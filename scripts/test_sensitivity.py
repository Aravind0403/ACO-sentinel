#!/usr/bin/env python3
"""
scripts/test_sensitivity.py
───────────────────────────
Performs binary search sweeps via gRPC to detect the exact boundary
conditions under which the ACO-Sentinel trust model begins to decay.
"""

from __future__ import annotations

import os
import sys
import time
import math

# Add proto and v2 directories to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "v2", "proto")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "v2")))

try:
    import grpc
    import sentinel_pb2
    import sentinel_pb2_grpc
except ImportError as e:
    print(f"Error importing gRPC dependencies: {e}")
    print("Ensure you have run 'pip install grpcio grpcio-tools' or are in the correct python virtual environment.")
    sys.exit(1)


class SensitivityAnalyzer:
    def __init__(self, stub: sentinel_pb2_grpc.ACOPredictiveSchedulerStub) -> None:
        self.stub = stub
        self.results: list[dict] = []

    def get_trust_for_candidate(self, node: sentinel_pb2.NodeCandidate) -> float:
        # Construct dummy pod
        pod = sentinel_pb2.PodSpec(
            uid="sensitivity-test-pod",
            name="test-pod",
            namespace="default",
            cpu_cores_requested=1.0,
            memory_gb_requested=2.0,
            workload_type="batch"
        )
        req = sentinel_pb2.ScoreRequest(
            pod=pod,
            nodes=[node],
            gamma=2.0
        )
        try:
            confidence = 0.0
            for _ in range(10):
                resp = self.stub.ScoreNodes(req)
                if resp.scores:
                    confidence = resp.scores[0].confidence
            return confidence
        except Exception as e:
            print(f"gRPC call failed: {e}")
        return 0.0

    def test_cpu_overreport(self, mismatch: float) -> float:
        node = sentinel_pb2.NodeCandidate(
            node_id="test-node-cpu",
            allocatable_cpu=8.0,
            allocatable_memory_gb=16.0,
            scheduler_expected_free_cpu=4.0,
            scheduler_expected_free_memory_gb=8.0,
            reported_allocatable_cpu=8.0,
            reported_used_cpu=4.0,
            reported_free_cpu=4.0 - mismatch,  # Introduce mismatch
            reported_allocatable_memory_gb=16.0,
            reported_used_memory_gb=8.0,
            reported_free_memory_gb=8.0,
            last_heartbeat_timestamp=time.time(),
            recent_heartbeat_intervals=[10.0, 10.0, 10.0, 10.0, 10.0]
        )
        # Reset tracker state on server first using dummy pod UID "reset"
        self.stub.ScoreNodes(sentinel_pb2.ScoreRequest(
            pod=sentinel_pb2.PodSpec(uid="reset"),
            nodes=[]
        ))
        return self.get_trust_for_candidate(node)

    def test_memory_mismatch(self, mismatch: float) -> float:
        node = sentinel_pb2.NodeCandidate(
            node_id="test-node-mem",
            allocatable_cpu=8.0,
            allocatable_memory_gb=16.0,
            scheduler_expected_free_cpu=4.0,
            scheduler_expected_free_memory_gb=8.0,
            reported_allocatable_cpu=8.0,
            reported_used_cpu=4.0,
            reported_free_cpu=4.0,
            reported_allocatable_memory_gb=16.0,
            reported_used_memory_gb=8.0,
            reported_free_memory_gb=8.0 - mismatch,  # Introduce mismatch
            last_heartbeat_timestamp=time.time(),
            recent_heartbeat_intervals=[10.0, 10.0, 10.0, 10.0, 10.0]
        )
        self.stub.ScoreNodes(sentinel_pb2.ScoreRequest(
            pod=sentinel_pb2.PodSpec(uid="reset"),
            nodes=[]
        ))
        return self.get_trust_for_candidate(node)

    def test_heartbeat_jitter(self, jitter: float) -> float:
        # Mean interval = 10s. CV = std_dev / mean.
        # Intervals list: alternate [10 - jitter, 10 + jitter]
        intervals = [10.0 - jitter, 10.0 + jitter, 10.0 - jitter, 10.0 + jitter, 10.0]
        node = sentinel_pb2.NodeCandidate(
            node_id="test-node-jitter",
            allocatable_cpu=8.0,
            allocatable_memory_gb=16.0,
            scheduler_expected_free_cpu=4.0,
            scheduler_expected_free_memory_gb=8.0,
            reported_allocatable_cpu=8.0,
            reported_used_cpu=4.0,
            reported_free_cpu=4.0,
            reported_allocatable_memory_gb=16.0,
            reported_used_memory_gb=8.0,
            reported_free_memory_gb=8.0,
            last_heartbeat_timestamp=time.time(),
            recent_heartbeat_intervals=intervals
        )
        self.stub.ScoreNodes(sentinel_pb2.ScoreRequest(
            pod=sentinel_pb2.PodSpec(uid="reset"),
            nodes=[]
        ))
        return self.get_trust_for_candidate(node)

    def binary_search_threshold(self, test_func, min_val: float, max_val: float, precision: float = 0.001) -> float:
        # Binary search for the perturbation level where trust score drops below 0.95
        while max_val - min_val > precision:
            mid = (min_val + max_val) / 2
            trust = test_func(mid)
            if trust >= 0.95:
                min_val = mid
            else:
                max_val = mid
        return (min_val + max_val) / 2

    def run_detection_sweep(self) -> None:
        print("\n=== STARTING AUTOMATED SENSITIVITY DETECTION SWEEP ===")
        test_cases = [
            ("CPU Telemetry Mismatch (Cores)", self.test_cpu_overreport, 0.0, 4.0),
            ("Memory Telemetry Mismatch (GB)", self.test_memory_mismatch, 0.0, 8.0),
            ("Heartbeat Interval Jitter (Secs)", self.test_heartbeat_jitter, 0.0, 5.0),
        ]

        for name, test_func, min_val, max_val in test_cases:
            print(f"Sweeping parameter: '{name}'...")
            threshold = self.binary_search_threshold(test_func, min_val, max_val)
            normalized_sensitivity = threshold / max_val
            self.results.append({
                "metric": name,
                "threshold": round(threshold, 4),
                "max_value": max_val,
                "sensitivity": round(normalized_sensitivity, 4)
            })

    def print_report(self) -> None:
        print("\n" + "="*70)
        print("                 ACO-SENTINEL SENSITIVITY REPORT")
        print("="*70)
        print(f"{'Metric':<35} | {'Decay Threshold':<15} | {'Normalized Sensitivity':<20}")
        print("-"*70)
        for r in self.results:
            print(f"{r['metric']:<35} | {r['threshold']:<15} | {r['sensitivity']:<20}")
        print("="*70)
        print("Note: Decay Threshold marks where the composite trust drops below 0.95.")
        print("="*70 + "\n")


def main():
    print("Connecting to sidecar gRPC server at 127.0.0.1:50051...")
    channel = grpc.insecure_channel("127.0.0.1:50051")
    try:
        # Check connection (short timeout)
        grpc.channel_ready_future(channel).result(timeout=3)
    except grpc.FutureTimeoutError:
        print("Error: Could not connect to gRPC server at 127.0.0.1:50051.")
        print("Please start the gRPC sidecar daemon first: 'python3 v2/grpc_server.py'")
        sys.exit(1)

    stub = sentinel_pb2_grpc.ACOPredictiveSchedulerStub(channel)
    analyzer = SensitivityAnalyzer(stub)
    analyzer.run_detection_sweep()
    analyzer.print_report()


if __name__ == "__main__":
    main()
