# Migration Guide: MCP to HTTP-based Agent Communication

This guide explains how to migrate from MCP-based agent communication to HTTP-based communication using REST endpoints.

## Overview

The CLI Agent Orchestrator now supports HTTP-based agent communication as an alternative to the MCP (Model Context Protocol) server. This provides the same functionality with better error handling, debugging capabilities, and integration with the existing FastAPI infrastructure.

## What Changed

### Before (MCP-based)
- Agents used `tron-mcp-server` for communication
- Communication happened through MCP protocol
- Tools: `handoff`, `assign`, `send_message`

### After (HTTP-based)
- Agents use `tron-http-server` for communication
- Communication happens through HTTP REST endpoints
- Same tools: `handoff`, `assign`, `send_message` (identical interface)

## Migration Steps

### 1. Update Agent Profile Configuration

**Before:**
```yaml
---
name: your_agent_name
description: Your agent description
mcpServers:
  tron-mcp-server:
    type: stdio
    command: uvx
    args:
      - "--from"
      - "git+https://github.com/maat16/cli-agent-manager.git@main"
      - "tron-mcp-server"
---
```

**After:**
```yaml
---
name: your_agent_name
description: Your agent description
mcpServers:
  tron-http-server:
    type: stdio
    command: uvx
    args:
      - "--from"
      - "git+https://github.com/maat16/cli-agent-manager.git@main"
      - "tron-http-server"
---
```

### 2. No Code Changes Required

The agent communication tools have identical interfaces:

```python
# These work exactly the same in both MCP and HTTP versions
handoff(agent_profile="analyst", message="Analyze data")
assign(agent_profile="worker", message="Process task")
send_message(receiver_id="abc123", message="Results ready")
```

### 3. Update Installation Commands

**Before:**
```bash
tron install examples/assign/analysis_supervisor.md
```

**After:**
```bash
tron install examples/assign/analysis_supervisor_http.md
```

## Benefits of HTTP-based Communication

### 1. Better Error Handling
- Detailed HTTP error codes and messages
- Structured error responses
- Better debugging information

### 2. OpenAPI Documentation
- Automatic API documentation at `/docs`
- Interactive API testing interface
- Complete endpoint specifications

### 3. Standard HTTP Infrastructure
- Uses existing FastAPI server
- Leverages HTTP best practices
- Better monitoring and logging

### 4. Backward Compatibility
- Same function signatures
- Identical behavior and responses
- Drop-in replacement for MCP tools

## Architecture Comparison

### MCP-based Architecture
```
Agent → MCP Protocol → tron-mcp-server → HTTP Requests → FastAPI Server
```

### HTTP-based Architecture
```
Agent → HTTP Requests → tron-http-server → HTTP Requests → FastAPI Server
```

## Available Endpoints

The HTTP-based communication uses these REST endpoints:

- `POST /agents/handoff` - Synchronous task delegation
- `POST /agents/assign` - Asynchronous task delegation
- `POST /agents/send-message` - Inter-agent messaging

## Environment Variables

Both systems use the same environment variables:

- `tron_TERMINAL_ID` - Current terminal identifier
- Required for sender identification in messaging

## Testing the Migration

### 1. Start the FastAPI Server
```bash
tron-server
```

### 2. Install HTTP-based Agent Profile
```bash
tron install examples/assign/analysis_supervisor_http.md
```

### 3. Launch Agent
```bash
tron launch --agents analysis_supervisor_http
```

### 4. Test Communication
The agent should work identically to the MCP version.

## Troubleshooting

### Common Issues

1. **Missing httpx dependency**
   - Solution: Ensure httpx is installed (`pip install httpx`)

2. **Server not running**
   - Solution: Start FastAPI server with `tron-server`

3. **Wrong endpoint URL**
   - Solution: Check `API_BASE_URL` configuration

### Debugging

1. **Check server logs**
   ```bash
   tron-server  # Check console output
   ```

2. **Test endpoints directly**
   - Visit `http://localhost:9889/docs` for interactive API docs

3. **Verify agent configuration**
   - Ensure agent profile uses `tron-http-server`

## Rollback Plan

If you need to rollback to MCP-based communication:

1. Change agent profile back to `tron-mcp-server`
2. Reinstall the original agent profile
3. Restart the agent

## Performance Considerations

- HTTP-based communication has similar performance to MCP
- Slightly more overhead due to HTTP protocol
- Better error recovery and retry capabilities

## Security

- HTTP communication uses the same security model
- All requests go through the existing FastAPI server
- Same authentication and authorization mechanisms

## Future Deprecation

The MCP-based communication will be deprecated in future versions:

- **Current**: Both MCP and HTTP supported
- **Next Release**: HTTP recommended, MCP deprecated
- **Future Release**: MCP support removed

## Support

For issues with the migration:

1. Check the troubleshooting section above
2. Review server logs for error details
3. Test with the provided example agent profiles
4. Ensure all dependencies are installed correctly