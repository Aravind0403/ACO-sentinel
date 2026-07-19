# ACO-Sentinel: Project Progress Tracking

**Last Updated:** 2026-07-19
**Current Version:** V2 (gRPC-based Custom Scheduler Plugin + Telemetry Consistency Daemon)

---

## 1. Summary of Recent Progress (KWOK Validation Run)
We have successfully completed high-fidelity validation of the **ACO-Sentinel (V2)** scheduler on a simulated K8s control plane using **KWOK (Kubernetes Without Kubelet)**. 

### A. Scheduling Framework & Telemetry Integration
* **Plugin Registration:** The custom Go scheduler plugin `ACOPredictiveScheduler` was successfully integrated into the active scheduling loop with `weight: 100` (resolving config weighting issues from older builds).
* **Mathematical Trust Discounting:** Telemetry consistency checking was validated in real time against nodes with different reliability behaviors:
  * **Adversarial Isolation:** `node-adversarial` (which reported a fake resource state) was completely isolated (0 pod placements) after its internal consistency trust score ($k_{internal}$) collapsed to `0.0`.
  * **Flapping Network Penalty:** `node-flapping` (which reported heartbeats with high jitter) suffered a **72.1% trust penalty** ($k_{heartbeat} = 0.2786$), routing only 1 pod during cold-start before being bypassed.
* **Transactional Rollback (Commit vs. Rollback):**
  * Implemented and tested transactional rollback using a `PreBind` interception in the Go scheduler plugin (for `pod-rollback`).
  * The Go plugin successfully caught the bind failure, aborted, and called the Python sidecar's `/PlacementCommitted` gRPC client with `Success: false` during the `Unreserve` phase, preventing phantom pheromone updates.

### B. Workload Count Audit & Reconciliation
All 15 test pods were successfully accounted for:
* **API Admission Rejects:** 2 pods (`pod-11` and `pod-12`) were rejected at admission time by K8s `ResourceQuota` constraints (CPU limit of 20 cores).
* **Successful Commits:** 12 pods bound successfully (9 on `node-safe-expensive`, 2 on `node-safe-cheap`, 1 on `node-flapping`).
* **Aborted Rollbacks:** 1 pod (`pod-rollback`) was unreserved.
* **Formula Check:** $12\text{ commits} + 1\text{ rollback} + 2\text{ rejects} = 15\text{ pods}$.

---

## 2. Phase Flow Coverage

Based on the roadmap outlined in [Project_Tutor.md](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/Project_Tutor.md):

| Phase | Focus | Status | Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Confidence Math & Trust Heuristics | **Covered** | Formulas for $k_{internal}$, $k_{fresh}$, $k_{heartbeat}$ (Python) and $k_{cross}$ (Go). |
| **Phase 2** | Protocol Contract (`sentinel.proto`) | **Covered** | gRPC protobuf definitions and generated stubs. |
| **Phase 3** | Python gRPC Server | **Covered** | Telemetry tracking and `/ScoreNodes` & `/PlacementCommitted` APIs. |
| **Phase 4** | Go Scheduler Plugin | **Covered** | Custom K8s Scheduling Framework overrides (`PreScore` to `PostBind`). |
| **Phase 5** | Go Simulation Harness & Sweeps | **Covered** | sweeps of trust exponent $\gamma \in \{0, 0.5, 1, 2, 4\}$ proving workload routing sensitivity. |
| **Phase 6** | Real-Cluster/Production Validation | **In Progress** | Local virtual cluster validation (KWOK) complete. Transitioning cloud-scale run. |
| **Phase 7** | Wrap-up & Packaging | **Pending** | Documentation write-up and final telemetry packaging. |

---

## 3. Deployment Migration: Chameleon Cloud vs. GKE

We are updating the deployment strategy for **Phase 6** (Real-Cluster/Production Validation), replacing **GKE Autopilot** with **Chameleon Cloud** (`chameleoncloud.org`).

### A. Comparison Table

| Aspect | GKE / GKE Autopilot | Chameleon Cloud |
| :--- | :--- | :--- |
| **Control Plane Access** | **Restricted / Blocked:** Autopilot blocks customization of control plane schedulers and system binaries. | **Absolute Access:** Bare-metal access allows running custom `kube-scheduler` binaries natively via `kubeadm`/`k3s`. |
| **Cluster Cost** | **Very Expensive:** GPU pools average $6+/hour (T4, V100, A100 nodes + management fees). | **Free:** NSF-funded computer systems research testbed (no credit cards or billing profiles). |
| **Telemetry Access** | Virtualized hypervisor layer hides low-level hardware metrics. | Physical bare-metal nodes allow direct GPU and OS kernel telemetry. |
| **Setup Overhead** | Low (managed via Terraform/gcloud). | Medium (requires manual OS installation, `kubeadm` init, and cluster joins). |

### B. Action Plan for Chameleon Cloud Migration
1. **Submit Research Project Proposal:** Request access to the "Explore" tier with a short CS research abstract.
2. **Provision Bare-Metal Nodes:** Request at least 1 master node and 3 worker nodes (including GPU nodes).
3. **Initialize Cluster:** Deploy Kubernetes (`kubeadm` or lightweight `k3s`).
4. **Deploy Custom Scheduler Control Plane:** Replace default scheduler configurations with the custom Go scheduler plugin and run the Python telemetry daemon.
5. **Re-run Workload Trace:** Verify the validation suite on physical bare metal.
