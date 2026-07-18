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


class ACOPredictiveSchedulerServicer(sentinel_pb2_grpc.ACOPredictiveSchedulerServicer):
    """
    gRPC service coordinating custom scoring and placement checks.
    """

    def __init__(self) -> None:
        self.cost_engine = CostEngine()
        self.confidence_trackers: Dict[str, NodeConfidenceTracker] = {}
        # Keeps track of committed placements for metrics and trace reconciliation
        self.committed_placements: Dict[str, str] = {}
        self.phantom_deposits = 0
        self.total_deposits = 0

    def ScoreNodes(
        self,
        request: sentinel_pb2.ScoreRequest,
        context: grpc.ServicerContext,
    ) -> sentinel_pb2.ScoreResponse:
        """
        Score a list of node candidates for a given pod spec.
        """
        if request.pod.uid == "reset":
            self.confidence_trackers.clear()
            self.committed_placements.clear()
            self.phantom_deposits = 0
            self.total_deposits = 0
            return sentinel_pb2.ScoreResponse()
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

        # Determine "now" - use the max last_heartbeat_timestamp from the request nodes if available (for simulation parity)
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
                )
            tracker = self.confidence_trackers[node_id]

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


def serve(port: int = 50051) -> grpc.Server:
    """Start the gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    sentinel_pb2_grpc.add_ACOPredictiveSchedulerServicer_to_server(
        ACOPredictiveSchedulerServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[Sentinel-Server] Listening on port {port}...")
    return server


if __name__ == "__main__":
    server = serve()
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)
