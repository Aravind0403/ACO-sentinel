package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"aco-sentinel-plugin/pb"
)

type NodeSimState struct {
	nodeID           string
	allocatableCPU   float64
	allocatableMem   float64
	currentAllocated float64
}

type SimulationResult struct {
	Placements        map[string]int      `json:"placements"`
	ConfidenceHistory map[string][]float64 `json:"confidence_history"`
}

type ExperimentResults struct {
	GammaResults map[string]*SimulationResult `json:"gamma_results"`
}

func main() {
	fmt.Println("==================================================")
	fmt.Println("ACO-SENTINEL: GO SIMULATION HARNESS & EXPERIMENTS")
	fmt.Println("==================================================")

	// Set up gRPC client
	conn, err := grpc.Dial("localhost:50051", grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		fmt.Printf("Error: Failed to connect to gRPC server: %v\n", err)
		os.Exit(1)
	}
	defer conn.Close()
	client := pb.NewACOPredictiveSchedulerClient(conn)

	gammas := []float64{0.0, 0.5, 1.0, 2.0, 4.0}
	results := &ExperimentResults{
		GammaResults: make(map[string]*SimulationResult),
	}

	for _, gamma := range gammas {
		fmt.Printf("\n--- Running simulation for Gamma = %.1f ---\n", gamma)

		// 1. Reset gRPC server trackers
		_, err := client.ScoreNodes(context.Background(), &pb.ScoreRequest{
			Pod: &pb.PodSpec{Uid: "reset", WorkloadType: "batch"},
		})
		if err != nil {
			fmt.Printf("Error: Failed to reset server trackers: %v\n", err)
			continue
		}

		// 2. Initialize simulated node states
		nodes := []*NodeSimState{
			{nodeID: "node-safe-cheap", allocatableCPU: 16.0, allocatableMem: 64.0},
			{nodeID: "node-safe-expensive", allocatableCPU: 32.0, allocatableMem: 128.0},
			{nodeID: "node-adversarial", allocatableCPU: 16.0, allocatableMem: 64.0},
			{nodeID: "node-flapping", allocatableCPU: 16.0, allocatableMem: 64.0},
		}

		placements := make(map[string]int)
		for _, n := range nodes {
			placements[n.nodeID] = 0
		}

		confHistory := make(map[string][]float64)
		for _, n := range nodes {
			confHistory[n.nodeID] = make([]float64, 0)
		}

		// Track pod release schedule: releaseTick -> list of (node, cpu)
		podReleases := make(map[int][]*NodeSimState)

		// Seed local RNG for reproducibility
		rng := rand.New(rand.NewSource(42))

		// 100 simulation ticks
		totalTicks := 100
		for tick := 1; tick <= totalTicks; tick++ {
			currentTime := float64(tick) * 5.0

			// Release resources of finished pods
			if releases, exists := podReleases[tick]; exists {
				for _, n := range releases {
					n.currentAllocated -= 2.0
					if n.currentAllocated < 0 {
						n.currentAllocated = 0
					}
				}
				delete(podReleases, tick)
			}

			// Generate Pod spec requesting 2 CPU and 8 GB RAM
			podUID := fmt.Sprintf("pod-g%.1f-t%d", gamma, tick)
			pbPod := &pb.PodSpec{
				Uid:               podUID,
				Name:              fmt.Sprintf("pod-%d", tick),
				Namespace:         "default",
				CpuCoresRequested: 2.0,
				MemoryGbRequested: 8.0,
				WorkloadType:      "batch",
			}

			// Prepare node candidates
			pbNodes := []*pb.NodeCandidate{}
			for _, n := range nodes {
				candidate := buildNodeCandidate(n, currentTime, tick)
				pbNodes = append(pbNodes, candidate)
			}

			// Call ScoreNodes
			req := &pb.ScoreRequest{
				Pod:   pbPod,
				Nodes: pbNodes,
				Gamma: gamma,
			}

			resp, err := client.ScoreNodes(context.Background(), req)
			if err != nil {
				fmt.Printf("Tick %d: ScoreNodes RPC failed: %v\n", tick, err)
				continue
			}

			// Select node via Roulette-wheel selection
			selectedNode := selectNode(nodes, resp.Scores, rng)
			if selectedNode == nil {
				// Cluster full / no node fits
				continue
			}

			// Record placement
			placements[selectedNode.nodeID]++
			selectedNode.currentAllocated += 2.0

			// Schedule pod release in 5 ticks (25 seconds)
			releaseTick := tick + 5
			podReleases[releaseTick] = append(podReleases[releaseTick], selectedNode)

			// Record confidences returned in ScoreResponse
			for _, ns := range resp.Scores {
				confHistory[ns.NodeId] = append(confHistory[ns.NodeId], ns.Confidence)
			}

			// Commit placement via gRPC callback
			_, err = client.PlacementCommitted(context.Background(), &pb.PlacementCommittedRequest{
				PodUid:  podUID,
				NodeId:  selectedNode.nodeID,
				Success: true,
			})
			if err != nil {
				fmt.Printf("Tick %d: PlacementCommitted commit failed: %v\n", tick, err)
			}
		}

		results.GammaResults[fmt.Sprintf("%.1f", gamma)] = &SimulationResult{
			Placements:        placements,
			ConfidenceHistory: confHistory,
		}

		fmt.Printf("Completed. Placements results:\n")
		for k, v := range placements {
			fmt.Printf("  - %s: %d pods\n", k, v)
		}
	}

	// Write results to JSON
	outputDir := "/Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront/docs"
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		fmt.Printf("Error: Failed to create output directory: %v\n", err)
		os.Exit(1)
	}

	outputPath := filepath.Join(outputDir, "experiment_results.json")
	bytes, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		fmt.Printf("Error: Failed to marshal results to JSON: %v\n", err)
		os.Exit(1)
	}

	if err := os.WriteFile(outputPath, bytes, 0644); err != nil {
		fmt.Printf("Error: Failed to write JSON file: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("\n✅ Success: Simulation results written to %s\n", outputPath)
}

func buildNodeCandidate(n *NodeSimState, currentTime float64, tick int) *pb.NodeCandidate {
	expectedFreeCPU := n.allocatableCPU - n.currentAllocated
	expectedFreeMem := n.allocatableMem - (n.currentAllocated * 4.0)

	// Base defaults matching a healthy node
	repAllocCPU := n.allocatableCPU
	repUsedCPU := n.currentAllocated
	repFreeCPU := expectedFreeCPU

	repAllocMem := n.allocatableMem
	repUsedMem := n.currentAllocated * 4.0
	repFreeMem := expectedFreeMem

	lastHeartbeat := currentTime
	var recentIntervals []float64

	switch n.nodeID {
	case "node-safe-cheap", "node-safe-expensive":
		// Perfect heartbeat history
		recentIntervals = []float64{5.0, 5.0, 5.0, 5.0, 5.0, 5.0}

	case "node-adversarial":
		// Lying: reports 0 used CPU and 40.0 free CPU (internal consistency error)
		repAllocCPU = 16.0
		repUsedCPU = 0.0
		repFreeCPU = 40.0 // Liar: Free > Allocatable, trips k_internal

		// Heartbeats arrive on time (regular heartbeats, not silent)
		lastHeartbeat = currentTime
		recentIntervals = []float64{5.0, 5.0, 5.0, 5.0, 5.0, 5.0}

	case "node-flapping":
		// Erratic cadence: alternates between 1s and 9s
		flappingIntervals := []float64{1.0, 9.0, 1.0, 9.0, 2.0, 8.0}
		recentIntervals = flappingIntervals
	}

	return &pb.NodeCandidate{
		NodeId:                        n.nodeID,
		AllocatableCpu:                n.allocatableCPU,
		AllocatableMemoryGb:           n.allocatableMem,
		SchedulerExpectedFreeCpu:      expectedFreeCPU,
		SchedulerExpectedFreeMemoryGb: expectedFreeMem,
		ReportedAllocatableCpu:        repAllocCPU,
		ReportedUsedCpu:               repUsedCPU,
		ReportedFreeCpu:               repFreeCPU,
		ReportedAllocatableMemoryGb:   repAllocMem,
		ReportedUsedMemoryGb:          repUsedMem,
		ReportedFreeMemoryGb:          repFreeMem,
		LastHeartbeatTimestamp:        lastHeartbeat,
		RecentHeartbeatIntervals:      recentIntervals,
	}
}

func selectNode(nodes []*NodeSimState, scores []*pb.NodeScore, rng *rand.Rand) *NodeSimState {
	// Create a map of node scores for easy access
	scoreMap := make(map[string]float64)
	for _, s := range scores {
		scoreMap[s.NodeId] = s.FinalScore
	}

	// Filter nodes that can fit the pod (requires at least 2 CPU cores)
	candidates := []*NodeSimState{}
	totalScore := 0.0

	for _, n := range nodes {
		expectedFreeCPU := n.allocatableCPU - n.currentAllocated
		if expectedFreeCPU >= 2.0 {
			candidates = append(candidates, n)
			totalScore += scoreMap[n.nodeID]
		}
	}

	if len(candidates) == 0 {
		return nil
	}

	// If all candidate scores are zero, select the one with the highest free CPU capacity
	if totalScore == 0.0 {
		var bestNode *NodeSimState
		maxFree := -1.0
		for _, c := range candidates {
			free := c.allocatableCPU - c.currentAllocated
			if free > maxFree {
				maxFree = free
				bestNode = c
			}
		}
		return bestNode
	}

	// Roulette-wheel selection
	rVal := rng.Float64() * totalScore
	runningSum := 0.0
	for _, c := range candidates {
		runningSum += scoreMap[c.nodeID]
		if rVal <= runningSum {
			return c
		}
	}

	return candidates[len(candidates)-1]
}
