"""REST API models for agent communication endpoints."""

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, StringConstraints

from cli_agent_manager.models.terminal import TerminalId


# Legacy compatibility model (moved from mcp_server.models)
class HandoffResult(BaseModel):
    """Result of a handoff operation (legacy MCP compatibility)."""

    success: bool = Field(description="Whether the handoff was successful")
    message: str = Field(description="A message describing the result of the handoff")
    output: Optional[str] = Field(None, description="The output from the target agent")
    terminal_id: Optional[TerminalId] = Field(None, description="The terminal ID used for the handoff")


# Request Models
class HandoffRequest(BaseModel):
    """Request model for handoff operation."""

    agent_profile: str = Field(
        description='The agent profile to hand off to (e.g., "developer", "analyst")',
        min_length=1
    )
    message: str = Field(
        description="The message/task to send to the target agent",
        min_length=1
    )
    timeout: int = Field(
        default=600,
        description="Maximum time to wait for the agent to complete the task (in seconds)",
        ge=1,
        le=3600,
    )


class AssignRequest(BaseModel):
    """Request model for assignment operation."""

    agent_profile: str = Field(
        description='The agent profile for the worker agent (e.g., "developer", "analyst")',
        min_length=1
    )
    message: str = Field(
        description="The task message to send. Include callback instructions for the worker to send results back.",
        min_length=1
    )


class SendMessageRequest(BaseModel):
    """Request model for sending messages to other agents."""

    receiver_id: TerminalId = Field(description="Target terminal ID to send message to")
    message: str = Field(description="Message content to send", min_length=1)
    sender_id: Optional[TerminalId] = Field(None, description="Optional sender terminal ID (auto-detected if not provided)")


# Response Models
class HandoffResponse(BaseModel):
    """Response model for handoff operation."""

    success: bool = Field(description="Whether the handoff was successful")
    message: str = Field(description="A message describing the result of the handoff")
    output: Optional[str] = Field(None, description="The output from the target agent")
    terminal_id: Optional[TerminalId] = Field(None, description="The terminal ID used for the handoff")


class AssignResponse(BaseModel):
    """Response model for assignment operation."""

    success: bool = Field(description="Whether the assignment was successful")
    terminal_id: Optional[TerminalId] = Field(None, description="The worker terminal ID")
    message: str = Field(description="A message describing the result of the assignment")


class SendMessageResponse(BaseModel):
    """Response model for send message operation."""

    success: bool = Field(description="Whether the message was sent successfully")
    message_id: Optional[str] = Field(None, description="The unique message ID")
    sender_id: Optional[TerminalId] = Field(None, description="The sender terminal ID")
    receiver_id: Optional[TerminalId] = Field(None, description="The receiver terminal ID")
    created_at: Optional[str] = Field(None, description="Message creation timestamp")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class InboxMessageResponse(BaseModel):
    """Response model for inbox message."""

    id: int = Field(description="Message ID")
    sender_id: str = Field(description="Sender terminal ID")
    receiver_id: str = Field(description="Receiver terminal ID")
    message: str = Field(description="Message content")
    status: str = Field(description="Message status (pending, delivered, failed)")
    created_at: str = Field(description="Creation timestamp (ISO format)")


class InboxMessagesResponse(BaseModel):
    """Response model for inbox messages list."""

    messages: List[InboxMessageResponse] = Field(description="List of inbox messages")
    total: int = Field(description="Total number of messages returned")
    receiver_id: str = Field(description="Terminal ID these messages belong to")