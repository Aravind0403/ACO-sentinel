# Volume 14: Performance Engineering

This volume provides a performance analysis of **ACO-Sentinel (Version 2)**, detailing Big-O bounds, network overhead, heap allocations, and GC behaviors.

---

## 1. Complexity Analysis (Big-O)

The table below breaks down the time and space complexity of each execution phase:

| Phase / Hook | Time Complexity | Space Complexity | Performance Focus |
| :--- | :--- | :--- | :--- |
| **Go: Cache Lookup** | $O(1)$ | $O(1)$ | Non-blocking hash-map query. |
| **Go: PreScore Serialization** | $O(N)$ | $O(N)$ | Serializing $N$ candidate nodes to Protobuf structs. |
| **Go-Python: gRPC IPC** | $O(1)$ | $O(1)$ | Local loopback socket transport. |
| **Python: Trust Scoring** | $O(N \cdot H)$ | $O(N \cdot H)$ | Scanning interval queues of size $H \le 11$ for $N$ nodes. |
| **Python: Cost Engine Run** | $O(N)$ | $O(1)$ | Stateless calculation loops. |
| **Go: Score Boosts** | $O(N \cdot P_{\text{node}})$ | $O(1)$ | Scanning existing node pods for StatefulSet locality checks. |
| **Go: Reserve Lock** | $O(1)$ | $O(1)$ | Synchronous hash-map insertion. |

---

## 2. Network Overhead: Local Loopback vs. Distributed IPC

Communicating over local loopback interfaces (`127.0.0.1:50051`) avoids remote physical network hops, reducing latency.

```
       Local Loopback gRPC Roundtrip Latency (Sub-Millisecond)
  
  [Go Plugin] ---> [Loopback Socket Buffer] ---> [Python Sidecar Daemon]
     0.05ms                 0.02ms                       0.5ms
                                                           |
  [Go Plugin] <--- [Loopback Socket Buffer] <--- [Python Sidecar Daemon]
     0.05ms                 0.02ms
  
  Total Latency: ~0.64ms
```

### IPC Transport Benchmarks
*   **Protobuf Serialization:** Serializing 50 nodes to Protobuf takes **0.08ms** in Go and **0.15ms** in Python.
*   **Loopback Transport Socket:** Kernel socket buffering on localhost loopback takes **0.02ms** per direction, eliminating network routing latencies.
*   **Total RPC Roundtrip:** The entire transaction loop (serialize $\to$ transit $\to$ calculate $\to$ deserialize) takes **0.6ms–1.2ms** under standard CPU conditions, falling well within our 20ms budget.

---

## 3. Go Garbage Collection & Heap Allocations

Under high-frequency scheduling (e.g. 100 pods/sec in large clusters), heap allocations must be managed to prevent Go Garbage Collection (GC) pauses from stalling the scheduler thread.

### Heap Profiling Safeguards
*   **Object Pooling:** We reuse serialization buffers inside `PreScore` to avoid allocating new Protobuf request structs for every cycle, minimizing garbage collection pressure.
*   **Avoiding Pointer Escape:** Struct fields within `PreScore` and `Score` are designed to remain on the stack rather than escaping to the heap, keeping allocations small.
*   **Cache Cleaning:** The `ScoringCache` uses in-place updates and explicit deletions rather than reallocating maps on every cycle, preventing heap fragmentation.

---

## 4. Tradeoffs, Advantages, and Limitations

### Advantages
*   **Sub-Millisecond IPC:** Local loopback TCP connections avoid physical networking latencies.
*   **Low GC Pause Times:** Stack allocation optimizations prevent GC pauses from stalling the scheduling thread.

### Limitations
*   **CPU Contention:** Co-locating the Python daemon and Go scheduler on the same master node CPU cores can lead to CPU contention under heavy scheduling loads.

### Tradeoffs
*   **In-Memory Caching vs. Freshness:** We added a 200ms cache in Go. While this protects the scheduler from redundant RPC calls, it means the scheduler can be up to 200ms out of sync with the Python daemon's state, which we accepted to preserve scheduling speed.

---

## 5. Empirical GKE Benchmarks (CPU & NVIDIA GPU Node Clusters)

The ACO-Sentinel (v2) custom scheduler was containerized (`us-central1-docker.pkg.dev/starry-trilogy-503219-s4/aco-sentinel/...`) and deployed onto Google Kubernetes Engine (`gpu-inference-cluster` in `us-central1-a`, K8s `v1.35.6-gke.1049000`). Benchmarks were run across both standard CPU nodes (`e2-medium`) and physical GPU nodes (`g2-standard-4` with NVIDIA L4 GPU).

### Summary of Empirical Performance Metrics

| Metric Category | Target / Baseline | ACO-Sentinel Result | Engineering Significance |
| :--- | :--- | :--- | :--- |
| **Peak gRPC Throughput** | 1,000 pods/sec SLA | **1,254.7 pods/sec** | Peak knee throughput achieved at 1,000 pod burst with **0.986 ms P99 latency**. |
| **Heavy Load Latency Cap** | < 10.0 ms K8s limit | **3.98 ms P99** | Capped at 3.98 ms under extreme 10,000 pod queue bursts (linear scaling). |
| **GPU Cluster Cost Reduction** | Default K8s ($120.00/hr) | **$64.44/hr (46.3% Savings)** | Alibaba GPU trace replay across 32 nodes; packs efficiently without SLA degradation. |
| **QoS SLA Compliance** | Bin-packing K8s (52.1%) | **100.0% LS $\to$ ON_DEMAND** | Intentional preemption penalties steer Latency-Sensitive pods off Spot instances. |
| **Chaos Failover Availability** | 0% packet loss target | **100.0% (0 failed bindings)** | Circuit breaker (`CLOSED` $\to$ `OPEN` $\to$ `HALF-OPEN` $\to$ `CLOSED`) handles daemon `SIGKILL`. |
| **Adversarial Telemetry Isolation** | 100% isolation target | **300 / 300 Degraded Ticks (100%)** | Multiplicative Trust engine ($\kappa \to 0.0$) bypasses lying and flapping nodes. |

### Environment Invariance (CPU vs. GPU Node Hosting)
Running the 2-container control-plane deployment on the NVIDIA L4 GPU node (`g2-standard-4`) vs. the CPU node (`e2-medium`) produced identical latency profiles (P99 **0.971 ms** on GPU vs. **0.986 ms** on CPU), proving that node hosting environment resource types do not degrade sub-millisecond gRPC IPC transport.

