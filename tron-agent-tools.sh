#!/bin/bash

# CLI Agent Orchestrator HTTP Tools
# Helper script for agents to communicate with the FastAPI server

TRON_SERVER_URL="http://localhost:9889"

# Function to make handoff requests
handoff() {
    local agent_profile="$1"
    local message="$2"
    local timeout="${3:-600}"
    
    if [ -z "$agent_profile" ] || [ -z "$message" ]; then
        echo "Error: handoff requires agent_profile and message"
        return 1
    fi
    
    curl -s -X POST "$TRON_SERVER_URL/agents/handoff" \
        -H "Content-Type: application/json" \
        -d "{\"agent_profile\":\"$agent_profile\",\"message\":\"$message\",\"timeout\":$timeout}"
}

# Function to make assign requests
assign() {
    local agent_profile="$1"
    local message="$2"
    
    if [ -z "$agent_profile" ] || [ -z "$message" ]; then
        echo "Error: assign requires agent_profile and message"
        return 1
    fi
    
    curl -s -X POST "$TRON_SERVER_URL/agents/assign" \
        -H "Content-Type: application/json" \
        -d "{\"agent_profile\":\"$agent_profile\",\"message\":\"$message\"}"
}

# Function to send messages
send_message() {
    local receiver_id="$1"
    local message="$2"
    
    if [ -z "$receiver_id" ] || [ -z "$message" ]; then
        echo "Error: send_message requires receiver_id and message"
        return 1
    fi
    
    curl -s -X POST "$TRON_SERVER_URL/agents/send-message" \
        -H "Content-Type: application/json" \
        -d "{\"receiver_id\":\"$receiver_id\",\"message\":\"$message\"}"
}

# Execute the function if called directly
if [ "$#" -gt 0 ]; then
    "$@"
fi