"""
v2/grpc_server.py
─────────────────
Phase 3: Python gRPC Server for ACO-Sentinel.

Serves the cost engine, workload predictor, and confidence tracker logic
over gRPC to the Go scheduler plugin.
"""

from __future__ import annotations

import os
import sys
import time
import json
import yaml
import signal
import threading
import http.server
import math
from concurrent import futures
from typing import Dict

import grpc

# Add project root and libraries to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "proto")))

import sentinel_pb2
import sentinel_pb2_grpc
from confidence import (
    NodeConfidenceTracker,
    AdaptiveThresholdManager,
    calculate_freshness,
    calculate_heartbeat_consistency,
    calculate_internal_consistency,
    calculate_cross_consistency,
)
from orchestrator.control_plane.cost_engine import CostEngine
from orchestrator.shared.models import (
    ComputeNode,
    JobRequest,
    NodeTelemetry,
    ResourceRequest,
    WorkloadType,
)


class ConfigWatcher:
    """
    Background file-watcher reloading yaml configuration dynamically.
    """
    def __init__(self, path: str = "v2/sentinel-config.yaml") -> None:
        self.path = path
        # Try local path or root path
        if not os.path.exists(self.path):
            self.path = "sentinel-config.yaml"
        self.config: dict = {}
        self.load_config()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def load_config(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self.config = yaml.safe_load(f) or {}
                print(f"[Sentinel-ConfigWatcher] Configuration loaded from {self.path}")
            except Exception as e:
                print(f"[Sentinel-ConfigWatcher] Error loading config: {e}")

    def _watch_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(30)
            self.load_config()

    def stop(self) -> None:
        self._stop_event.set()


class StatePersistence:
    """
    Periodically flushes and recovers committed placement state to disk atomically.
    """
    def __init__(self, server: ACOPredictiveSchedulerServicer, path: str = "v2/sentinel_state.json") -> None:
        self.server = server
        self.path = path
        if not os.path.exists(os.path.dirname(self.path)) and os.path.dirname(self.path):
            self.path = "sentinel_state.json"
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._save_loop, daemon=True)
        self._thread.start()

    def _save_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(300)  # Flush every 5 minutes
            self.save()

    def save(self) -> None:
        data = {
            "committed_placements": self.server.committed_placements,
            "total_deposits": self.server.total_deposits,
            "phantom_deposits": self.server.phantom_deposits,
            "timestamp": time.time()
        }
        try:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f)
            os.rename(tmp_path, self.path)
            print(f"[Sentinel-Persistence] State flushed atomically to {self.path}")
        except Exception as e:
            print(f"[Sentinel-Persistence] Error writing state: {e}")

    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                self.server.committed_placements = data.get("committed_placements", {})
                self.server.total_deposits = data.get("total_deposits", 0)
                self.server.phantom_deposits = data.get("phantom_deposits", 0)
                print(f"[Sentinel-Persistence] State loaded successfully from {self.path}")
            except Exception as e:
                print(f"[Sentinel-Persistence] Error loading state: {e}")

    def stop(self) -> None:
        self._stop_event.set()


class FederationHTTPServer:
    """
    Exposes a lightweight, read-only HTTP server for pulling cluster placements.
    """
    def __init__(self, server: ACOPredictiveSchedulerServicer, port: int = 8083) -> None:
        self.server = server
        self.port = port

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(h) -> None:
                if h.path == "/pheromones":
                    h.send_response(200)
                    h.send_header("Content-Type", "application/json")
                    h.end_headers()
                    response = {
                        "placements": self.server.committed_placements,
                        "total_deposits": self.server.total_deposits,
                        "phantom_deposits": self.server.phantom_deposits
                    }
                    h.wfile.write(json.dumps(response).encode())
                else:
                    h.send_response(404)
                    h.end_headers()

            def log_message(h, format, *args) -> None:
                pass  # Suppress request logging to keep server console clean

        try:
            self.httpd = http.server.HTTPServer(("0.0.0.0", self.port), Handler)
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
            print(f"[Sentinel-FederationServer] Serving metrics on port {self.port}...")
        except Exception as e:
            print(f"[Sentinel-FederationServer] WARNING: Failed to start HTTP server: {e}")

    def stop(self) -> None:
        self.httpd.shutdown()


class ACOPredictiveSchedulerServicer(sentinel_pb2_grpc.ACOPredictiveSchedulerServicer):
    """
    gRPC service coordinating custom scoring and placement checks.
    """

    def __init__(self) -> None:
        self.cost_engine = CostEngine()
        self.confidence_trackers: Dict[str, NodeConfidenceTracker] = {}
        self.committed_placements: Dict[str, str] = {}
        self.phantom_deposits = 0
        self.total_deposits = 0
        self.threshold_manager = AdaptiveThresholdManager()
        self.config_watcher = ConfigWatcher()
        self.persistence = StatePersistence(self)
        self.persistence.load()
        self.fed_server = FederationHTTPServer(self)

    def ScoreNodes(
        self,
        request: sentinel_pb2.ScoreRequest,
        context: grpc.ServicerContext,
    ) -> sentinel_pb2.ScoreResponse:
        """
        Score a list of node candidates for a given pod spec.
        """
        if request.pod.uid == "healthz":
            return sentinel_pb2.ScoreResponse()
        if request.pod.uid == "reset":
            self.confidence_trackers.clear()
            self.committed_placements.clear()
            self.phantom_deposits = 0
            self.total_deposits = 0
            return sentinel_pb2.ScoreResponse()

        # Collect intervals and calculate CVs for active threshold management
        cv_values = []
        for n in request.nodes:
            if n.recent_heartbeat_intervals:
                intervals = list(n.recent_heartbeat_intervals)
                if len(intervals) >= 2:
                    mean = sum(intervals) / len(intervals)
                    if mean > 1e-6:
                        variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
                        std_dev = math.sqrt(variance)
                        cv_values.append(std_dev / mean)

        if cv_values:
            avg_cv = sum(cv_values) / len(cv_values)
            self.threshold_manager.evaluate_state(avg_cv)

        # Get dynamic thresholds
        thresholds = self.threshold_manager.get_thresholds()
        cv_max = thresholds["cv_max"]
        t_max = thresholds["t_max"]

        # Map workload type string to enum
        workload_type_map = {
            "batch": WorkloadType.BATCH,
            "latency-critical": WorkloadType.LATENCY_CRITICAL,
            "stream-processing": WorkloadType.STREAM,
        }
        w_type = workload_type_map.get(request.pod.workload_type.lower(), WorkloadType.BATCH)

        # Re-construct JobRequest object for CostEngine
        job = JobRequest(
            job_id=request.pod.uid,
            workload_type=w_type,
            resources=ResourceRequest(
                cpu_cores_min=request.pod.cpu_cores_requested,
                memory_gb_min=request.pod.memory_gb_requested,
            ),
        )

        # Determine "now" - use the max last_heartbeat_timestamp from the request nodes if available
        heartbeats = [n.last_heartbeat_timestamp for n in request.nodes if n.last_heartbeat_timestamp > 0]
        current_time = max(heartbeats) if heartbeats else time.time()

        scores = []
        for node_cand in request.nodes:
            node_id = node_cand.node_id

            # Initialize tracker if not exists
            if node_id not in self.confidence_trackers:
                self.confidence_trackers[node_id] = NodeConfidenceTracker(
                    node_id=node_id,
                    alpha=0.5,
                    initial_confidence=0.7,
                    t_max=t_max,
                    cv_max=cv_max,
                )
            tracker = self.confidence_trackers[node_id]
            tracker.cv_max = cv_max
            tracker.t_max = t_max

            # Record heartbeat timestamp
            if node_cand.last_heartbeat_timestamp > 0:
                tracker.record_heartbeat(node_cand.last_heartbeat_timestamp)

            # Compute raw and smoothed confidence
            if node_cand.recent_heartbeat_intervals:
                # Use intervals passed by Go plugin
                intervals = list(node_cand.recent_heartbeat_intervals)
                k_heartbeat = calculate_heartbeat_consistency(intervals, tracker.cv_max)
                k_internal = calculate_internal_consistency(
                    node_cand.reported_allocatable_cpu,
                    node_cand.reported_used_cpu,
                    node_cand.reported_free_cpu,
                )
                if node_cand.last_heartbeat_timestamp > 0:
                    delta_t = max(0.0, current_time - node_cand.last_heartbeat_timestamp)
                    k_fresh = calculate_freshness(delta_t, tracker.t_max)
                else:
                    k_fresh = 1.0
                k_cross = calculate_cross_consistency(
                    node_cand.allocatable_cpu,
                    node_cand.scheduler_expected_free_cpu,
                    node_cand.reported_free_cpu,
                )
                raw_conf = k_internal * k_fresh * k_heartbeat * k_cross
                kappa_i = tracker.ema.update(raw_conf)
            else:
                # Compute from tracker history
                kappa_i = tracker.update(
                    reported_allocatable=node_cand.reported_allocatable_cpu,
                    reported_used=node_cand.reported_used_cpu,
                    reported_free=node_cand.reported_free_cpu,
                    current_time=current_time,
                )
                k_cross = calculate_cross_consistency(
                    node_cand.allocatable_cpu,
                    node_cand.scheduler_expected_free_cpu,
                    node_cand.reported_free_cpu,
                )
                kappa_i = kappa_i * k_cross

            # Re-construct ComputeNode object for CostEngine
            node_telemetry = NodeTelemetry(
                node_id=node_id,
                cpu_util_pct=(
                    (node_cand.reported_used_cpu / node_cand.reported_allocatable_cpu * 100.0)
                    if node_cand.reported_allocatable_cpu > 0
                    else 0.0
                ),
                memory_util_pct=(
                    (
                        node_cand.reported_used_memory_gb
                        / node_cand.reported_allocatable_memory_gb
                        * 100.0
                    )
                    if node_cand.reported_allocatable_memory_gb > 0
                    else 0.0
                ),
            )

            compute_node = ComputeNode(
                node_id=node_id,
                total_cpu_cores=node_cand.allocatable_cpu,
                total_memory_gb=node_cand.allocatable_memory_gb,
                allocated_cpu_cores=node_cand.allocatable_cpu
                - node_cand.scheduler_expected_free_cpu,
                allocated_memory_gb=node_cand.allocatable_memory_gb
                - node_cand.scheduler_expected_free_memory_gb,
                latest_telemetry=node_telemetry,
            )

            # Base CostEngine heuristic score (prediction is None for clean split)
            eta = self.cost_engine.score_node(job, compute_node, prediction=None)

            # Apply trust-weighted discount
            final_score = eta * (kappa_i**request.gamma)

            scores.append(
                sentinel_pb2.NodeScore(
                    node_id=node_id,
                    eta=eta,
                    confidence=kappa_i,
                    final_score=final_score,
                )
            )

        return sentinel_pb2.ScoreResponse(scores=scores)

    def PlacementCommitted(
        self,
        request: sentinel_pb2.PlacementCommittedRequest,
        context: grpc.ServicerContext,
    ) -> sentinel_pb2.PlacementCommittedResponse:
        """
        Acknowledges if a pod placement was committed (success) or aborted/unreserved.
        """
        pod_uid = request.pod_uid
        node_id = request.node_id

        if request.success:
            self.committed_placements[pod_uid] = node_id
            self.total_deposits += 1
            print(
                f"[Sentinel-Server] COMMIT: Pheromone deposit confirmed on node {node_id} "
                f"for pod {pod_uid}."
            )
            # Replicas update pheromones in memory (equivalent logic to _deposit_pheromone)
        else:
            self.phantom_deposits += 1
            print(
                f"[Sentinel-Server] ROLLBACK: Bind failed or unreserved for pod {pod_uid} "
                f"on node {node_id}. Rollback triggered."
            )

        return sentinel_pb2.PlacementCommittedResponse(acknowledged=True)


def serve(port: int = 50051) -> tuple[grpc.Server, ACOPredictiveSchedulerServicer]:
    """Start the gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = ACOPredictiveSchedulerServicer()
    sentinel_pb2_grpc.add_ACOPredictiveSchedulerServicer_to_server(
        servicer, server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[Sentinel-Server] Listening on port {port}...")
    return server, servicer


if __name__ == "__main__":
    server, servicer = serve()

    def shutdown_handler(signum, frame) -> None:
        print(f"[Sentinel-Server] Received signal {signum}, persisting state and shutting down...")
        servicer.persistence.save()
        servicer.persistence.stop()
        servicer.config_watcher.stop()
        servicer.fed_server.stop()
        server.stop(0)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        while True:
            time.sleep(86400)
    except SystemExit:
        pass

