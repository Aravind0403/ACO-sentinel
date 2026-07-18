#!/bin/bash
set -e

REPO_ROOT="/Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront"
cd "$REPO_ROOT"

echo "--------------------------------------------------"
echo "Starting Python gRPC server in background..."
echo "--------------------------------------------------"
python v2/grpc_server.py &
SERVER_PID=$!

# Ensure cleanup on exit
cleanup() {
    echo "Stopping Python gRPC server (PID: $SERVER_PID)..."
    kill $SERVER_PID || true
    wait $SERVER_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for server to bind to port 50051
echo "Waiting for gRPC server to start..."
sleep 3

echo "--------------------------------------------------"
echo "Running Go Simulation Harness..."
echo "--------------------------------------------------"
cd v2/go_plugin
go run simulation/main.go
cd "$REPO_ROOT"

echo "--------------------------------------------------"
echo "Generating plots..."
echo "--------------------------------------------------"
python scripts/plot_experiments.py

echo "--------------------------------------------------"
echo "Experiment execution completed successfully!"
echo "--------------------------------------------------"
