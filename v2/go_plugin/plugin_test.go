package main

import (
	"context"
	"testing"

	grpc "google.golang.org/grpc"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	types "k8s.io/apimachinery/pkg/types"
	"k8s.io/kubernetes/pkg/scheduler/framework"

	"aco-sentinel-plugin/pb"
)

type mockClient struct {
	pb.ACOPredictiveSchedulerClient
	scoreNodesCalled bool
	commitCalled     bool
	lastSuccess      bool
}

func (m *mockClient) ScoreNodes(ctx context.Context, in *pb.ScoreRequest, opts ...grpc.CallOption) (*pb.ScoreResponse, error) {
	m.scoreNodesCalled = true
	var scores []*pb.NodeScore
	for _, n := range in.Nodes {
		scores = append(scores, &pb.NodeScore{
			NodeId:     n.NodeId,
			FinalScore: 0.85,
		})
	}
	return &pb.ScoreResponse{Scores: scores}, nil
}

func (m *mockClient) PlacementCommitted(ctx context.Context, in *pb.PlacementCommittedRequest, opts ...grpc.CallOption) (*pb.PlacementCommittedResponse, error) {
	m.commitCalled = true
	m.lastSuccess = in.Success
	return &pb.PlacementCommittedResponse{Acknowledged: true}, nil
}

func TestPlugin(t *testing.T) {
	// Test Pod extraction
	pod := &v1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-pod",
			Namespace: "default",
			UID:       types.UID("pod-123"),
			Labels: map[string]string{
				LabelWorkloadType: "batch",
			},
		},
		Spec: v1.PodSpec{
			Containers: []v1.Container{
				{
					Resources: v1.ResourceRequirements{
						Requests: v1.ResourceList{
							v1.ResourceCPU:    *resource.NewMilliQuantity(1000, resource.DecimalSI),
							v1.ResourceMemory: *resource.NewQuantity(1024*1024*1024, resource.BinarySI),
						},
					},
				},
			},
		},
	}

	podSpec := extractPodSpec(pod)
	if podSpec.Uid != "pod-123" || podSpec.WorkloadType != "batch" {
		t.Errorf("Unexpected podSpec properties: %+v", podSpec)
	}
	if podSpec.CpuCoresRequested != 1.0 || podSpec.MemoryGbRequested != 1.0 {
		t.Errorf("Unexpected resources in podSpec: CPU=%f, Mem=%f", podSpec.CpuCoresRequested, podSpec.MemoryGbRequested)
	}

	// Test Node Candidate extraction
	node := &v1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name: "node-1",
			Annotations: map[string]string{
				AnnotationReportedUsedCPU: "0.5",
			},
		},
	}
	node.Status.Allocatable = v1.ResourceList{
		v1.ResourceCPU:    *resource.NewMilliQuantity(2000, resource.DecimalSI),
		v1.ResourceMemory: *resource.NewQuantity(4*1024*1024*1024, resource.BinarySI),
	}

	nodeInfo := framework.NewNodeInfo()
	nodeInfo.SetNode(node)

	candidate := extractNodeCandidate(nodeInfo)
	if candidate.NodeId != "node-1" || candidate.AllocatableCpu != 2.0 || candidate.ReportedUsedCpu != 0.5 {
		t.Errorf("Unexpected candidate properties: %+v", candidate)
	}

	// Test Plugin Hooks with mock client
	mock := &mockClient{}
	plugin := &SentinelPlugin{
		client:             mock,
		gamma:              1.0,
		reservedPlacements: make(map[string]string),
	}

	state := framework.NewCycleState()
	status := plugin.PreScore(context.Background(), state, pod, []*framework.NodeInfo{nodeInfo})
	if status != nil && !status.IsSuccess() {
		t.Errorf("PreScore failed: %v", status)
	}

	if !mock.scoreNodesCalled {
		t.Errorf("Expected PreScore to call ScoreNodes gRPC endpoint")
	}

	score, scoreStatus := plugin.Score(context.Background(), state, pod, "node-1")
	if scoreStatus != nil && !scoreStatus.IsSuccess() {
		t.Errorf("Score failed: %v", scoreStatus)
	}
	if score != 85 {
		t.Errorf("Expected score to be 85 (0.85 * 100), got %d", score)
	}

	// Test Reserve/Commit lifecycle
	reserveStatus := plugin.Reserve(context.Background(), state, pod, "node-1")
	if reserveStatus != nil && !reserveStatus.IsSuccess() {
		t.Errorf("Reserve failed: %v", reserveStatus)
	}

	plugin.PostBind(context.Background(), state, pod, "node-1")
	if !mock.commitCalled || !mock.lastSuccess {
		t.Errorf("Expected PostBind to call PlacementCommitted with success=true")
	}

	plugin.Unreserve(context.Background(), state, pod, "node-1")
	if mock.lastSuccess {
		t.Errorf("Expected Unreserve to call PlacementCommitted with success=false")
	}
}
