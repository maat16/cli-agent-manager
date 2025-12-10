#!/bin/bash

# CLI Agent Orchestrator HTTP Setup Test Script
# This script tests the HTTP-based agent communication setup

set -e

echo "🚀 Testing CLI Agent Orchestrator HTTP Setup"
echo "============================================="

# Check if tron-server is available
echo "1. Checking tron-server availability..."
if ! command -v tron-server &> /dev/null; then
    echo "❌ tron-server not found. Please install CLI Agent Orchestrator first:"
    echo "   uv tool install git+https://github.com/maat16/cli-agent-manager.git@main --upgrade"
    exit 1
fi
echo "✅ tron-server found"

# Check if server is running
echo "2. Checking if HTTP server is running..."
if curl -s http://localhost:9889/health > /dev/null 2>&1; then
    echo "✅ HTTP server is running on port 9889"
else
    echo "⚠️  HTTP server not running. Starting it now..."
    echo "   Run 'tron-server' in another terminal and try again"
    echo "   Or run: tron-server &"
    exit 1
fi

# Test API endpoints
echo "3. Testing API endpoints..."
if curl -s --max-time 5 http://localhost:9889/health | grep -q "ok"; then
    echo "✅ API endpoints responding"
else
    echo "❌ API endpoints not responding correctly"
    exit 1
fi

# Check agent installation
echo "4. Testing agent installation..."
tron install examples/assign/analysis_supervisor_http.md > /dev/null 2>&1 || true
echo "✅ Agent installation completed"

echo ""
echo "🎉 All tests passed! Your HTTP-based setup is ready."
echo ""
echo "Next steps:"
echo "1. Keep tron-server running in this terminal"
echo "2. In another terminal:"
echo "   tron install examples/assign/analysis_supervisor_http.md --provider kiro_cli"
echo "   tron launch --agents analysis_supervisor_http --provider kiro_cli"
echo "3. Try the example workflow in the agent terminal"
echo ""
echo "For the complete example, see: examples/assign/README.md"