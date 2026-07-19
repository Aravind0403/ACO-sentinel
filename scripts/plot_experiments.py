import json
import os
import matplotlib.pyplot as plt
import numpy as np

def generate_plots():
    results_path = "docs/experiment_results.json"
    if not os.path.exists(results_path):
        print(f"Error: results file {results_path} not found.")
        return

    with open(results_path, "r") as f:
        data = json.load(f)

    gamma_results = data.get("gamma_results", {})
    gammas = sorted(list(gamma_results.keys()), key=float)
    nodes = ["node-safe-cheap", "node-safe-expensive", "node-adversarial", "node-flapping"]
    colors = ["#4CAF50", "#2196F3", "#F44336", "#FF9800"] # Green, Blue, Red, Orange

    # Prepare data for placements chart
    placements_data = {node: [] for node in nodes}
    for g in gammas:
        res = gamma_results[g]
        for node in nodes:
            placements_data[node].append(res["placements"].get(node, 0))

    # Set up matplotlib figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle("ACO-Sentinel V2: Trust-Weighted Routing & Telemetry Confidence Trajectories", fontsize=16, fontweight="bold", y=0.98)

    # 1. Bar Chart: Placements vs Gamma
    x = np.arange(len(gammas))
    width = 0.2

    for i, node in enumerate(nodes):
        bars = ax1.bar(x + (i - 1.5) * width, placements_data[node], width, label=node, color=colors[i])
        
        # Annotate exact 0 counts for adversarial/flapping nodes at higher gamma to show data is not missing
        if node in ["node-adversarial", "node-flapping"]:
            for bar in bars:
                height = bar.get_height()
                if height == 0:
                    ax1.text(
                        bar.get_x() + bar.get_width() / 2.0, 
                        1.0, 
                        "0", 
                        ha="center", 
                        va="bottom", 
                        fontsize=8, 
                        color="#777777", 
                        fontweight="bold"
                    )

    ax1.set_xlabel(r"Trust Sensitivity exponent ($\gamma$)", fontsize=12)
    ax1.set_ylabel("Total Pods Scheduled (out of 100)", fontsize=12)
    ax1.set_title(r"Workload Distribution vs. Trust Sensitivity ($\gamma$)", fontsize=13, pad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels([fr"$\gamma$ = {g}" for g in gammas])
    ax1.legend(loc="upper right")
    ax1.grid(axis="y", linestyle="--", alpha=0.7)

    # 2. Line Chart: Confidence Trajectory for gamma = 1.0 (with zoomed inset)
    g_target = "1.0"
    if g_target in gamma_results:
        res = gamma_results[g_target]
        history = res.get("confidence_history", {})
        ticks = np.arange(1, len(history.get(nodes[0], [])) + 1)
        
        # Plot main lines
        for i, node in enumerate(nodes):
            conf_values = history.get(node, [])
            ax2.plot(ticks, conf_values, label=f"{node}", color=colors[i], linewidth=2.5)

        ax2.set_xlabel("Simulation Steps (Ticks)", fontsize=12)
        ax2.set_ylabel(r"Smoothed Confidence Score ($\kappa$)", fontsize=12)
        ax2.set_title(fr"Confidence Trajectory over Time ($\gamma$ = {g_target})", fontsize=13, pad=10)
        ax2.set_ylim(-0.05, 1.05)
        ax2.legend(loc="lower left")
        ax2.grid(True, linestyle="--", alpha=0.7)

        # Zoomed Inset for bottom trajectories (adversarial vs flapping)
        # Position inset in upper-middle/right: [x_start, y_start, width, height] relative to ax2 dimensions
        axins = ax2.inset_axes([0.45, 0.45, 0.5, 0.5])
        
        # Plot the flapping and adversarial trajectories in the inset
        for i, node in enumerate(nodes):
            if node in ["node-adversarial", "node-flapping"]:
                conf_values = history.get(node, [])
                axins.plot(ticks, conf_values, color=colors[i], linewidth=2)
        
        # Zoom in on ticks 1 to 40 and y-range -0.02 to 0.52 to see details
        axins.set_xlim(1, 40)
        axins.set_ylim(-0.02, 0.52)
        axins.set_xticklabels([])  # Hide x-labels to avoid clutter
        axins.grid(True, linestyle=":", alpha=0.6)
        axins.set_title("Zoom: Lying vs Flapping", fontsize=9, pad=5, fontweight="bold")
        
        # Draw connections from ax2 to inset box
        ax2.indicate_inset_zoom(axins, edgecolor="black", alpha=0.3)
    else:
        ax2.text(0.5, 0.5, f"Data for Gamma={g_target} not found", ha="center", va="center")

    plt.tight_layout()
    output_path = "docs/v2-experiments.png"
    plt.savefig(output_path, dpi=150)
    print(f"✅ Success: Generated plots saved to {output_path}")

if __name__ == "__main__":
    generate_plots()
