"""HTTP client wrapper for agent communication endpoints."""

import logging
from typing import Any, Dict

import httpx

from cli_agent_manager.api.models import (
    AssignRequest,
    AssignResponse,
    HandoffRequest,
    HandoffResponse,
    HandoffResult,
    SendMessageRequest,
    SendMessageResponse,
)
from cli_agent_manager.constants import API_BASE_URL

logger = logging.getLogger(__name__)


class AgentCommunicationClient:
    """HTTP client for agent communication operations.
    
    This client provides the same interface as the MCP tools but uses HTTP requests
    to communicate with the FastAPI server endpoints.
    """

    def __init__(self, base_url: str = API_BASE_URL, timeout: float = 30.0):
        """Initialize the agent communication client.
        
        Args:
            base_url: Base URL for the API server
            timeout: Default timeout for HTTP requests
        """
        self.base_url = base_url
        self.timeout = timeout

    async def handoff(
        self,
        agent_profile: str,
        message: str,
        timeout: int = 600,
    ) -> HandoffResult:
        """Hand off a task to another agent via TRON terminal and wait for completion.

        This method replicates the MCP handoff tool functionality using HTTP requests.

        Args:
            agent_profile: The agent profile to hand off to
            message: The message/task to send to the target agent
            timeout: Maximum time to wait for completion (1-3600 seconds)

        Returns:
            HandoffResult with success status, message, and agent output
        """
        try:
            request = HandoffRequest(
                agent_profile=agent_profile,
                message=message,
                timeout=timeout
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/agents/handoff",
                    json=request.model_dump(),
                )
                response.raise_for_status()
                
                handoff_response = HandoffResponse(**response.json())
                
                # Convert to HandoffResult for compatibility
                return HandoffResult(
                    success=handoff_response.success,
                    message=handoff_response.message,
                    output=handoff_response.output,
                    terminal_id=handoff_response.terminal_id,
                )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during handoff: {e}")
            return HandoffResult(
                success=False,
                message=f"Handoff failed: HTTP error - {str(e)}",
                output=None,
                terminal_id=None,
            )
        except Exception as e:
            logger.error(f"Unexpected error during handoff: {e}")
            return HandoffResult(
                success=False,
                message=f"Handoff failed: {str(e)}",
                output=None,
                terminal_id=None,
            )

    async def assign(
        self,
        agent_profile: str,
        message: str,
    ) -> Dict[str, Any]:
        """Assign a task to another agent without blocking.

        This method replicates the MCP assign tool functionality using HTTP requests.

        Args:
            agent_profile: Agent profile for the worker terminal
            message: Task message (include callback instructions)

        Returns:
            Dict with success status, worker terminal_id, and message
        """
        try:
            request = AssignRequest(
                agent_profile=agent_profile,
                message=message
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/agents/assign",
                    json=request.model_dump(),
                )
                response.raise_for_status()
                
                assign_response = AssignResponse(**response.json())
                
                # Convert to dict for compatibility with MCP interface
                return {
                    "success": assign_response.success,
                    "terminal_id": assign_response.terminal_id,
                    "message": assign_response.message,
                }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during assignment: {e}")
            return {
                "success": False,
                "terminal_id": None,
                "message": f"Assignment failed: HTTP error - {str(e)}",
            }
        except Exception as e:
            logger.error(f"Unexpected error during assignment: {e}")
            return {
                "success": False,
                "terminal_id": None,
                "message": f"Assignment failed: {str(e)}",
            }

    async def send_message(
        self,
        receiver_id: str,
        message: str,
    ) -> Dict[str, Any]:
        """Send a message to another terminal's inbox.

        This method replicates the MCP send_message tool functionality using HTTP requests.

        Args:
            receiver_id: Terminal ID of the receiver
            message: Message content to send

        Returns:
            Dict with success status and message details
        """
        try:
            # Get sender ID from environment
            import os
            sender_id = os.getenv("TRON_TERMINAL_ID")
            
            request = SendMessageRequest(
                receiver_id=receiver_id,
                message=message,
                sender_id=sender_id  # Will be None if not set, endpoint will handle it
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/agents/send-message",
                    json=request.model_dump(),
                )
                response.raise_for_status()
                
                send_response = SendMessageResponse(**response.json())
                
                if send_response.success:
                    # Convert to dict for compatibility with MCP interface
                    return {
                        "success": send_response.success,
                        "message_id": send_response.message_id,
                        "sender_id": send_response.sender_id,
                        "receiver_id": send_response.receiver_id,
                        "created_at": send_response.created_at,
                    }
                else:
                    # Return error format compatible with MCP interface
                    return {
                        "success": False,
                        "error": send_response.error,
                    }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during send message: {e}")
            return {
                "success": False,
                "error": f"HTTP error - {str(e)}",
            }
        except Exception as e:
            logger.error(f"Unexpected error during send message: {e}")
            return {
                "success": False,
                "error": str(e),
            }


# Global client instance for easy access
agent_client = AgentCommunicationClient()


# Convenience functions that match the MCP tool signatures exactly
async def handoff(
    agent_profile: str,
    message: str,
    timeout: int = 600,
) -> HandoffResult:
    """Hand off a task to another agent via TRON terminal and wait for completion.
    
    This function provides the exact same interface as the MCP handoff tool.
    """
    return await agent_client.handoff(agent_profile, message, timeout)


async def assign(
    agent_profile: str,
    message: str,
) -> Dict[str, Any]:
    """Assign a task to another agent without blocking.
    
    This function provides the exact same interface as the MCP assign tool.
    """
    return await agent_client.assign(agent_profile, message)


async def send_message(
    receiver_id: str,
    message: str,
) -> Dict[str, Any]:
    """Send a message to another terminal's inbox.
    
    This function provides the exact same interface as the MCP send_message tool.
    """
    return await agent_client.send_message(receiver_id, message)