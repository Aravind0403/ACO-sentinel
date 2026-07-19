#!/usr/bin/env python3
import json
import subprocess
import time
import sys

def get_node_allocated_cpu(node_name):
    try:
        cmd = ["kubectl", "get", "pods", "-A", f"--field-selector=spec.nodeName={node_name}", "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if not result.stdout.strip():
            return 0.0
        pods_data = json.loads(result.stdout)
        total_cpu = 0.0
        for pod in pods_data.get("items", []):
            if pod.get("metadata", {}).get("deletionTimestamp"):
                continue
            # Only count pods in default namespace or scheduler pods
            for container in pod.get("spec", {}).get("containers", []):
                resources = container.get("resources", {})
                requests = resources.get("requests", {})
                cpu = requests.get("cpu", "0")
                if cpu.endswith("m"):
                    cpu_val = float(cpu[:-1]) / 1000.0
                else:
                    try:
                        cpu_val = float(cpu)
                    except ValueError:
                        cpu_val = 0.0
                total_cpu += cpu_val
        return total_cpu
    except Exception:
        return 0.0

def annotate_node(node_name, annotations):
    anno_args = []
    for k, v in annotations.items():
        anno_args.append(f"{k}={v}")
    try:
        cmd = ["kubectl", "annotate", "node", node_name] + anno_args + ["--overwrite"]
        subprocess.run(cmd, capture_output=True, check=True)
    except Exception as e:
        print(f"Error annotating node {node_name}: {e}", file=sys.stderr)

def main():
    print("[Telemetry-Agent] Telemetry simulation agent started.")
    
    # Flapping state
    flapping_intervals = [1.0, 9.0, 1.0, 9.0, 2.0, 8.0]
    flapping_index = 0
    flapping_history = [5.0, 5.0, 5.0, 5.0, 5.0]
    last_flapping_heartbeat = time.time()

    while True:
        try:
            current_time = time.time()

            # 1. node-safe-cheap
            cpu_cheap = get_node_allocated_cpu("node-safe-cheap")
            annotate_node("node-safe-cheap", {
                "aco-sentinel.io/reported-allocatable-cpu": "16.0",
                "aco-sentinel.io/reported-used-cpu": f"{cpu_cheap:.2f}",
                "aco-sentinel.io/reported-free-cpu": f"{(16.0 - cpu_cheap):.2f}",
                "aco-sentinel.io/reported-allocatable-memory-gb": "64.0",
                "aco-sentinel.io/reported-used-memory-gb": f"{(cpu_cheap * 4.0):.2f}",
                "aco-sentinel.io/reported-free-memory-gb": f"{(64.0 - cpu_cheap * 4.0):.2f}",
                "aco-sentinel.io/last-heartbeat-timestamp": f"{current_time:.2f}",
                "aco-sentinel.io/recent-heartbeat-intervals": "5.0,5.0,5.0,5.0,5.0"
            })

            # 2. node-safe-expensive
            cpu_exp = get_node_allocated_cpu("node-safe-expensive")
            annotate_node("node-safe-expensive", {
                "aco-sentinel.io/reported-allocatable-cpu": "32.0",
                "aco-sentinel.io/reported-used-cpu": f"{cpu_exp:.2f}",
                "aco-sentinel.io/reported-free-cpu": f"{(32.0 - cpu_exp):.2f}",
                "aco-sentinel.io/reported-allocatable-memory-gb": "128.0",
                "aco-sentinel.io/reported-used-memory-gb": f"{(cpu_exp * 4.0):.2f}",
                "aco-sentinel.io/reported-free-memory-gb": f"{(128.0 - cpu_exp * 4.0):.2f}",
                "aco-sentinel.io/last-heartbeat-timestamp": f"{current_time:.2f}",
                "aco-sentinel.io/recent-heartbeat-intervals": "5.0,5.0,5.0,5.0,5.0"
            })

            # 3. node-adversarial (Lying: reports 0 used CPU and 40.0 free CPU)
            annotate_node("node-adversarial", {
                "aco-sentinel.io/reported-allocatable-cpu": "16.0",
                "aco-sentinel.io/reported-used-cpu": "0.00",
                "aco-sentinel.io/reported-free-cpu": "40.00",  # Liar: Free > Allocatable
                "aco-sentinel.io/reported-allocatable-memory-gb": "64.0",
                "aco-sentinel.io/reported-used-memory-gb": "0.00",
                "aco-sentinel.io/reported-free-memory-gb": "160.00", # Liar: Free > Allocatable
                "aco-sentinel.io/last-heartbeat-timestamp": f"{current_time:.2f}",
                "aco-sentinel.io/recent-heartbeat-intervals": "5.0,5.0,5.0,5.0,5.0"
            })

            # 4. node-flapping (Erratic intervals)
            elapsed = current_time - last_flapping_heartbeat
            next_interval = flapping_intervals[flapping_index]
            if elapsed >= next_interval:
                flapping_history.append(round(elapsed, 2))
                if len(flapping_history) > 5:
                    flapping_history.pop(0)
                flapping_intervals_str = ",".join(map(str, flapping_history))
                
                cpu_flap = get_node_allocated_cpu("node-flapping")
                annotate_node("node-flapping", {
                    "aco-sentinel.io/reported-allocatable-cpu": "16.0",
                    "aco-sentinel.io/reported-used-cpu": f"{cpu_flap:.2f}",
                    "aco-sentinel.io/reported-free-cpu": f"{(16.0 - cpu_flap):.2f}",
                    "aco-sentinel.io/reported-allocatable-memory-gb": "64.0",
                    "aco-sentinel.io/reported-used-memory-gb": f"{(cpu_flap * 4.0):.2f}",
                    "aco-sentinel.io/reported-free-memory-gb": f"{(64.0 - cpu_flap * 4.0):.2f}",
                    "aco-sentinel.io/last-heartbeat-timestamp": f"{current_time:.2f}",
                    "aco-sentinel.io/recent-heartbeat-intervals": flapping_intervals_str
                })
                
                last_flapping_heartbeat = current_time
                flapping_index = (flapping_index + 1) % len(flapping_intervals)

        except Exception as e:
            print(f"[Telemetry-Agent] Error in loop: {e}", file=sys.stderr)

        time.sleep(5.0)

if __name__ == "__main__":
    main()
