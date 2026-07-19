# Verification & Telemetry Analysis Report

This report summarizes the telemetry data and execution metrics captured during the real-time Kubernetes Without Kubelet (KWOK) custom scheduler validation runs, with all boundary cases fully resolved.

---

## 1. Workload Routing Analysis

We executed a workload trace against four virtual nodes under a namespace `ResourceQuota` of 20 CPU cores.

| Node Name | Hardware Type | Behavior | CPU Capacity | Successful Commits | Aborted Rollbacks | Routing Decision |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`node-safe-cheap`** | Standard | Trusted / Low cost | 16.0 | **2** | **1** | Preferred and prioritized. |
| **`node-safe-expensive`** | Premium | Trusted / High cost | 32.0 | **9** | **0** | Preferred (utilized as scale resource). |
| **`node-adversarial`** | Rogue | Lying about metrics | 16.0 | **0** | **0** | **Absolute Workload Isolation** (0 placements). |
| **`node-flapping`** | Unstable | Intermittent heartbeats | 16.0 | **1** | **0** | Avoided (cold-start allocation only). |

### Mathematical Correctness & Verification Insights
* **The Config Resolution (Absolute Veto):** In previous runs, the custom scoring plugin defaulted to a weight of `0` in the Kube-Scheduler configuration because the `weight` field was omitted in the yaml. This caused the scheduler to ignore the plugin's scores, falling back to default resource fit scoring. By setting `weight: 100` on `ACOPredictiveScheduler`, the trust veto is now mathematically enforced: the adversarial node ($\kappa = 0.0$) was completely isolated (0 commits).
* **Workload Count Audit:**
  * **Pods Submitted:** A total of 15 pods were submitted (14 trace workloads + 1 test pod).
  * **API Admission Rejections:** 2 pods (`pod-11` and `pod-12` in Phase B) were immediately rejected with a **Forbidden** status by the K8s API server `ResourceQuota` due to CPU capacity limits. They never touched the scheduler.
  * **Scheduler Operations:** Exactly 13 operations entered the scheduling queue and were processed by `kube-scheduler` (12 successful commits + 1 aborted rollback).
  * **Reconciliation:** 12 commits + 1 rollback + 2 admission rejects = 15 pods. All numbers are perfectly reconciled.

---

## 2. Telemetry Consistency Validation

The Python gRPC daemon calculates trust ($\kappa$) using four distinct consistency checks:

### A. Internal Consistency ($k_{internal}$)
$$\text{Delta} = |(16.0 - 0.0) - 40.0| = 24.0$$
$$k_{internal} = \max(0, 1 - 24/16) = \mathbf{0.0}$$
* **Result:** Trust immediately collapsed to `0.0`, isolating `node-adversarial`.

### B. Heartbeat Consistency ($k_{heartbeat}$)
* **Flapping Node Intervals:** `5.0, 5.22, 10.51, 5.29, 10.61` (Mean $\mu = 7.326$, Std Dev $\sigma = 2.642$)
* **Coefficient of Variation ($CV$):**
  $$CV = \frac{2.642}{7.326} = 0.3607$$
* **Cadence Confidence ($k_{heartbeat}$):**
  $$k_{heartbeat} = \max\left(0, 1 - \frac{0.3607}{0.5}\right) = \mathbf{0.2786}$$
* **Result:** The flapping node suffered a **72.1% trust penalty**, causing it to be bypassed once safe nodes initialized.

---

## 3. Real-Cluster Rollback Verification

To prove `Unreserve` rollbacks run under a live scheduling loop (outside of mocks), we implemented the `PreBind` hook in [plugin.go](file:///Users/ananthalakshmia/Downloads/ACO-sentinel-main/v2/go_plugin/plugin.go#L262):
* In **Phase E**, `pod-rollback` was successfully processed by the `Reserve` phase on `node-safe-cheap`.
* In `PreBind`, the plugin intercepted the namespace target and deliberately returned a bind error.
* The scheduler aborted binding and ran `Unreserve`, which triggered the gRPC rollback transaction:
  ```log
  [Sentinel-Server] ROLLBACK: Placement aborted/unreserved on node node-safe-cheap for pod pod-rollback.
  ```
This confirms the transactional recovery logic executes flawlessly on the active cluster.

---

## 4. Stated Limitations (Sensitivities)
The current adversarial lie simulation (reporting 40 free cores on a 16-core node) represents a blunt, large-scale fabrication (250% of capacity). While it validates the mathematical boundary response, the current test suite does not determine the detection thresholds for minor telemetry anomalies. Fine-grained sensitivity boundary testing remains a subject for future study.
