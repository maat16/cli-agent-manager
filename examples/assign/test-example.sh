#!/bin/bash

# Test script for the HTTP-based assign example
# This script validates that all components are properly configured

set -e

echo "🧪 Testing HTTP-Based Assign Example"
echo "===================================="

# Check prerequisites
echo "1. Checking prerequisites..."

if ! command -v tron-server &> /dev/null; then
    echo "❌ tron-server not found"
    exit 1
fi

if ! command -v tron &> /dev/null; then
    echo "❌ tron command not found"
    exit 1
fi

echo "✅ Prerequisites found"

# Check if HTTP server is running
echo "2. Checking HTTP server..."
if ! curl -s http://localhost:9889/health > /dev/null 2>&1; then
    echo "⚠️  HTTP server not running. Please start it with: tron-server"
    exit 1
fi
echo "✅ HTTP server is running"

# Install agent profiles
echo "3. Installing agent profiles..."
tron install examples/assign/analysis_supervisor_http.md > /dev/null 2>&1 || true
tron install examples/assign/data_analyst.md > /dev/null 2>&1 || true
tron install examples/assign/report_generator.md > /dev/null 2>&1 || true
echo "✅ Agent profiles installed"

# Validate agent profiles exist
echo "4. Validating agent profiles..."
if [ -f ~/.aws/cli-agent-manager/agent-store/analysis_supervisor_http.md ]; then
    echo "✅ analysis_supervisor_http found"
else
    echo "❌ analysis_supervisor_http not found"
    exit 1
fi

if [ -f ~/.aws/cli-agent-manager/agent-store/data_analyst.md ]; then
    echo "✅ data_analyst found"
else
    echo "❌ data_analyst not found"
    exit 1
fi

if [ -f ~/.aws/cli-agent-manager/agent-store/report_generator.md ]; then
    echo "✅ report_generator found"
else
    echo "❌ report_generator not found"
    exit 1
fi

echo "✅ All agent profiles validated"

echo ""
echo "🎉 Example setup is ready!"
echo ""
echo "To run the example:"
echo "1. tron launch --agents analysis_supervisor_http --provider kiro_cli"
echo "2. In the agent terminal, paste the example task from README.md"
echo "3. Watch the multi-agent orchestration in action"
echo ""
echo "Monitor with: tmux list-sessions"
echo "Cleanup with: tron shutdown --all"