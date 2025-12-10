# CLI Agent Orchestrator

CLI Agent Orchestrator (TRON, pronounced as "tron"), is a lightweight orchestration system for managing multiple AI agent sessions in tmux terminals. Enables Multi-agent collaboration via HTTP-based REST API communication.

## Hierarchical Multi-Agent System

CLI Agent Orchestrator (TRON) implements a hierarchical multi-agent system that enables complex problem-solving through specialized division of CLI Developer Agents.

![TRON Architecture](./docs/assets/tron_architecture.png)

### Key Features

* **Hierarchical orchestration** – tron's supervisor agent coordinates workflow management and task delegation to specialized worker agents. The supervisor maintains overall project context while agents focus on their domains of expertise.
* **Session-based isolation** – Each agent operates in isolated tmux sessions, ensuring proper context separation while enabling seamless communication through HTTP-based REST APIs. This provides both coordination and parallel processing capabilities.
* **Intelligent task delegation** – tron automatically routes tasks to appropriate specialists based on project requirements, expertise matching, and workflow dependencies. The system adapts between individual agent work and coordinated team efforts through three orchestration patterns:
    - **Handoff** - Synchronous task transfer with wait-for-completion
    - **Assign** - Asynchronous task spawning for parallel execution  
    - **Send Message** - Direct communication with existing agents
* **Flexible workflow patterns** – tron supports both sequential coordination for dependent tasks and parallel processing for independent work streams. This allows optimization of both development speed and quality assurance processes.
* **Flow - Scheduled runs** – Automated execution of workflows at specified intervals using cron-like scheduling, enabling routine tasks and monitoring workflows to run unattended.
* **Context preservation** – The supervisor agent provides only necessary context to each worker agent, avoiding context pollution while maintaining workflow coherence.
* **Direct worker interaction and steering** – Users can interact directly with worker agents to provide additional steering, distinguishing from sub-agents features by allowing real-time guidance and course correction.
* **Advanced CLI integration** – tron agents have full access to advanced features of the developer CLI, such as the [sub-agents](https://docs.claude.com/en/docs/claude-code/sub-agents) feature of Claude Code, [Custom Agent](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/command-line-custom-agents.html) of Amazon Q Developer for CLI and so on.

For detailed project structure and architecture, see [CODEBASE.md](CODEBASE.md).

## Installation

1. Install tmux (version 3.3 or higher required)

```bash
bash <(curl -s https://raw.githubusercontent.com/maat16/cli-agent-manager/refs/heads/main/tmux-install.sh)
```

2. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install CLI Agent Orchestrator:

```bash
uv tool install git+https://github.com/maat16/cli-agent-manager.git@main --upgrade
```

**Note:** This version uses HTTP-based agent communication instead of MCP. All functionality remains the same, but with better compatibility and easier debugging.

## Quick Start

### Complete HTTP-Based Workflow Example

**Quick Test (Optional):**
```bash
# Test your setup with the provided script
./test-http-setup.sh
```

Here's a complete example showing how to set up and run the HTTP-based multi-agent system:

```bash
# 1. Start the HTTP server
tron-server

# 2. In another terminal, install the HTTP-based agent profiles
tron install examples/assign/analysis_supervisor_http.md --provider kiro_cli
tron install examples/assign/data_analyst.md --provider kiro_cli
tron install examples/assign/report_generator.md --provider kiro_cli

# 3. Launch the supervisor agent
tron launch --agents analysis_supervisor_http --provider kiro_cli

# 4. In the supervisor terminal, try this example:
# "Analyze these datasets and create a comprehensive report:
#  - Dataset A: [1, 2, 3, 4, 5]
#  - Dataset B: [10, 20, 30, 40, 50]  
#  - Dataset C: [5, 15, 25, 35, 45]
#  Calculate mean, median, and standard deviation for each dataset."

# 5. Watch the orchestration:
#    - Supervisor assigns 3 data analysts (parallel)
#    - Supervisor handoffs to report generator (sequential)
#    - Data analysts send results back via send_message
#    - Supervisor combines everything into final report

# 6. Clean up when done
tron shutdown --all
```

### Installing Agents

tron supports installing agents from multiple sources:

**1. Install built-in agents (bundled with tron):**

```bash
tron install code_supervisor
tron install developer
tron install reviewer
```

**2. Install from a local file:**

```bash
tron install ./my-custom-agent.md
tron install /absolute/path/to/agent.md
```

**3. Install from a URL:**

```bash
tron install https://example.com/agents/custom-agent.md
```

When installing from a file or URL, the agent is saved to your local agent store (`~/.aws/cli-agent-manager/agent-store/`) and can be referenced by name in future installations.

**Provider Selection:**

By default, agents are installed for the `kiro_cli` provider (Kiro CLI). You can specify a different provider:

```bash
# Install for Kiro CLI (default)
tron install developer --provider kiro_cli

# Install for Amazon Q CLI
tron install developer --provider q_cli
```

Note: The `claude_code` provider does not require agent installation.

**Default Provider:** Kiro CLI is now the default provider, making it easy to use with your current setup.

For details on creating custom agent profiles, see [docs/agent-profile.md](docs/agent-profile.md).

### Launching Agents

Start the tron HTTP server:

```bash
tron-server
```

In another terminal, launch a terminal with an agent profile:

```bash
tron launch --agents code_supervisor

# Or specify a provider
tron launch --agents code_supervisor --provider kiro_cli
```

Shutdown sessions:

```bash
# Shutdown all tron sessions
tron shutdown --all

# Shutdown specific session
tron shutdown --session tron-my-session
```

### Working with tmux Sessions

All agent sessions run in tmux. Useful commands:

```bash
# List all sessions
tmux list-sessions

# Attach to a session
tmux attach -t <session-name>

# Detach from session (inside tmux)
Ctrl+b, then d

# Switch between windows (inside tmux)
Ctrl+b, then n          # Next window
Ctrl+b, then p          # Previous window
Ctrl+b, then <number>   # Go to window number (0-9)
Ctrl+b, then w          # List all windows (interactive selector)

# Delete a session
tron shutdown --session <session-name>
```

**List all windows (Ctrl+b, w):**

![Tmux Window Selector](./docs/assets/tmux_all_windows.png)

## HTTP-Based Agent Communication and Orchestration Modes

tron provides a local HTTP server that processes orchestration requests. CLI agents can interact with this server through HTTP-based agent communication tools to coordinate multi-agent workflows.

### How It Works

Each agent terminal is assigned a unique `tron_TERMINAL_ID` environment variable. The server uses this ID to:

- Route messages between agents
- Track terminal status (IDLE, BUSY, COMPLETED, ERROR)
- Manage terminal-to-terminal communication via inbox
- Coordinate orchestration operations

When an agent calls an HTTP-based agent communication tool, the server identifies the caller by their `tron_TERMINAL_ID` and orchestrates accordingly.

### Orchestration Modes

tron supports three orchestration patterns:

**1. Handoff** - Transfer control to another agent and wait for completion

- Creates a new terminal with the specified agent profile
- Sends the task message and waits for the agent to finish
- Returns the agent's output to the caller
- Automatically exits the agent after completion
- Use when you need **synchronous** task execution with results

Example: Sequential code review workflow

![Handoff Workflow](./docs/assets/handoff-workflow.png)

**2. Assign** - Spawn an agent to work independently (async)

- Creates a new terminal with the specified agent profile
- Sends the task message with callback instructions
- Returns immediately with the terminal ID
- Agent continues working in the background
- Assigned agent sends results back to supervisor via `send_message` when complete
- Messages are queued for delivery if the supervisor is busy (common in parallel workflows)
- Use for **asynchronous** task execution or fire-and-forget operations

Example: A supervisor assigns parallel data analysis tasks to multiple analysts while using handoff to sequentially generate a report template, then combines all results.

See [examples/assign](examples/assign) for the complete working example with step-by-step execution instructions.

![Parallel Data Analysis](./docs/assets/parallel-data-analysis.png)

**3. Send Message** - Communicate with an existing agent

- Sends a message to a specific terminal's inbox
- Messages are queued and delivered when the terminal is idle
- Enables ongoing collaboration between agents
- Common for **swarm** operations where multiple agents coordinate dynamically
- Use for iterative feedback or multi-turn conversations

Example: Multi-role feature development

![Multi-role Feature Development](./docs/assets/multi-role-feature-development.png)

### Custom Orchestration

The `tron-server` runs on `http://localhost:9889` by default and exposes REST APIs for session management, terminal control, and messaging. The CLI commands (`tron launch`, `tron shutdown`) and HTTP-based agent communication tools (`handoff`, `assign`, `send_message`) are just examples of how these APIs can be packaged together.

You can combine the three orchestration modes above into custom workflows, or create entirely new orchestration patterns using the underlying APIs to fit your specific needs.

For complete API documentation, see [docs/api.md](docs/api.md).

### HTTP-Based Communication Benefits

tron now uses HTTP-based REST APIs instead of MCP (Model Context Protocol) for agent communication:

**Key Advantages:**
- **Better compatibility**: Works in environments where MCP access is restricted
- **Standard protocols**: Uses familiar HTTP requests and JSON responses
- **Enhanced debugging**: Clear HTTP status codes and error messages
- **OpenAPI documentation**: Automatic API documentation generation
- **Easier integration**: Compatible with existing HTTP infrastructure


**Agent Configuration:**
```yaml
mcpServers:
  tron-http-server:  # Changed from tron-mcp-server
    type: stdio
    command: uvx
    args:
      - "--from"
      - "git+https://github.com/maat16/cli-agent-manager.git@main"
      - "tron-http-server"  # Changed from tron-mcp-server
```

## Flows - Scheduled Agent Sessions

Flows allow you to schedule agent sessions to run automatically based on cron expressions.

### Prerequisites

Install the agent profile you want to use:

```bash
tron install developer
```

### Quick Start

The example flow asks a simple world trivia question every morning at 7:30 AM.

```bash
# 1. Start the tron HTTP server
tron-server

# 2. In another terminal, add a flow
tron flow add examples/flow/morning-trivia.md

# 3. List flows to see schedule and status
tron flow list

# 4. Manually run a flow (optional - for testing)
tron flow run morning-trivia

# 5. View flow execution (after it runs)
tmux list-sessions
tmux attach -t <session-name>

# 6. Cleanup session when done
tron shutdown --session <session-name>
```

**IMPORTANT:** The `tron-server` must be running for flows to execute on schedule.

### Example 1: Simple Scheduled Task

A flow that runs at regular intervals with a static prompt (no script needed):

**File: `daily-standup.md`**

```yaml
---
name: daily-standup
schedule: "0 9 * * 1-5"  # 9am weekdays
agent_profile: developer
provider: kiro_cli  # Optional, defaults to kiro_cli
---

Review yesterday's commits and create a standup summary.
```

### Example 2: Conditional Execution with Health Check

A flow that monitors a service and only executes when there's an issue:

**File: `monitor-service.md`**

```yaml
---
name: monitor-service
schedule: "*/5 * * * *"  # Every 5 minutes
agent_profile: developer
script: ./health-check.sh
---

The service at [[url]] is down (status: [[status_code]]).
Please investigate and triage the issue:
1. Check recent deployments
2. Review error logs
3. Identify root cause
4. Suggest remediation steps
```

**Script: `health-check.sh`**

```bash
#!/bin/bash
URL="https://api.example.com/health"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL")

if [ "$STATUS" != "200" ]; then
  # Service is down - execute flow
  echo "{\"execute\": true, \"output\": {\"url\": \"$URL\", \"status_code\": \"$STATUS\"}}"
else
  # Service is healthy - skip execution
  echo "{\"execute\": false, \"output\": {}}"
fi
```

### Flow Commands

```bash
# Add a flow
tron flow add daily-standup.md

# List all flows (shows schedule, next run time, enabled status)
tron flow list

# Enable/disable a flow
tron flow enable daily-standup
tron flow disable daily-standup

# Manually run a flow (ignores schedule)
tron flow run daily-standup

# Remove a flow
tron flow remove daily-standup
```

## Troubleshooting

### Common HTTP Server Issues

**Server won't start:**
```bash
# Check if port 9889 is already in use
netstat -an | grep 9889

# Kill existing processes if needed
pkill -f tron-server
```

**Server won't stop with Ctrl+C:**
```bash
# If Ctrl+C doesn't work, force kill the process
pkill -f tron-server

# Or find and kill the specific process
ps aux | grep tron-server
kill <process_id>
```

**Agent tools not working:**
```bash
# Verify server is running
curl http://localhost:9889/health

# Check agent configuration uses tron-http-server (not tron-mcp-server)
# Reinstall agents if needed
tron install examples/assign/analysis_supervisor_http.md --force
```

**Connection refused errors:**
```bash
# Ensure tron-server is running before launching agents
tron-server &
tron launch --agents analysis_supervisor_http
```

## Special Thanks

Special thanks to [AWS Labs CLI Agent Orchestrator](https://github.com/maat16/cli-agent-manager), which this project is based upon. The original project pioneered the use of MCP (Model Context Protocol) for communication between AI agents, providing the foundational architecture and concepts that enabled this HTTP-based implementation.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.