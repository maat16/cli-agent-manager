"""Single FastAPI entry point for all HTTP routes."""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any, Dict, List, Optional, Tuple

import requests
from fastapi import FastAPI, HTTPException, Path, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, field_validator
from watchdog.observers.polling import PollingObserver

from cli_agent_manager.api.models import (
    AssignRequest,
    AssignResponse,
    HandoffRequest,
    HandoffResponse,
    InboxMessagesResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from cli_agent_manager.clients.database import create_inbox_message, get_inbox_messages, init_db
from cli_agent_manager.constants import (
    API_BASE_URL,
    DEFAULT_PROVIDER,
    INBOX_POLLING_INTERVAL,
    SERVER_HOST,
    SERVER_PORT,
    SERVER_VERSION,
    TERMINAL_LOG_DIR,
)
from cli_agent_manager.models.inbox import MessageStatus
from cli_agent_manager.models.terminal import Terminal, TerminalId, TerminalStatus
from cli_agent_manager.providers.manager import provider_manager
from cli_agent_manager.services import (
    flow_service,
    inbox_service,
    session_service,
    terminal_service,
)
from cli_agent_manager.services.cleanup_service import cleanup_old_data
from cli_agent_manager.services.inbox_service import LogFileHandler
from cli_agent_manager.services.terminal_service import OutputMode
from cli_agent_manager.utils.logging import setup_logging
from cli_agent_manager.utils.terminal import (
    generate_session_name,
    wait_until_terminal_status,
)

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging."""
    
    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        try:
            # Log incoming request
            logger.info(f"[{request_id}] {request.method} {request.url.path} - Started")
            
            # Log query parameters if present (but don't block)
            try:
                if request.query_params:
                    logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
            except Exception:
                pass  # Don't let query param logging block the request
            
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response
            logger.info(f"[{request_id}] {request.method} {request.url.path} - "
                       f"Status: {response.status_code} - Duration: {duration:.3f}s")
            
            # Add request ID to response headers (safely)
            try:
                response.headers["X-Request-ID"] = request_id
            except Exception:
                pass  # Don't let header setting block the response
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{request_id}] {request.method} {request.url.path} - "
                        f"ERROR: {str(e)} - Duration: {duration:.3f}s")
            # Re-raise the exception to let FastAPI handle it
            raise


async def flow_daemon():
    """Background task to check and execute flows."""
    logger.info("Flow daemon started")
    while True:
        try:
            flows = flow_service.get_flows_to_run()
            for flow in flows:
                try:
                    executed = flow_service.execute_flow(flow.name)
                    if executed:
                        logger.info(f"Flow '{flow.name}' executed successfully")
                    else:
                        logger.info(f"Flow '{flow.name}' skipped (execute=false)")
                except Exception as e:
                    logger.error(f"Flow '{flow.name}' failed: {e}")
        except Exception as e:
            logger.error(f"Flow daemon error: {e}")

        await asyncio.sleep(60)


# Response Models
class TerminalOutputResponse(BaseModel):
    output: str
    mode: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting CLI Agent Orchestrator server...")
    setup_logging()
    init_db()

    # Run cleanup in background
    asyncio.create_task(asyncio.to_thread(cleanup_old_data))

    # Start flow daemon as background task
    daemon_task = asyncio.create_task(flow_daemon())

    # Start inbox watcher
    inbox_observer = PollingObserver(timeout=INBOX_POLLING_INTERVAL)
    inbox_observer.schedule(LogFileHandler(), str(TERMINAL_LOG_DIR), recursive=False)
    inbox_observer.start()
    logger.info("Inbox watcher started (PollingObserver)")

    yield

    # Stop inbox observer
    inbox_observer.stop()
    inbox_observer.join()
    logger.info("Inbox watcher stopped")

    # Cancel daemon on shutdown
    daemon_task.cancel()
    try:
        await daemon_task
    except asyncio.CancelledError:
        pass

    logger.info("Shutting down CLI Agent Orchestrator server...")


app = FastAPI(
    title="CLI Agent Orchestrator",
    description="""
    CLI Agent Orchestrator API for managing agent sessions, terminals, and communication.
    
    ## Agent Communication
    
    The API provides three main agent communication endpoints:
    
    * **Handoff** - Synchronous task delegation with completion waiting
    * **Assign** - Asynchronous task delegation without blocking  
    * **Send Message** - Inter-agent messaging via inbox system
    
    ## Features
    
    * Terminal and session management
    * Agent profile support
    * Message queuing and delivery
    * Automatic OpenAPI documentation
    * Comprehensive request/response logging
    * Health monitoring and status endpoints
    """,
    version=SERVER_VERSION,
    lifespan=lifespan,
    tags_metadata=[
        {
            "name": "Health",
            "description": "Health check and monitoring endpoints.",
        },
        {
            "name": "Agent Communication",
            "description": "Endpoints for agent-to-agent communication including handoff, assignment, and messaging operations.",
        },
        {
            "name": "Sessions",
            "description": "Session management operations for organizing related terminals.",
        },
        {
            "name": "Terminals", 
            "description": "Terminal management operations for individual agent execution environments.",
        },
    ],
)

# Add request logging middleware (temporarily disabled for debugging)
# app.add_middleware(RequestLoggingMiddleware)


# Helper functions for agent communication
def _create_terminal_direct(agent_profile: str) -> Tuple[str, str]:
    """Create a new terminal directly without HTTP requests to avoid circular dependencies.

    Args:
        agent_profile: Agent profile for the terminal

    Returns:
        Tuple of (terminal_id, provider)

    Raises:
        Exception: If terminal creation fails
    """
    provider = DEFAULT_PROVIDER

    # Get current terminal ID from environment
    current_terminal_id = os.environ.get("TRON_TERMINAL_ID")
    if current_terminal_id:
        # Get terminal metadata directly from database
        from cli_agent_manager.clients.database import get_terminal_metadata
        terminal_metadata = get_terminal_metadata(current_terminal_id)
        
        if not terminal_metadata:
            raise ValueError(f"Terminal metadata not found for {current_terminal_id}")

        provider = terminal_metadata["provider"]
        session_name = terminal_metadata["tmux_session"]

        # Create new terminal in existing session directly
        terminal = terminal_service.create_terminal(
            provider=provider,
            agent_profile=agent_profile,
            session_name=session_name,
            new_session=False,
        )
    else:
        # Create new session with terminal directly
        session_name = generate_session_name()
        terminal = terminal_service.create_terminal(
            provider=provider,
            agent_profile=agent_profile,
            session_name=session_name,
            new_session=True,
        )

    return terminal.id, provider


def _create_terminal(agent_profile: str) -> Tuple[str, str]:
    """Create a new terminal with the specified agent profile.

    Args:
        agent_profile: Agent profile for the terminal

    Returns:
        Tuple of (terminal_id, provider)

    Raises:
        Exception: If terminal creation fails
    """
    provider = DEFAULT_PROVIDER

    # Get current terminal ID from environment
    current_terminal_id = os.environ.get("TRON_TERMINAL_ID")
    if current_terminal_id:
        # Get terminal metadata via API
        response = requests.get(f"{API_BASE_URL}/terminals/{current_terminal_id}")
        response.raise_for_status()
        terminal_metadata = response.json()

        provider = terminal_metadata["provider"]
        session_name = terminal_metadata["session_name"]

        # Create new terminal in existing session
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_name}/terminals",
            params={"provider": provider, "agent_profile": agent_profile},
        )
        response.raise_for_status()
        terminal = response.json()
    else:
        # Create new session with terminal
        session_name = generate_session_name()
        response = requests.post(
            f"{API_BASE_URL}/sessions",
            params={
                "provider": provider,
                "agent_profile": agent_profile,
                "session_name": session_name,
            },
        )
        response.raise_for_status()
        terminal = response.json()

    return terminal["id"], provider


def _send_direct_input_direct(terminal_id: str, message: str) -> None:
    """Send input directly to a terminal without HTTP requests to avoid circular dependencies.

    Args:
        terminal_id: Terminal ID
        message: Message to send

    Raises:
        Exception: If sending fails
    """
    # Use terminal service directly instead of HTTP request
    success = terminal_service.send_input(terminal_id, message)
    if not success:
        raise ValueError(f"Failed to send input to terminal {terminal_id}")


def _send_direct_input(terminal_id: str, message: str) -> None:
    """Send input directly to a terminal (bypasses inbox).

    Args:
        terminal_id: Terminal ID
        message: Message to send

    Raises:
        Exception: If sending fails
    """
    response = requests.post(
        f"{API_BASE_URL}/terminals/{terminal_id}/input", params={"message": message}
    )
    response.raise_for_status()


def _send_to_inbox(receiver_id: str, message: str) -> Dict[str, Any]:
    """Send message to another terminal's inbox (queued delivery when IDLE).

    Args:
        receiver_id: Target terminal ID
        message: Message content

    Returns:
        Dict with message details

    Raises:
        ValueError: If TRON_TERMINAL_ID not set
        Exception: If API call fails
    """
    sender_id = os.getenv("TRON_TERMINAL_ID")
    if not sender_id:
        raise ValueError("TRON_TERMINAL_ID not set - cannot determine sender")

    response = requests.post(
        f"{API_BASE_URL}/terminals/{receiver_id}/inbox/messages",
        params={"sender_id": sender_id, "message": message},
    )
    response.raise_for_status()
    return response.json()


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint with basic API information."""
    return {
        "service": "CLI Agent Orchestrator",
        "version": SERVER_VERSION,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "agent_communication": ["/agents/handoff", "/agents/assign", "/agents/send-message"],
            "terminals": ["/terminals", "/terminals/{id}", "/terminals/{id}/output"],
            "sessions": ["/sessions", "/sessions/{name}"],
            "inbox": ["/inbox/{terminal_id}", "/terminals/{id}/inbox/messages"]
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "ok", 
        "service": "cli-agent-manager",
        "version": SERVER_VERSION,
        "timestamp": time.time()
    }


@app.get("/health/ping", tags=["Health"])
async def ping():
    """Ultra-lightweight ping endpoint for responsiveness checks."""
    return {"ping": "pong", "timestamp": time.time()}


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check():
    """Detailed health check with system information."""
    try:
        # Check database connectivity
        from cli_agent_manager.clients.database import SessionLocal
        from sqlalchemy import text
        db_status = "ok"
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1")).fetchone()
        except Exception as e:
            db_status = f"error: {str(e)}"
        
        # Check active sessions
        try:
            sessions = session_service.list_sessions()
            session_count = len(sessions)
        except Exception as e:
            session_count = f"error: {str(e)}"
        
        # Check log directory
        log_dir_exists = TERMINAL_LOG_DIR.exists()
        
        return {
            "status": "ok",
            "service": "cli-agent-manager", 
            "version": SERVER_VERSION,
            "timestamp": time.time(),
            "components": {
                "database": db_status,
                "sessions": session_count,
                "log_directory": log_dir_exists,
                "server_host": SERVER_HOST,
                "server_port": SERVER_PORT
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}"
        )


@app.get("/terminals", tags=["Terminals"])
async def list_all_terminals() -> List[Dict]:
    """List all terminals across all sessions."""
    try:
        from cli_agent_manager.clients.database import list_all_terminals
        return list_all_terminals()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list terminals: {str(e)}",
        )


@app.get("/agents/status", tags=["Agent Communication"])
async def get_agents_status() -> Dict[str, Any]:
    """Get status of all active agents and terminals."""
    try:
        from cli_agent_manager.clients.database import list_all_terminals
        terminals = list_all_terminals()
        
        # Group by session and get status
        sessions = {}
        for terminal in terminals:
            session_name = terminal.get("tmux_session", "unknown")
            if session_name not in sessions:
                sessions[session_name] = []
            
            # Get terminal status
            try:
                from cli_agent_manager.services.terminal_service import get_terminal
                terminal_info = get_terminal(terminal["id"])
                terminal["status"] = terminal_info.status.value
            except Exception:
                terminal["status"] = "unknown"
                
            sessions[session_name].append(terminal)
        
        return {
            "total_terminals": len(terminals),
            "sessions": sessions,
            "timestamp": time.time()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agents status: {str(e)}",
        )


@app.post("/agents/handoff", response_model=HandoffResponse, status_code=status.HTTP_200_OK, tags=["Agent Communication"])
async def handoff_agent(request: HandoffRequest) -> HandoffResponse:
    """Hand off a task to another agent via TRON terminal and wait for completion.

    This endpoint allows handing off tasks to other agents by creating a new terminal
    in the same session. It sends the message, waits for completion, and captures the output.

    The endpoint will:
    1. Create a new terminal with the specified agent profile and provider
    2. Send the message to the terminal
    3. Monitor until completion
    4. Return the agent's response
    5. Clean up the terminal with /exit

    Requirements:
    - Must be called from within a tron terminal (tron_TERMINAL_ID environment variable)
    - Target session must exist and be accessible
    """
    start_time = time.time()
    terminal_id = None

    try:
        logger.info(f"Starting handoff to agent: {request.agent_profile}")
        
        # Create terminal with timeout using direct method
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_create_terminal_direct, request.agent_profile)
            
            try:
                terminal_id, provider = await asyncio.wait_for(
                    asyncio.wrap_future(future), 
                    timeout=30.0  # 30 second timeout
                )
                logger.info(f"Created terminal {terminal_id} with provider {provider}")
            except asyncio.TimeoutError:
                logger.error(f"Terminal creation timed out after 30 seconds")
                return HandoffResponse(
                    success=False,
                    message="Terminal creation timed out after 30 seconds",
                    output=None,
                    terminal_id=None,
                )
            except Exception as e:
                logger.error(f"Failed to create terminal: {e}")
                return HandoffResponse(
                    success=False,
                    message=f"Failed to create terminal: {str(e)}",
                    output=None,
                    terminal_id=None,
                )

        # Wait for terminal to be IDLE before sending message
        logger.info(f"Waiting for terminal {terminal_id} to reach IDLE status")
        if not wait_until_terminal_status(terminal_id, TerminalStatus.IDLE, timeout=30.0):
            logger.error(f"Terminal {terminal_id} did not reach IDLE status within 30 seconds")
            return HandoffResponse(
                success=False,
                message=f"Terminal {terminal_id} did not reach IDLE status within 30 seconds",
                output=None,
                terminal_id=terminal_id,
            )

        await asyncio.sleep(2)  # wait another 2s

        # Send message to terminal using direct method
        logger.info(f"Sending message to terminal {terminal_id}")
        _send_direct_input_direct(terminal_id, request.message)

        # Monitor until completion with timeout
        logger.info(f"Waiting for terminal {terminal_id} to complete (timeout: {request.timeout}s)")
        if not wait_until_terminal_status(
            terminal_id, TerminalStatus.COMPLETED, timeout=request.timeout, polling_interval=1.0
        ):
            logger.error(f"Handoff timed out after {request.timeout} seconds")
            return HandoffResponse(
                success=False,
                message=f"Handoff timed out after {request.timeout} seconds",
                output=None,
                terminal_id=terminal_id,
            )

        # Get the response
        logger.info(f"Retrieving output from terminal {terminal_id}")
        try:
            response = requests.get(
                f"{API_BASE_URL}/terminals/{terminal_id}/output", 
                params={"mode": "last"},
                timeout=10  # Add timeout to requests
            )
            response.raise_for_status()
            output_data = response.json()
            output = output_data["output"]
        except Exception as e:
            logger.error(f"Failed to get terminal output: {e}")
            output = f"Failed to retrieve output: {str(e)}"

        # Send provider-specific exit command to cleanup terminal
        try:
            logger.info(f"Cleaning up terminal {terminal_id}")
            response = requests.post(f"{API_BASE_URL}/terminals/{terminal_id}/exit", timeout=5)
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to cleanup terminal {terminal_id}: {e}")

        execution_time = time.time() - start_time
        logger.info(f"Handoff completed successfully in {execution_time:.2f}s")

        return HandoffResponse(
            success=True,
            message=f"Successfully handed off to {request.agent_profile} ({provider}) in {execution_time:.2f}s",
            output=output,
            terminal_id=terminal_id,
        )

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Handoff failed after {execution_time:.2f}s: {e}")
        return HandoffResponse(
            success=False, 
            message=f"Handoff failed: {str(e)}", 
            output=None, 
            terminal_id=terminal_id
        )


@app.post("/agents/assign", response_model=AssignResponse, status_code=status.HTTP_201_CREATED, tags=["Agent Communication"])
async def assign_agent(request: AssignRequest) -> AssignResponse:
    """Assign a task to another agent without blocking.

    This endpoint allows assigning tasks to other agents by creating a new terminal
    and sending the task message immediately. Unlike handoff, this operation returns
    immediately without waiting for completion.

    The endpoint will:
    1. Create a new terminal with the specified agent profile and provider
    2. Send the message to the terminal immediately
    3. Return the worker terminal ID for callback purposes

    Usage Notes:
    - Include callback instructions in the message for the worker to send results back
    - The terminal ID of each agent is available in environment variable TRON_TERMINAL_ID
    - Example message: "Analyze the logs. When done, send results back to terminal ee3f93b3 using send_message tool."

    Requirements:
    - Must be called from within a tron terminal (tron_TERMINAL_ID environment variable)
    - Target session must exist and be accessible
    """
    try:
        logger.info(f"Starting assignment to agent: {request.agent_profile}")
        
        # Create terminal with async timeout to avoid blocking
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_create_terminal_direct, request.agent_profile)
            
            try:
                # Wait for terminal creation with timeout
                terminal_id, provider = await asyncio.wait_for(
                    asyncio.wrap_future(future), 
                    timeout=30.0  # 30 second timeout for assignment
                )
                logger.info(f"Created terminal {terminal_id} with provider {provider}")
                
            except asyncio.TimeoutError:
                logger.error(f"Assignment timed out after 30 seconds")
                return AssignResponse(
                    success=False,
                    terminal_id=None,
                    message="Assignment timed out after 30 seconds during terminal creation",
                )

        # Send message immediately using direct method
        logger.info(f"Sending message to terminal {terminal_id}")
        _send_direct_input_direct(terminal_id, request.message)
        
        logger.info(f"Assignment completed successfully - terminal: {terminal_id}")

        return AssignResponse(
            success=True,
            terminal_id=terminal_id,
            message=f"Task assigned to {request.agent_profile} (terminal: {terminal_id})",
        )

    except Exception as e:
        logger.error(f"Assignment failed: {e}")
        return AssignResponse(
            success=False, 
            terminal_id=None, 
            message=f"Assignment failed: {str(e)}"
        )


@app.post("/agents/send-message", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED, tags=["Agent Communication"])
async def send_message_to_agent(request: SendMessageRequest) -> SendMessageResponse:
    """Send a message to another terminal's inbox.

    This endpoint allows sending messages to other agents by queuing them in the
    receiver's inbox. Messages will be delivered when the destination terminal is IDLE.
    Messages are delivered in order (oldest first).

    The endpoint will:
    1. Detect the sender terminal ID from TRON_TERMINAL_ID environment variable
    2. Queue the message in the receiver's inbox
    3. Return confirmation with message details

    Usage Notes:
    - Messages are queued and delivered when the receiver terminal becomes IDLE
    - Messages are delivered in FIFO (first-in-first-out) order
    - The sender terminal ID is automatically detected from the environment

    Requirements:
    - Must be called from within a tron terminal (tron_TERMINAL_ID environment variable)
    - Receiver terminal must exist
    """
    try:
        # Use sender_id from request if provided, otherwise try environment, otherwise use default
        sender_id = request.sender_id or os.getenv("TRON_TERMINAL_ID")
        if not sender_id:
            # Use a default sender_id for agents that don't have TRON_TERMINAL_ID set
            sender_id = "unknown"
        
        # Create message directly instead of using _send_to_inbox
        inbox_msg = create_inbox_message(sender_id, request.receiver_id, request.message)
        inbox_service.check_and_send_pending_messages(request.receiver_id)
        
        result = {
            "message_id": inbox_msg.id,
            "sender_id": inbox_msg.sender_id,
            "receiver_id": inbox_msg.receiver_id,
            "created_at": inbox_msg.created_at.isoformat(),
        }
        
        return SendMessageResponse(
            success=True,
            message_id=result.get("message_id"),
            sender_id=result.get("sender_id"),
            receiver_id=result.get("receiver_id"),
            created_at=result.get("created_at"),
            error=None
        )

    except ValueError as e:
        # Handle TRON_TERMINAL_ID not set error
        return SendMessageResponse(
            success=False,
            message_id=None,
            sender_id=None,
            receiver_id=request.receiver_id,
            created_at=None,
            error=str(e)
        )
    except Exception as e:
        return SendMessageResponse(
            success=False,
            message_id=None,
            sender_id=None,
            receiver_id=request.receiver_id,
            created_at=None,
            error=f"Failed to send message: {str(e)}"
        )


@app.post("/sessions", status_code=status.HTTP_202_ACCEPTED, tags=["Sessions"])
async def create_session(
    provider: str, agent_profile: str, session_name: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new session with exactly one terminal (async initialization)."""
    try:
        logger.info(f"Creating session with provider={provider}, agent_profile={agent_profile}")
        
        # Generate IDs immediately
        from cli_agent_manager.utils.terminal import generate_session_name, generate_terminal_id
        from cli_agent_manager.constants import SESSION_PREFIX
        
        terminal_id = generate_terminal_id()
        if not session_name:
            session_name = generate_session_name()
        
        if not session_name.startswith(SESSION_PREFIX):
            session_name = f"{SESSION_PREFIX}{session_name}"
        
        # Return immediately with session info
        response = {
            "status": "initializing",
            "session_name": session_name,
            "terminal_id": terminal_id,
            "provider": provider,
            "agent_profile": agent_profile,
            "message": "Session creation started. Terminal is initializing in the background."
        }
        
        # Start background initialization (fire and forget)
        asyncio.create_task(
            _initialize_session_background(
                terminal_id, session_name, provider, agent_profile
            )
        )
        
        logger.info(f"Session creation started: {session_name} (terminal: {terminal_id})")
        return response

    except Exception as e:
        logger.error(f"Failed to start session creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start session creation: {str(e)}",
        )


async def _initialize_session_background(
    terminal_id: str, session_name: str, provider: str, agent_profile: str
):
    """Initialize session in the background without blocking the API."""
    try:
        logger.info(f"Background initialization started for session {session_name}")
        
        # Run the blocking terminal creation in a thread
        import concurrent.futures
        
        def create_terminal_sync():
            return terminal_service.create_terminal(
                provider=provider,
                agent_profile=agent_profile,
                session_name=session_name,
                new_session=True,
            )
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                # Give it a longer timeout since it's background
                result = await asyncio.wait_for(
                    asyncio.wrap_future(executor.submit(create_terminal_sync)),
                    timeout=60.0
                )
                logger.info(f"Background initialization completed for session {session_name}")
                
            except asyncio.TimeoutError:
                logger.error(f"Background initialization timed out for session {session_name}")
                # Try to cleanup the failed session
                try:
                    from cli_agent_manager.clients.tmux import tmux_client
                    if tmux_client.session_exists(session_name):
                        tmux_client.kill_session(session_name)
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup timed out session: {cleanup_error}")
                    
    except Exception as e:
        logger.error(f"Background initialization failed for session {session_name}: {e}")
        # Try to cleanup on any error
        try:
            from cli_agent_manager.clients.tmux import tmux_client
            if tmux_client.session_exists(session_name):
                tmux_client.kill_session(session_name)
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup failed session: {cleanup_error}")


@app.get("/sessions", tags=["Sessions"])
async def list_sessions() -> List[Dict]:
    try:
        return session_service.list_sessions()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@app.get("/sessions/{session_name}", tags=["Sessions"])
async def get_session(session_name: str) -> Dict:
    try:
        return session_service.get_session(session_name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}",
        )


@app.get("/sessions/{session_name}/status", tags=["Sessions"])
async def get_session_status(session_name: str) -> Dict[str, Any]:
    """Get the current status of a session and its terminals."""
    try:
        from cli_agent_manager.clients.tmux import tmux_client
        
        # Check if tmux session exists
        if not tmux_client.session_exists(session_name):
            return {
                "session_name": session_name,
                "status": "not_found",
                "message": "Session does not exist"
            }
        
        # Get terminals in this session
        from cli_agent_manager.clients.database import list_terminals_by_session
        terminals = list_terminals_by_session(session_name)
        
        # Check terminal statuses
        terminal_statuses = []
        for terminal in terminals:
            try:
                # Get terminal status
                from cli_agent_manager.services.terminal_service import get_terminal
                terminal_info = get_terminal(terminal["id"])
                terminal_statuses.append({
                    "terminal_id": terminal["id"],
                    "agent_profile": terminal["agent_profile"],
                    "provider": terminal["provider"],
                    "status": terminal_info.status.value if terminal_info else "unknown"
                })
            except Exception as e:
                terminal_statuses.append({
                    "terminal_id": terminal["id"],
                    "agent_profile": terminal["agent_profile"],
                    "provider": terminal["provider"],
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "session_name": session_name,
            "status": "active",
            "terminal_count": len(terminals),
            "terminals": terminal_statuses
        }
        
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session status: {str(e)}",
        )


@app.delete("/sessions/{session_name}", tags=["Sessions"])
async def delete_session(session_name: str) -> Dict:
    try:
        success = session_service.delete_session(session_name)
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )


@app.post(
    "/sessions/{session_name}/terminals",
    response_model=Terminal,
    status_code=status.HTTP_201_CREATED,
    tags=["Terminals"],
)
async def create_terminal_in_session(
    session_name: str, provider: str, agent_profile: str
) -> Terminal:
    """Create additional terminal in existing session."""
    try:
        result = terminal_service.create_terminal(
            provider=provider,
            agent_profile=agent_profile,
            session_name=session_name,
            new_session=False,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create terminal: {str(e)}",
        )


@app.get("/sessions/{session_name}/terminals", tags=["Terminals"])
async def list_terminals_in_session(session_name: str) -> List[Dict]:
    """List all terminals in a session."""
    try:
        from cli_agent_manager.clients.database import list_terminals_by_session

        return list_terminals_by_session(session_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list terminals: {str(e)}",
        )


@app.get("/terminals/{terminal_id}", response_model=Terminal, tags=["Terminals"])
async def get_terminal(terminal_id: TerminalId) -> Terminal:
    try:
        terminal = terminal_service.get_terminal(terminal_id)
        return Terminal(**terminal)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get terminal: {str(e)}",
        )


@app.post("/terminals/{terminal_id}/input", tags=["Terminals"])
async def send_terminal_input(terminal_id: TerminalId, message: str) -> Dict:
    try:
        success = terminal_service.send_input(terminal_id, message)
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send input: {str(e)}",
        )


@app.get("/terminals/{terminal_id}/output", response_model=TerminalOutputResponse, tags=["Terminals"])
async def get_terminal_output(
    terminal_id: TerminalId, mode: OutputMode = OutputMode.FULL
) -> TerminalOutputResponse:
    try:
        output = terminal_service.get_output(terminal_id, mode)
        return TerminalOutputResponse(output=output, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get output: {str(e)}",
        )


@app.post("/terminals/{terminal_id}/exit", tags=["Terminals"])
async def exit_terminal(terminal_id: TerminalId) -> Dict:
    """Send provider-specific exit command to terminal."""
    try:
        provider = provider_manager.get_provider(terminal_id)
        if provider is None:
            raise ValueError(f"Provider not found for terminal {terminal_id}")
        exit_command = provider.exit_cli()
        terminal_service.send_input(terminal_id, exit_command)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exit terminal: {str(e)}",
        )


@app.delete("/terminals/{terminal_id}", tags=["Terminals"])
async def delete_terminal(terminal_id: TerminalId) -> Dict:
    """Delete a terminal."""
    try:
        success = terminal_service.delete_terminal(terminal_id)
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete terminal: {str(e)}",
        )


@app.get("/terminals/{terminal_id}/inbox/messages", response_model=InboxMessagesResponse, tags=["Terminals"])
async def get_inbox_messages_endpoint(
    terminal_id: TerminalId,
    status: Optional[str] = None,
    limit: int = 10
) -> InboxMessagesResponse:
    """Get inbox messages for a terminal with optional status filter and pagination.
    
    This endpoint allows reading from a terminal's inbox, which is the message queue
    that powers terminal-to-terminal communication. Messages can be filtered by status
    and paginated for efficient retrieval.
    
    Args:
        terminal_id: Terminal ID to get messages for
        status: Optional status filter (pending, delivered, failed)
        limit: Maximum number of messages to return (default 10, max 100)
        
    Returns:
        List of inbox messages with metadata
        
    Example:
        GET /terminals/abc123/inbox/messages?status=pending&limit=5
    """
    try:
        # Validate status parameter if provided
        message_status = None
        if status and status.lower() != "all":
            try:
                message_status = MessageStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status '{status}'. Must be one of: pending, delivered, failed, all"
                )
        
        # Validate and clamp limit
        limit = min(max(1, limit), 100)
        
        # Get messages from database
        messages = get_inbox_messages(terminal_id, message_status, limit)
        
        # Convert to response format
        message_responses = [
            {
                "id": msg.id,
                "sender_id": msg.sender_id,
                "receiver_id": msg.receiver_id,
                "message": msg.message,
                "status": msg.status.value,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]
        
        return InboxMessagesResponse(
            messages=message_responses,
            total=len(message_responses),
            receiver_id=terminal_id
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get inbox messages: {str(e)}",
        )


@app.get("/inbox/{terminal_id}", response_model=InboxMessagesResponse, tags=["Terminals"])
async def get_inbox_messages_shorthand(
    terminal_id: TerminalId,
    status: Optional[str] = None,
    limit: int = 10
) -> InboxMessagesResponse:
    """Shorthand endpoint for getting inbox messages.
    
    This is a convenience endpoint that provides the same functionality as
    GET /terminals/{terminal_id}/inbox/messages but with a shorter URL.
    
    Args:
        terminal_id: Terminal ID to get messages for
        status: Optional status filter (pending, delivered, failed)
        limit: Maximum number of messages to return (default 10, max 100)
        
    Returns:
        List of inbox messages with metadata
        
    Example:
        GET /inbox/abc123?status=pending&limit=5
    """
    # Delegate to the main inbox endpoint
    return await get_inbox_messages_endpoint(terminal_id, status, limit)


@app.get("/messages/{terminal_id}", response_model=InboxMessagesResponse, tags=["Terminals"])
async def get_messages_alias(
    terminal_id: TerminalId,
    status: Optional[str] = None,
    limit: int = 10
) -> InboxMessagesResponse:
    """Alias endpoint for getting messages (same as inbox).
    
    This provides compatibility for agents expecting /messages/{terminal_id} endpoint.
    
    Args:
        terminal_id: Terminal ID to get messages for
        status: Optional status filter (pending, delivered, failed)
        limit: Maximum number of messages to return (default 10, max 100)
        
    Returns:
        List of inbox messages with metadata
    """
    # Delegate to the main inbox endpoint
    return await get_inbox_messages_endpoint(terminal_id, status, limit)


@app.get("/messages", tags=["Terminals"])
async def get_all_messages() -> Dict[str, Any]:
    """Get all messages across all terminals (for debugging)."""
    try:
        from cli_agent_manager.clients.database import SessionLocal, InboxModel
        with SessionLocal() as db:
            messages = db.query(InboxModel).all()
            
            # Group by receiver
            by_receiver = {}
            for msg in messages:
                if msg.receiver_id not in by_receiver:
                    by_receiver[msg.receiver_id] = []
                by_receiver[msg.receiver_id].append({
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "message": msg.message[:100] + "..." if len(msg.message) > 100 else msg.message,
                    "status": msg.status,
                    "created_at": msg.created_at.isoformat(),
                })
            
            return {
                "total_messages": len(messages),
                "by_receiver": by_receiver,
                "timestamp": time.time()
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}",
        )


@app.get("/terminals/{terminal_id}/messages", response_model=InboxMessagesResponse, tags=["Terminals"])
async def get_terminal_messages_alias(
    terminal_id: TerminalId,
    status: Optional[str] = None,
    limit: int = 10
) -> InboxMessagesResponse:
    """Alias endpoint for getting terminal messages (same as inbox).
    
    This provides compatibility for agents expecting /terminals/{terminal_id}/messages endpoint.
    """
    # Delegate to the main inbox endpoint
    return await get_inbox_messages_endpoint(terminal_id, status, limit)


@app.get("/terminals/{terminal_id}/inbox", response_model=InboxMessagesResponse, tags=["Terminals"])
async def get_terminal_inbox_alias(
    terminal_id: TerminalId,
    status: Optional[str] = None,
    limit: int = 10
) -> InboxMessagesResponse:
    """Alias endpoint for getting terminal inbox (same as inbox).
    
    This provides compatibility for agents expecting /terminals/{terminal_id}/inbox endpoint.
    """
    # Delegate to the main inbox endpoint
    return await get_inbox_messages_endpoint(terminal_id, status, limit)


@app.post("/terminals/{receiver_id}/inbox/messages", tags=["Terminals"])
async def create_inbox_message_endpoint(
    receiver_id: TerminalId, sender_id: str, message: str
) -> Dict:
    """Create inbox message and attempt immediate delivery."""
    try:
        inbox_msg = create_inbox_message(sender_id, receiver_id, message)
        inbox_service.check_and_send_pending_messages(receiver_id)

        return {
            "success": True,
            "message_id": inbox_msg.id,
            "sender_id": inbox_msg.sender_id,
            "receiver_id": inbox_msg.receiver_id,
            "created_at": inbox_msg.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create inbox message: {str(e)}",
        )


def main():
    """Entry point for tron-server command."""
    import uvicorn
    import signal
    import sys
    import os

    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Enhanced logging configuration
    log_level = os.getenv("TRON_LOG_LEVEL", "info").lower()
    
    try:
        logger.info(f"Starting CLI Agent Orchestrator HTTP server on {SERVER_HOST}:{SERVER_PORT}")
        logger.info(f"Log level: {log_level}")
        logger.info(f"Access logs: enabled for debugging")
        
        uvicorn.run(
            app, 
            host=SERVER_HOST, 
            port=SERVER_PORT,
            log_level=log_level,
            access_log=True,  # Enable access logs for better observability
            timeout_keep_alive=30,  # Keep connections alive longer
            timeout_graceful_shutdown=10,  # Graceful shutdown timeout
            loop="asyncio",  # Use asyncio event loop
            workers=1  # Single worker for simplicity
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
