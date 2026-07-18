# Project Tutor: ACO-Sentinel (Version 2)

Welcome to the running tutorial and design log for **ACO-Sentinel (Version 2)**. This document serves as a study guide, tracing key design patterns, trade-offs, coding techniques, and senior engineer interview questions for each phase of the build.

---

## Phase 1: Confidence Math (Trust-Weighted Heuristics)

In Phase 1, we implement the mathematical models that calculate how much the scheduler can trust node telemetry before letting it influence our stateful Ant Colony Optimization (ACO) pheromone trails.

### 1. Key Concepts & Mathematical Formulas

Rather than hard-rejecting nodes with poor telemetry (which can crash scheduling throughput), we introduce a discount factor $\kappa_i$ into the node selection heuristic:
$$\text{FinalScore}_i = \eta_i \times \kappa_i^\gamma$$

We break trust down into three independent, multiplicative dimensions computed in Python, plus one computed natively in Go:

#### A. Internal Consistency ($\kappa_{\text{internal}, i}$)
*   **Formula:** $\kappa_{\text{internal}, i} = \max(0, 1 - \Delta_i / A_i)$ where $\Delta_i = |(A_i - U_i) - F_i|$
*   **Meaning:** Does the node's reported state match simple arithmetic? If reported Allocatable ($A_i$), Used ($U_i$), and Free ($F_i$) memory/CPU do not balance, the node agent is reporting garbage or is internally broken.

#### B. Telemetry Freshness ($\kappa_{\text{fresh}, i}$)
*   **Formula:** $\kappa_{\text{fresh}, i} = \max(0, 1 - \Delta t_i / T_{\text{max}})$
*   **Meaning:** How old is the last heartbeat? If $\Delta t_i \ge T_{\text{max}}$ (e.g. 30 seconds), the node has gone quiet, and we exponentially discount our confidence in its load state.

#### C. Heartbeat Consistency ($\kappa_{\text{heartbeat}, i}$)
*   **Formula:** $\kappa_{\text{heartbeat}, i} = \max(0, 1 - \text{CV}_i / \text{CV}_{\text{max}})$
*   **Meaning:** Is the telemetry reporting cadence stable or flapping? $\text{CV}_i$ is the **Coefficient of Variation** (Standard Deviation / Mean) of the intervals between recent heartbeats. A flapping network connection or overloaded node CPU will cause telemetry packets to arrive erratically, raising $\text{CV}_i$ and discounting trust.

#### D. The EMA Smoothing Filter
Just as we use an Exponential Moving Average (EMA) to predict node utilization trends (reusing the findings from the HiPC paper), we apply an EMA filter to node confidence $\kappa$ over time. 
*   **Seeding (Cold Start):** When a new node joins, we initialize its confidence to a moderate default ($0.6\text{--}0.7$) rather than $1.0$ (too trusting of unverified capacity) or $0.0$ (which would make the node unschedulable).
*   **Update:**
    $$\kappa_{\text{smoothed}, t} = \alpha \cdot \kappa_{\text{raw}, t} + (1 - \alpha) \cdot \kappa_{\text{smoothed}, t-1}$$

---

### 2. Architectural Trade-offs

| Design Decision | Pros | Cons |
| :--- | :--- | :--- |
| **Multiplicative vs. Additive Confidence** | A single zero-value trust component drags the overall score to $0$ immediately (hard veto). | Small errors in multiple dimensions compound and discount node scores heavily. |
| **EMA Trust Smoothing** | Prevents jitter or singular dropped packets from triggering massive scheduling shifts. | Delays reactions to a node that suddenly begins sending corrupted telemetry. |
| **Decoupled Cross-Consistency** | Keeping scheduler-state checks ($\kappa_{\text{cross}}$) in Go avoids network serialization costs and dual-write desyncs. | Splits the trust calculation logic across two codebases (Go and Python). |

---

### 3. Senior Engineer Interview Questions

#### Q1: "Why did you choose a multiplicative $\kappa_i$ rather than an additive penalty (like subtracting confidence from the score)?"
*   **Answer:** Additive penalties are highly sensitive to the scale of the base score. If a premium node has a very high base cost-engine score, a flat subtracted penalty might not be enough to prevent a high-priority job from landing there despite compromised telemetry. A multiplicative discount scales naturally: if confidence is zero, the product is zero, converting to a hard gate automatically.

#### Q2: "How did you determine $T_{\text{max}}$ and $\text{CV}_{\text{max}}$? Aren't these just magic numbers?"
*   **Answer:** They are operational thresholds that must map directly to the telemetry sampling rate ($T_{\text{sample}}$). For example, if heartbeats arrive every $5\text{s}$, $T_{\text{max}}$ should be set to $3 \times T_{\text{sample}}$ ($15\text{s}$) to allow for up to two missed packet arrivals before triggering a discount. For $\text{CV}_{\text{max}}$, a standard deviation equal to the mean ($\text{CV}=1.0$) indicates a highly erratic Poisson-like arrival process; setting $\text{CV}_{\text{max}} = 0.5$ acts as a reasonable threshold for alarming on reporting jitter.

#### Q3: "Why does the trust score default to a neutral $1.0$ when the validator pipeline is down?"
*   **Answer:** This prevents the trust layer from becoming a single point of failure (SPOF) for scheduling. If a bug crashes the validator, setting confidence to $0.0$ across all nodes would reduce all $\eta_i$ scores to $0$, causing the extender/plugin to reject the entire cluster and halt all deployments. Defaulting to $1.0$ allows the system to degrade gracefully to base cost-aware scheduling.

---

## Phase 2: Protocol Contract (.proto)

In Phase 2, we define the API contracts using Protocol Buffers and generate type-safe stubs in both Go and Python to build the gRPC communication layer.

### 1. Key Concepts: Why Protocol Buffers?

Standard Kubernetes extenders use JSON over HTTP. While simple, JSON is:
*   **Schema-less:** A change in the spelling of a field in Python (e.g. `gpu_util_pct` vs `gpu_utilisation`) causes runtime parsing errors without compile-time warning.
*   **Heavy to parse:** Text serialization is CPU-expensive.
*   **Single-stream:** HTTP/1.1 requires a TCP connection per concurrent request or head-of-line blocking.

gRPC uses **Protocol Buffers (protobuf)** and **HTTP/2**:
*   **Strict Contracts:** Field names and type constraints are compiled directly. If the Go plugin sends `scheduler_expected_free` as a float but Python expects a string, it fails immediately at serialization.
*   **Persistent HTTP/2 Multiplexing:** Multiple scheduling streams (`ScoreNodes`, `PlacementCommitted`) run concurrently over a single shared TCP connection.

### 2. Architectural Design of sentinel.proto

The contract is structured as follows:

```protobuf
syntax = "proto3";
package sentinel;
option go_package = "./pb";

service ACOPredictiveScheduler {
  rpc ScoreNodes(ScoreRequest) returns (ScoreResponse);
  rpc PlacementCommitted(PlacementCommittedRequest) returns (PlacementCommittedResponse);
}
```

*   `ScoreRequest`: Packs the pod's resources (CPU, Memory, GPU) and a list of `NodeCandidate` profiles containing both Go-measured values (allocatable, scheduler expected free) and node-reported telemetry.
*   `ScoreResponse`: Returns calculated `eta` (base heuristic), `confidence` ($\kappa_i$), and `final_score` ($\eta_i \times \kappa_i^\gamma$).
*   `PlacementCommittedRequest`: Sends the pod UID, selected node ID, and a boolean `success` flag indicating if the scheduling bind succeeded, allowing the Python daemon to update the pheromone matrix.

### 3. Senior Engineer Interview Questions

#### Q1: "Why do we pass the `gamma` ablation parameter inside the `ScoreRequest` instead of hardcoding it in the Python daemon configuration?"
*   **Answer:** Passing parameters like `gamma` on a per-request basis allows dynamic policy configuration. For example, different namespaces or SLA tiers can use different levels of trust sensitivity (e.g., highly sensitive $\gamma=4$ for system critical tasks, but $\gamma=0.5$ for low-priority batch jobs). It also facilitates automated dynamic sweeps and validation experiments without having to reload or reconfigure the sidecar service.

#### Q2: "What happens if the gRPC channel disconnects mid-transaction? How does the Go plugin handle it?"
*   **Answer:** If the gRPC call fails or times out, the Go plugin catches the error and degrades gracefully: it returns a neutral score/filtering decision (effectively bypassing the ACO optimizer) and increments a fallback failure metric. This ensures the scheduler is resilient to sidecar failures.

---

---

## Phase 3: Python gRPC Server

In Phase 3, we implement the Python gRPC daemon, which wraps the existing CostEngine and maps incoming Protobuf payload structures to Pydantic domain models to run trust-weighted heuristics.

### 1. Key Concepts: The Mapping Boundary

The gRPC server acts as a bridge between the K8s system representation (Protobuf) and our validated algorithmic core. We perform two translations:
*   **Request Translation:** The incoming `PodSpec` and `NodeCandidate` Protobuf messages are converted to Python `JobRequest` and `ComputeNode` structures, matching the cost engine's expectations.
*   **Trust Injection:** For each candidate node, we retrieve its running `NodeConfidenceTracker` from an in-memory dictionary. We update its metrics (freshness, internal consistency, and heartbeat variation) and calculate its smoothed trust factor $\kappa_i$.
*   **Discount Application:** We call `CostEngine.score_node` to compute $\eta_i$ and return the final discounted value:
    $$\text{FinalScore}_i = \eta_i \times \kappa_i^\gamma$$

### 2. The PlacementCommitted Callback

Instead of depositing pheromones speculatively inside `ScoreNodes` (as in Version 1), we implement a `/PlacementCommitted` RPC.
*   The Go plugin calls this endpoint *after* K8s successfully executes the pod binding transaction.
*   If K8s rejects the placement (e.g. downstream quota check failure) or the reservation fails, the Go plugin sends `success = false`, which increments rollback counters and skips the pheromone deposit, keeping the state clean.

### 3. Senior Engineer Interview Questions

#### Q1: "What is the memory footprint of maintaining `NodeConfidenceTracker` states in-memory? Can this cause leaks as nodes join/leave?"
*   **Answer:** Each tracker is tiny, containing a FIFO list of up to 11 timestamps and a few floats (less than 200 bytes per node). Even for a 10,000-node cluster, the memory footprint is under 3MB. To prevent leaks in clusters with high node churn, we can implement an eviction policy (e.g., clearing trackers for nodes that have not reported a heartbeat in over 1 hour).

#### Q2: "Why is the placement confirmation asynchronous? What if the network drops before the confirmation is delivered?"
*   **Answer:** If the confirmation is delayed or lost, the scheduling flow is unaffected—K8s has already successfully bound the pod, and the job is running. The only impact is that the Python daemon misses a single pheromone deposit, which the statistical learning of the ACO colony (averaging over many iterations) is highly robust against.

---

---

## Phase 4: Go Scheduler Plugin

In Phase 4, we write the native Go plugin using the Kubernetes Scheduling Framework, implementing the transactional lifecycle hooks (`Score`, `Reserve`, `Unreserve`, and `PostBind`).

### 1. The Cross-Consistency Formula ($\kappa_{\text{cross}}$)

Only the Go plugin has access to the scheduler’s internal assumed cache state. Thus, Go calculates the cross-scheduler consistency metric $\kappa_{\text{cross}, i}$ and passes it to the Python sidecar:
$$\kappa_{\text{cross}, i} = \max(0, 1 - |\text{SchedulerExpectedFree}_i - F_i| / A_i)$$
where:
$$\text{SchedulerExpectedFree}_i = \text{Allocatable}_i - \sum(\text{bound-pods}) - \sum(\text{assumed reservations})$$
If this diverges significantly from the node's reported free capacity ($F_i$), it indicates the node telemetry is lying or desynced, triggering a discount.

### 2. Transaction Hooks in Go

*   **Score:** The plugin queries the Python gRPC daemon’s `ScoreNodes` method, passing the pod requirements, candidate nodes, and the computed $\kappa_{\text{cross}}$ parameters.
*   **Reserve:** Go records the chosen node ID for each pod UID inside an in-memory, mutex-guarded map: `map[string]string`. No resource accounting is duplicated; K8s’s internal assumed cache handles the actual CPU/memory allocations natively.
*   **Unreserve:** If binding fails downstream, K8s triggers `Unreserve`. The Go plugin calls the Python daemon’s `PlacementCommitted` endpoint with `success = false`, removing the local mapping and rolling back the decision.
*   **PostBind:** Once K8s confirms the binding was successfully created on the API server, `PostBind` fires. The plugin calls `PlacementCommitted` with `success = true`, committing the pheromone deposit.

### 3. Senior Engineer Interview Questions

#### Q1: "Why can we safely use a simple in-memory Go map for `Reserve` and `Unreserve` instead of a distributed Redis lock?"
*   **Answer:** In production, high-availability `kube-scheduler` deployments run with leader election enabled. Strictly only **one** scheduler process is active and writing placements at any given instant. This guarantees that all concurrent placement transactions are managed by a single process, making a local, mutex-guarded Go map perfectly safe, thread-safe, and infinitely faster than a Redis round-trip.

#### Q2: "How does the Go plugin handle the case where the Python gRPC daemon crashes or is temporarily unreachable?"
*   **Answer:** The gRPC client connection uses a short call timeout (e.g. 50ms). If the call fails or times out, the `Score` hook logs the warning, increments a fallback counter, and returns a neutral score (e.g. `100` or `0` for all nodes), allowing the scheduler to degrade gracefully to K8s's default scoring rather than blocking pod scheduling completely.

---

## Phase 5: Go Simulation Harness & Experiments

In Phase 5, we implement a lightweight, self-contained Go simulation harness to verify the transactional scheduling loop and evaluate routing behavior under adversarial telemetry conditions.

### 1. Key Concepts: Simulated Telemetry Scenarios

To prove the trust-weighted heuristic works under adversarial scenarios, we construct a 100-job scheduling sweep over 4 nodes:
*   `node-safe-cheap` & `node-safe-expensive`: High reliability, sending consistent heartbeats every 5s.
*   `node-adversarial`: Reports 100% free CPU (lying arithmetically and violating reservation cache), but sends heartbeats regularly (healthy freshness and cadence).
*   `node-flapping`: Reports correct metrics, but has irregular telemetry intervals (high cadence jitter, $\text{CV}=0.8 \ge \text{CV}_{\text{max}}$).

### 2. Trust Discount Exponent ($\gamma$) Sweeps

By sweeping the trust discount exponent $\gamma \in \{0, 0.5, 1, 2, 4\}$, we observe a clear transition:
*   At $\gamma = 0$ (no trust discounting), the scheduler schedules almost exclusively on the adversarial and cheap nodes because they appear cheap and free, ignoring the trust risks.
*   As $\gamma$ increases, the penalty for untrusted telemetry increases, shifting scheduling decisions to healthy nodes.
*   At $\gamma = 4.0$, the degraded/flapping nodes are completely avoided, with 100% of the workload successfully routed to the healthy/safe nodes.

### 3. Verification Resequencing

> [!IMPORTANT]
> **Architectural Note on Parity Verification:**
> Local Kubernetes clusters (like `kind`) or simulators (like `kwok`) require active container runtimes and control planes, which are not present in sandbox verification environments. To keep local development blocker-free, we:
> 1. Verified core framework logic and sweeps using a custom Go Simulation Harness ([simulation/main.go](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront/v2/go_plugin/simulation/main.go)).
> 2. Deferred the real-cluster parity verification directly to the GKE Autopilot phase (Phase 6), where GKE Autopilot resources are used directly for verification, bypassing local runtime blockers.

### 4. Senior Engineer Interview Questions

#### Q1: "How did you synchronize time between the Go simulation loop and the Python gRPC daemon without using mock date libraries?"
*   **Answer:** Instead of using mock time libraries, we designed the Python gRPC daemon's `/ScoreNodes` endpoint to check if any of the incoming `NodeCandidate` profiles have a positive `last_heartbeat_timestamp`. If they do, the server extracts the maximum timestamp as the current logical time. This "simulated clock" synchronization ensures deterministic time tracking for freshness during test runs, while defaulting to `time.time()` in production.

#### Q2: "What does the $\gamma$ sweep tell us about the choice of $\gamma$ for production clusters?"
*   **Answer:** It demonstrates the sensitivity curve of trust discounting. A very high $\gamma$ (e.g. 4.0) behaves like a hard gate, actively avoiding any node with the slightest telemetry degradation. A lower $\gamma$ (e.g. 0.5) acts as a soft discount, allowing nodes with temporary network jitter to still be utilized for low-priority tasks if the price is low enough. In production, $\gamma$ should be configured based on tenant namespace SLAs.

---

## Future Phases Index (Outline)
*   **Phase 6: GKE Autopilot Validation:** Running cloud-parity pricing runs with minimal spend, serving as the real-cluster deployment gate.
*   **Phase 7: Wrap-up & Packaging:** Drafting writeups and publishing.

