"""HTTP-based agent communication server (MCP replacement).

This module provides the same agent communication tools as tron-mcp-server
but uses HTTP requests to communicate with the FastAPI server instead of MCP protocol.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict

from cli_agent_manager.clients.agent_communication import (
    assign as async_assign,
    handoff as async_handoff,
    send_message as async_send_message,
)

logger = logging.getLogger(__name__)


def handoff(agent_profile: str, message: str, timeout: int = 600) -> Dict[str, Any]:
    """Synchronous wrapper for handoff function.
    
    Args:
        agent_profile: The agent profile to hand off to
        message: The message/task to send to the target agent
        timeout: Maximum time to wait for completion (1-3600 seconds)
        
    Returns:
        Dict with success status, message, and agent output
    """
    try:
        result = asyncio.run(async_handoff(agent_profile, message, timeout))
        return {
            "success": result.success,
            "message": result.message,
            "output": result.output,
            "terminal_id": result.terminal_id,
        }
    except Exception as e:
        logger.error(f"Handoff failed: {e}")
        return {
            "success": False,
            "message": f"Handoff failed: {str(e)}",
            "output": None,
            "terminal_id": None,
        }


def assign(agent_profile: str, message: str) -> Dict[str, Any]:
    """Synchronous wrapper for assign function.
    
    Args:
        agent_profile: Agent profile for the worker terminal
        message: Task message (include callback instructions)
        
    Returns:
        Dict with success status, worker terminal_id, and message
    """
    try:
        return asyncio.run(async_assign(agent_profile, message))
    except Exception as e:
        logger.error(f"Assignment failed: {e}")
        return {
            "success": False,
            "terminal_id": None,
            "message": f"Assignment failed: {str(e)}",
        }


def send_message(receiver_id: str, message: str, sender_id: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for send_message function.
    
    Args:
        receiver_id: Terminal ID of the receiver
        message: Message content to send
        
    Returns:
        Dict with success status and message details
    """
    try:
        # If sender_id provided, set it in environment temporarily
        import os
        original_sender = os.environ.get("TRON_TERMINAL_ID")
        if sender_id:
            os.environ["TRON_TERMINAL_ID"] = sender_id
        
        try:
            return asyncio.run(async_send_message(receiver_id, message))
        finally:
            # Restore original environment
            if original_sender:
                os.environ["TRON_TERMINAL_ID"] = original_sender
            elif sender_id and "TRON_TERMINAL_ID" in os.environ:
                del os.environ["TRON_TERMINAL_ID"]
    except Exception as e:
        logger.error(f"Send message failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def main():
    """Main entry point for the HTTP-based agent communication server.
    
    This provides an MCP-compatible interface using HTTP requests instead of MCP protocol.
    """
    print("HTTP-based agent communication server started", file=sys.stderr)
    print("Available tools: handoff, assign, send_message", file=sys.stderr)
    
    # Simple stdio-based interface for MCP compatibility
    try:
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break
                
            try:
                request = json.loads(line.strip())
                method = request.get("method")
                params = request.get("params", {})
                
                if method == "handoff":
                    result = handoff(**params)
                elif method == "assign":
                    result = assign(**params)
                elif method == "send_message":
                    result = send_message(**params)
                else:
                    result = {"error": f"Unknown method: {method}"}
                
                response = {
                    "id": request.get("id"),
                    "result": result
                }
                print(json.dumps(response), flush=True)
                
            except json.JSONDecodeError:
                error_response = {
                    "error": "Invalid JSON request"
                }
                print(json.dumps(error_response), flush=True)
            except Exception as e:
                error_response = {
                    "error": f"Request failed: {str(e)}"
                }
                print(json.dumps(error_response), flush=True)
                
    except KeyboardInterrupt:
        pass
    finally:
        print("HTTP-based agent communication server stopped", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())