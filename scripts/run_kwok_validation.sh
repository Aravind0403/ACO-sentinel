#!/usr/bin/env bash
# scripts/run_kwok_validation.sh
#
# One-button script to run real-time custom scheduler validation on KWOK.
# Verifies trust-weighted routing, ResourceQuota bind failures, and Unreserve rollbacks.

set -eo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Ensure output files are clean
rm -f grpc_server.log scheduler.log k8s/v2-scheduler-config-local.yaml

echo "=================================================="
echo "ACO-SENTINEL: REAL-TIME KWOK CLUSTER VALIDATION"
echo "=================================================="

# ── 1. Check Dependencies ────────────────────────────────────────────────────
echo "==> Checking dependencies..."
if ! command -v kwokctl &> /dev/null; then
    echo "    KWOK not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install kwok
    else
        echo "    Error: Homebrew not found. Please install KWOK manually."
        exit 1
    fi
fi
echo "    KWOK OK."

# ── 2. Re-create Cluster ─────────────────────────────────────────────────────
echo "==> Creating virtual KWOK cluster 'aco-validation'..."
kwokctl delete cluster --name aco-validation || true
kwokctl create cluster --name aco-validation --wait 60s

# Point kubectl and scheduler to the local cluster
kwokctl get kubeconfig --name aco-validation > aco-validation-kubeconfig.yaml
KUBECONFIG_PATH="$(pwd)/aco-validation-kubeconfig.yaml"
export KUBECONFIG="$KUBECONFIG_PATH"
echo "    Cluster ready. KUBECONFIG set to: $KUBECONFIG_PATH"

# ── 3. Apply Simulated Nodes & ResourceQuota ─────────────────────────────────
echo "==> Provisioning virtual nodes..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Node
metadata:
  name: node-safe-cheap
  labels:
    type: kwok
    aco-sentinel.io/reported-allocatable-cpu: "16.0"
spec: {}
---
apiVersion: v1
kind: Node
metadata:
  name: node-safe-expensive
  labels:
    type: kwok
    aco-sentinel.io/reported-allocatable-cpu: "32.0"
spec: {}
---
apiVersion: v1
kind: Node
metadata:
  name: node-adversarial
  labels:
    type: kwok
    aco-sentinel.io/reported-allocatable-cpu: "16.0"
spec: {}
---
apiVersion: v1
kind: Node
metadata:
  name: node-flapping
  labels:
    type: kwok
    aco-sentinel.io/reported-allocatable-cpu: "16.0"
spec: {}
EOF

echo "==> Applying ResourceQuota of 20 CPU cores..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ResourceQuota
metadata:
  name: cpu-quota
  namespace: default
spec:
  hard:
    cpu: "20"
EOF

# ── 4. Generate Scheduler Config ─────────────────────────────────────────────
echo "==> Generating local scheduler configuration..."
cat <<EOF > k8s/v2-scheduler-config-local.yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
leaderElection:
  leaderElect: false
clientConnection:
  kubeconfig: $KUBECONFIG
profiles:
  - schedulerName: aco-sentinel-scheduler
    plugins:
      preScore:
        enabled:
          - name: ACOPredictiveScheduler
      score:
        enabled:
          - name: ACOPredictiveScheduler
            weight: 100
      reserve:
        enabled:
          - name: ACOPredictiveScheduler
      preBind:
        enabled:
          - name: ACOPredictiveScheduler
      postBind:
        enabled:
          - name: ACOPredictiveScheduler
EOF

# ── 5. Start Background Daemons ──────────────────────────────────────────────
_pids=()
cleanup() {
    echo ""
    echo "==> Cleaning up background daemons and clusters..."
    for pid in "${_pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    kwokctl delete cluster --name aco-validation || true
    rm -f aco-validation-kubeconfig.yaml k8s/v2-scheduler-config-local.yaml
    echo "    Cleanup completed."
}
trap cleanup EXIT INT TERM

echo "==> Starting Python gRPC daemon..."
python3 -u v2/grpc_server.py > grpc_server.log 2>&1 &
_pids+=($!)

echo "==> Starting Python node telemetry agent..."
python3 -u scripts/kwok_telemetry_agent.py > telemetry_agent.log 2>&1 &
_pids+=($!)

echo "==> Starting custom Go Scheduler plugin..."
./v2/go_plugin/kube-scheduler --config=k8s/v2-scheduler-config-local.yaml --v=2 > scheduler.log 2>&1 &
_pids+=($!)

# Wait for components to bind
echo "==> Waiting for scheduler components to initialize..."
sleep 5

# ── 6. Inject Workloads & Verify Rollbacks ───────────────────────────────────
echo "==> Phase A: Submitting 10 pods (2 CPU cores each, 8Gi memory) to fill the ResourceQuota..."
for i in {1..10}; do
  kubectl run "pod-$i" --image=nginx --overrides='{"spec": {"schedulerName": "aco-sentinel-scheduler", "containers": [{"name": "nginx", "image": "nginx", "resources": {"requests": {"cpu": "2", "memory": "8Gi"}}}]}}'
  sleep 0.5
done

echo "==> Waiting for Phase A bindings to settle..."
sleep 5
echo "    Current Pod Statuses:"
kubectl get pods -o wide

echo "==> Phase B: Submitting 2 additional pods (which exceed the 20 CPU ResourceQuota)..."
for i in {11..12}; do
  kubectl run "pod-$i" --image=nginx --overrides='{"spec": {"schedulerName": "aco-sentinel-scheduler", "containers": [{"name": "nginx", "image": "nginx", "resources": {"requests": {"cpu": "2", "memory": "8Gi"}}}]}}' || true
  sleep 0.5
done

echo "==> Waiting for API admission failures to trigger rollbacks..."
sleep 5
echo "    Current Pod Statuses (pods 11 and 12 should be Failed/Pending):"
kubectl get pods -o wide

echo "==> Phase C: Deleting 2 running pods to free up 4 CPU cores..."
kubectl delete pod pod-1 pod-2 --wait=false
sleep 2

echo "==> Phase D: Submitting 2 recovery pods to verify scheduling resumes..."
for i in {13..14}; do
  kubectl run "pod-$i" --image=nginx --overrides='{"spec": {"schedulerName": "aco-sentinel-scheduler", "containers": [{"name": "nginx", "image": "nginx", "resources": {"requests": {"cpu": "2", "memory": "8Gi"}}}]}}'
  sleep 0.5
done

echo "==> Waiting for Phase D scheduling..."
sleep 5
echo "    Final Pod Statuses:"
kubectl get pods -o wide

echo "==> Phase E: Deleting pod-3 to free up quota, then submitting pod-rollback and immediately deleting it to force a scheduler Bind failure..."
kubectl delete pod pod-3 --wait=false
sleep 2
kubectl run "pod-rollback" --image=nginx --overrides='{"spec": {"schedulerName": "aco-sentinel-scheduler", "containers": [{"name": "nginx", "image": "nginx", "resources": {"requests": {"cpu": "2", "memory": "8Gi"}}}]}}' &
sleep 0.05
kubectl delete pod "pod-rollback" --grace-period=0 --force || true
sleep 3

# ── 7. Compile Report and Plot ───────────────────────────────────────────────
echo "==> Stopping background daemons to flush logs..."
for pid in "${_pids[@]}"; do
    kill "$pid" 2>/dev/null || true
done
# Remove from list so trap doesn't try to double-kill
_pids=()

echo "==> Generating validation report and analysis plots..."
python3 scripts/analyze_kwok_logs.py

echo "==> Validation run finished successfully!"
