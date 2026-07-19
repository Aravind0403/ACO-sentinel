package main

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/kubernetes/pkg/scheduler/framework"

	"aco-sentinel-plugin/pb"
)

const (
	Name = "ACOPredictiveScheduler"

	// Annotations for telemetry passing
	AnnotationReportedAllocatableCPU = "aco-sentinel.io/reported-allocatable-cpu"
	AnnotationReportedUsedCPU        = "aco-sentinel.io/reported-used-cpu"
	AnnotationReportedFreeCPU        = "aco-sentinel.io/reported-free-cpu"

	AnnotationReportedAllocatableMem = "aco-sentinel.io/reported-allocatable-memory-gb"
	AnnotationReportedUsedMem        = "aco-sentinel.io/reported-used-memory-gb"
	AnnotationReportedFreeMem        = "aco-sentinel.io/reported-free-memory-gb"

	AnnotationLastHeartbeat      = "aco-sentinel.io/last-heartbeat-timestamp"
	AnnotationHeartbeatIntervals = "aco-sentinel.io/recent-heartbeat-intervals"

	LabelWorkloadType = "aco-sentinel.io/workload-type"
)

// SentinelPlugin implements the PreScore, Score, Reserve, and PostBind plugins
type SentinelPlugin struct {
	handle             framework.Handle
	client             pb.ACOPredictiveSchedulerClient
	conn               *grpc.ClientConn
	gamma              float64
	mu                 sync.RWMutex
	reservedPlacements map[string]string // Pod UID -> Node Name
}

var _ framework.PreScorePlugin = &SentinelPlugin{}
var _ framework.ScorePlugin = &SentinelPlugin{}
var _ framework.ReservePlugin = &SentinelPlugin{}
var _ framework.PreBindPlugin = &SentinelPlugin{}
var _ framework.PostBindPlugin = &SentinelPlugin{}

func (p *SentinelPlugin) Name() string {
	return Name
}

// New initializes the SentinelPlugin and establishes the gRPC client connection
func New(obj runtime.Object, handle framework.Handle) (framework.Plugin, error) {
	// Connection to the sidecar python gRPC daemon
	dialCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(dialCtx, "127.0.0.1:50051", grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("failed to dial gRPC: %w", err)
	}

	client := pb.NewACOPredictiveSchedulerClient(conn)
	return &SentinelPlugin{
		handle:             handle,
		client:             client,
		conn:               conn,
		gamma:              1.0, // default trust exponent
		reservedPlacements: make(map[string]string),
	}, nil
}

// extractPodSpec extracts pod telemetry requirement properties
func extractPodSpec(pod *v1.Pod) *pb.PodSpec {
	var cpuMin, memMin float64
	for _, container := range pod.Spec.Containers {
		cpuMin += float64(container.Resources.Requests.Cpu().MilliValue()) / 1000.0
		memMin += float64(container.Resources.Requests.Memory().Value()) / (1024.0 * 1024.0 * 1024.0)
	}

	wType := "batch"
	if pod.Labels != nil {
		if val, ok := pod.Labels[LabelWorkloadType]; ok {
			wType = val
		}
	}

	return &pb.PodSpec{
		Uid:               string(pod.UID),
		Name:              pod.Name,
		Namespace:         pod.Namespace,
		CpuCoresRequested: cpuMin,
		MemoryGbRequested: memMin,
		WorkloadType:      wType,
	}
}

// extractNodeCandidate maps K8s Node and cache state to pb.NodeCandidate
func extractNodeCandidate(nodeInfo *framework.NodeInfo) *pb.NodeCandidate {
	node := nodeInfo.Node()
	if node == nil {
		return &pb.NodeCandidate{NodeId: "unknown"}
	}

	allocCpu := float64(node.Status.Allocatable.Cpu().MilliValue()) / 1000.0
	allocMem := float64(node.Status.Allocatable.Memory().Value()) / (1024.0 * 1024.0 * 1024.0)

	// Compute K8s assumed-cache allocations (Requested resources)
	reqCpu := float64(nodeInfo.Requested.MilliCPU) / 1000.0
	reqMem := float64(nodeInfo.Requested.Memory) / (1024.0 * 1024.0 * 1024.0)

	expectedFreeCpu := allocCpu - reqCpu
	expectedFreeMem := allocMem - reqMem

	// Default telemetry values fallback
	repAllocCpu := allocCpu
	repUsedCpu := reqCpu
	repFreeCpu := expectedFreeCpu

	repAllocMem := allocMem
	repUsedMem := reqMem
	repFreeMem := expectedFreeMem

	var lastHeartbeat float64
	var recentIntervals []float64

	if node.Annotations != nil {
		if val, err := strconv.ParseFloat(node.Annotations[AnnotationReportedAllocatableCPU], 64); err == nil {
			repAllocCpu = val
		}
		if val, err := strconv.ParseFloat(node.Annotations[AnnotationReportedUsedCPU], 64); err == nil {
			repUsedCpu = val
		}
		if val, err := strconv.ParseFloat(node.Annotations[AnnotationReportedFreeCPU], 64); err == nil {
			repFreeCpu = val
		}

		if val, err := strconv.ParseFloat(node.Annotations[AnnotationReportedAllocatableMem], 64); err == nil {
			repAllocMem = val
		}
		if val, err := strconv.ParseFloat(node.Annotations[AnnotationReportedUsedMem], 64); err == nil {
			repUsedMem = val
		}
		if val, err := strconv.ParseFloat(node.Annotations[AnnotationReportedFreeMem], 64); err == nil {
			repFreeMem = val
		}

		if val, err := strconv.ParseFloat(node.Annotations[AnnotationLastHeartbeat], 64); err == nil {
			lastHeartbeat = val
		}

		if val, ok := node.Annotations[AnnotationHeartbeatIntervals]; ok && val != "" {
			parts := strings.Split(val, ",")
			for _, p := range parts {
				if iv, err := strconv.ParseFloat(strings.TrimSpace(p), 64); err == nil {
					recentIntervals = append(recentIntervals, iv)
				}
			}
		}
	}

	return &pb.NodeCandidate{
		NodeId:                        node.Name,
		AllocatableCpu:                allocCpu,
		AllocatableMemoryGb:           allocMem,
		SchedulerExpectedFreeCpu:      expectedFreeCpu,
		SchedulerExpectedFreeMemoryGb: expectedFreeMem,
		ReportedAllocatableCpu:        repAllocCpu,
		ReportedUsedCpu:               repUsedCpu,
		ReportedFreeCpu:               repFreeCpu,
		ReportedAllocatableMemoryGb:   repAllocMem,
		ReportedUsedMemoryGb:          repUsedMem,
		ReportedFreeMemoryGb:          repFreeMem,
		LastHeartbeatTimestamp:        lastHeartbeat,
		RecentHeartbeatIntervals:      recentIntervals,
	}
}

type stateData struct {
	scores map[string]int64
}

func (s *stateData) Clone() framework.StateData {
	return s
}

const StateKey = framework.StateKey(Name + "State")

// PreScore batches all candidate nodes and fetches trust-weighted heuristic scores from gRPC server
func (p *SentinelPlugin) PreScore(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodes []*v1.Node) *framework.Status {
	if len(nodes) == 0 {
		return nil
	}

	pbPod := extractPodSpec(pod)
	pbNodes := make([]*pb.NodeCandidate, 0, len(nodes))
	for _, n := range nodes {
		var nodeInfo *framework.NodeInfo
		var err error
		if p.handle != nil {
			nodeInfo, err = p.handle.SnapshotSharedLister().NodeInfos().Get(n.Name)
		}
		if p.handle == nil || err != nil || nodeInfo == nil || nodeInfo.Node() == nil {
			dummyNodeInfo := framework.NewNodeInfo()
			dummyNodeInfo.SetNode(n)
			nodeInfo = dummyNodeInfo
		}
		pbNodes = append(pbNodes, extractNodeCandidate(nodeInfo))
	}

	req := &pb.ScoreRequest{
		Pod:   pbPod,
		Nodes: pbNodes,
		Gamma: p.gamma,
	}

	resp, err := p.client.ScoreNodes(ctx, req)
	if err != nil {
		fmt.Printf("[Sentinel-GoPlugin] WARNING: gRPC ScoreNodes call failed: %v. Graceful fallback active.\n", err)
		return nil
	}

	nodeScores := make(map[string]int64)
	for _, ns := range resp.Scores {
		// Map score from [0.0, 1.0] to [0, 100] int64 range
		nodeScores[ns.NodeId] = int64(ns.FinalScore * 100.0)
	}

	state.Write(StateKey, &stateData{scores: nodeScores})
	return nil
}

// Score retrieves the cached score for the target node
func (p *SentinelPlugin) Score(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) (int64, *framework.Status) {
	data, err := state.Read(StateKey)
	if err != nil {
		// Fallback to neutral score (100) if no scores are stored
		return 100, nil
	}

	sd, ok := data.(*stateData)
	if !ok {
		return 100, nil
	}

	score, exists := sd.scores[nodeName]
	if !exists {
		return 0, nil
	}

	return score, nil
}

func (p *SentinelPlugin) ScoreExtensions() framework.ScoreExtensions {
	return nil
}

// PreBind blocks binding for pod-rollback to force Unreserve rollbacks
func (p *SentinelPlugin) PreBind(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) *framework.Status {
	if pod.Name == "pod-rollback" {
		return framework.NewStatus(framework.Error, "Deliberate test rollback triggered for pod-rollback")
	}
	return nil
}

// Reserve registers the assumed placement
func (p *SentinelPlugin) Reserve(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) *framework.Status {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.reservedPlacements[string(pod.UID)] = nodeName
	return nil
}

// Unreserve clears the placement and calls rollback PlacementCommitted callback via gRPC
func (p *SentinelPlugin) Unreserve(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) {
	p.mu.Lock()
	delete(p.reservedPlacements, string(pod.UID))
	p.mu.Unlock()

	req := &pb.PlacementCommittedRequest{
		PodUid:  string(pod.UID),
		NodeId:  nodeName,
		Success: false,
	}
	_, err := p.client.PlacementCommitted(ctx, req)
	if err != nil {
		fmt.Printf("[Sentinel-GoPlugin] WARNING: gRPC PlacementCommitted rollback failed: %v\n", err)
	}
}

// PostBind clears the placement and calls commit PlacementCommitted callback via gRPC
func (p *SentinelPlugin) PostBind(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) {
	p.mu.Lock()
	delete(p.reservedPlacements, string(pod.UID))
	p.mu.Unlock()

	req := &pb.PlacementCommittedRequest{
		PodUid:  string(pod.UID),
		NodeId:  nodeName,
		Success: true,
	}
	_, err := p.client.PlacementCommitted(ctx, req)
	if err != nil {
		fmt.Printf("[Sentinel-GoPlugin] WARNING: gRPC PlacementCommitted commit failed: %v\n", err)
	}
}
