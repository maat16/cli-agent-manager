"""Launch command for CLI Agent Orchestrator CLI."""

import subprocess

import click
import requests

from cli_agent_manager.constants import DEFAULT_PROVIDER, PROVIDERS, SERVER_HOST, SERVER_PORT


@click.command()
@click.option("--agents", required=True, help="Agent profile to launch")
@click.option("--session-name", help="Name of the session (default: auto-generated)")
@click.option("--headless", is_flag=True, help="Launch in detached mode")
@click.option(
    "--provider", default=DEFAULT_PROVIDER, help=f"Provider to use (default: {DEFAULT_PROVIDER})"
)
def launch(agents, session_name, headless, provider):
    """Launch tron session with specified agent profile."""
    try:
        # Validate provider
        if provider not in PROVIDERS:
            raise click.ClickException(
                f"Invalid provider '{provider}'. Available providers: {', '.join(PROVIDERS)}"
            )

        # Call API to create session
        url = f"http://{SERVER_HOST}:{SERVER_PORT}/sessions"
        params = {
            "provider": provider,
            "agent_profile": agents,
        }
        if session_name:
            params["session_name"] = session_name

        response = requests.post(url, params=params)
        response.raise_for_status()

        terminal = response.json()

        click.echo(f"Session created: {terminal['session_name']}")
        
        # Handle both old and new response formats
        if 'name' in terminal:
            click.echo(f"Terminal created: {terminal['name']}")
        elif 'terminal_id' in terminal:
            click.echo(f"Terminal created: {terminal['terminal_id']}")
        
        # Show status if available
        if 'status' in terminal:
            click.echo(f"Status: {terminal['status']}")
        if 'message' in terminal:
            click.echo(f"Info: {terminal['message']}")

        # Attach to tmux session unless headless
        if not headless:
            import time
            # Small delay to ensure session is fully ready
            time.sleep(1)
            
            try:
                result = subprocess.run(
                    ["tmux", "attach-session", "-t", terminal["session_name"]], 
                    capture_output=True, 
                    text=True
                )
                if result.returncode != 0:
                    click.echo(f"Warning: Could not attach to session. Error: {result.stderr}")
                    click.echo(f"You can manually attach with: tmux attach-session -t {terminal['session_name']}")
            except Exception as e:
                click.echo(f"Warning: Could not attach to session: {e}")
                click.echo(f"You can manually attach with: tmux attach-session -t {terminal['session_name']}")

    except requests.exceptions.RequestException as e:
        raise click.ClickException(f"Failed to connect to tron-server: {str(e)}")
    except Exception as e:
        raise click.ClickException(str(e))
