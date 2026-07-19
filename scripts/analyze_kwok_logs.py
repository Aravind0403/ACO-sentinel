#!/usr/bin/env python3
import re
import os
import matplotlib.pyplot as plt
import numpy as np

def analyze_logs():
    log_path = "grpc_server.log"
    if not os.path.exists(log_path):
        print(f"Error: Log file {log_path} not found.")
        return

    # Count templates
    # [Sentinel-Server] COMMIT: Pheromone deposit confirmed on node node-safe-cheap for pod ...
    # [Sentinel-Server] ROLLBACK: Bind failed or unreserved for pod ... on node node-safe-cheap. Rollback triggered.
    commit_pat = re.compile(r"\[Sentinel-Server\] COMMIT: Pheromone deposit confirmed on node ([a-zA-Z0-9_-]+) for pod")
    rollback_pat = re.compile(r"\[Sentinel-Server\] ROLLBACK: Bind failed or unreserved for pod [a-zA-Z0-9_-]+ on node ([a-zA-Z0-9_-]+)\. Rollback triggered\.")

    nodes = ["node-safe-cheap", "node-safe-expensive", "node-adversarial", "node-flapping"]
    stats = {node: {"commits": 0, "rollbacks": 0} for node in nodes}

    with open(log_path, "r") as f:
        for line in f:
            commit_match = commit_pat.search(line)
            if commit_match:
                node = commit_match.group(1)
                if node in stats:
                    stats[node]["commits"] += 1
            
            rollback_match = rollback_pat.search(line)
            if rollback_match:
                node = rollback_match.group(1)
                if node in stats:
                    stats[node]["rollbacks"] += 1

    print("\n==================================================")
    print("KWOK REAL-TIME VALIDATION ANALYSIS RESULTS")
    print("==================================================")
    for node, count in stats.items():
        print(f"Node: {node}")
        print(f"  - Successful Commits:  {count['commits']}")
        print(f"  - Aborted Rollbacks:   {count['rollbacks']}")
    print("==================================================")

    # Plot results
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(nodes))
    width = 0.35

    commits_list = [stats[node]["commits"] for node in nodes]
    rollbacks_list = [stats[node]["rollbacks"] for node in nodes]

    rects1 = ax.bar(x - width/2, commits_list, width, label='Commits (PostBind)', color='#4CAF50')
    rects2 = ax.bar(x + width/2, rollbacks_list, width, label='Rollbacks (Unreserve)', color='#F44336')

    ax.set_ylabel('Count of Transactions')
    ax.set_title('Scheduler Framework Parity: Commits vs Rollbacks on KWOK')
    ax.set_xticks(x)
    ax.set_xticklabels(nodes)
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    # Attach a text label above each bar in rects
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom')

    autolabel(rects1)
    autolabel(rects2)

    os.makedirs("docs", exist_ok=True)
    output_path = "docs/kwok-validation.png"
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"✅ Success: Generated KWOK validation report plot saved to {output_path}")

if __name__ == "__main__":
    analyze_logs()
