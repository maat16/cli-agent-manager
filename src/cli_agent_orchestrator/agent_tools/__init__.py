"""Agent tools module for providing communication functions to agents."""

# Import the HTTP-based agent communication functions
from cli_agent_manager.clients.agent_communication import (
    assign,
    handoff,
    send_message,
)

# Make them available at the module level for easy import
__all__ = ["handoff", "assign", "send_message"]