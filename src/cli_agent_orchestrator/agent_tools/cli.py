"""Command-line interface for HTTP-based agent communication tools."""

import argparse
import asyncio
import sys

from cli_agent_manager.agent_tools.http_server import main


def tron_http_server():
    """Entry point for tron-http-server command."""
    parser = argparse.ArgumentParser(
        description="HTTP-based agent communication server (MCP replacement)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This server provides the same agent communication tools as tron-mcp-server
but uses HTTP requests to communicate with the FastAPI server instead of MCP protocol.

Available tools:
  - handoff(agent_profile, message, timeout=600)  # Synchronous task delegation
  - assign(agent_profile, message)                # Asynchronous task delegation  
  - send_message(receiver_id, message)            # Inter-agent messaging

Usage in agent profiles:
  Replace 'tron-mcp-server' with 'tron-http-server' in your agent configuration.

Example:
  mcpServers:
    tron-http-server:
      type: stdio
      command: uvx
      args:
        - "--from"
        - "git+https://github.com/maat16/cli-agent-manager.git@main"
        - "tron-http-server"
        """
    )
    
    parser.add_argument(
        "--version", 
        action="version", 
        version="tron-http-server 1.0.0 (HTTP-based agent communication)"
    )
    
    # Parse arguments (this will handle --help automatically)
    args = parser.parse_args()
    
    try:
        print("Starting HTTP-based agent communication server...", file=sys.stderr)
        print("This server replaces tron-mcp-server with HTTP-based communication.", file=sys.stderr)
        print("Press Ctrl+C to stop.", file=sys.stderr)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    tron_http_server()