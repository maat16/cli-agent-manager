"""HTTP-based agent communication server to replace MCP server functionality.

This module provides a standalone server that agents can use instead of the MCP server.
It provides the same tools (handoff, assign, send_message) but uses HTTP requests
to communicate with the FastAPI server.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict

from cli_agent_manager.clients.agent_communication import (
    assign as http_assign,
    handoff as http_handoff,
    send_message as http_send_message,
)

logger = logging.getLogger(__name__)


class HTTPAgentServer:
    """HTTP-based agent communication server."""

    def __init__(self):
        """Initialize the HTTP agent server."""
        self.tools = {
            "handoff": self._handoff_tool,
            "assign": self._assign_tool,
            "send_message": self._send_message_tool,
        }

    async def _handoff_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle handoff tool calls."""
        try:
            agent_profile = params.get("agent_profile")
            message = params.get("message")
            timeout = params.get("timeout", 600)

            if not agent_profile or not message:
                return {
                    "error": "Missing required parameters: agent_profile and message are required"
                }

            result = await http_handoff(agent_profile, message, timeout)
            
            # Convert HandoffResult to dict for JSON serialization
            return {
                "success": result.success,
                "message": result.message,
                "output": result.output,
                "terminal_id": result.terminal_id,
            }

        except Exception as e:
            logger.error(f"Error in handoff tool: {e}")
            return {
                "success": False,
                "message": f"Handoff failed: {str(e)}",
                "output": None,
                "terminal_id": None,
            }

    async def _assign_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle assign tool calls."""
        try:
            agent_profile = params.get("agent_profile")
            message = params.get("message")

            if not agent_profile or not message:
                return {
                    "error": "Missing required parameters: agent_profile and message are required"
                }

            result = await http_assign(agent_profile, message)
            return result

        except Exception as e:
            logger.error(f"Error in assign tool: {e}")
            return {
                "success": False,
                "terminal_id": None,
                "message": f"Assignment failed: {str(e)}",
            }

    async def _send_message_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle send_message tool calls."""
        try:
            receiver_id = params.get("receiver_id")
            message = params.get("message")

            if not receiver_id or not message:
                return {
                    "error": "Missing required parameters: receiver_id and message are required"
                }

            result = await http_send_message(receiver_id, message)
            return result

        except Exception as e:
            logger.error(f"Error in send_message tool: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a tool request."""
        try:
            tool_name = request.get("tool")
            params = request.get("params", {})

            if tool_name not in self.tools:
                return {
                    "error": f"Unknown tool: {tool_name}. Available tools: {list(self.tools.keys())}"
                }

            result = await self.tools[tool_name](params)
            return result

        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {"error": f"Request failed: {str(e)}"}

    async def run_stdio(self):
        """Run the server using stdio for MCP-compatible communication."""
        logger.info("Starting HTTP-based agent communication server (stdio mode)")
        
        try:
            while True:
                # Read request from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    break
                
                try:
                    request = json.loads(line.strip())
                    response = await self.handle_request(request)
                    
                    # Write response to stdout
                    print(json.dumps(response), flush=True)
                    
                except json.JSONDecodeError as e:
                    error_response = {"error": f"Invalid JSON: {str(e)}"}
                    print(json.dumps(error_response), flush=True)
                    
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")


async def main():
    """Main entry point for the HTTP agent server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    server = HTTPAgentServer()
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())