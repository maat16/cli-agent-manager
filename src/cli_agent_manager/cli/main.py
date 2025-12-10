"""Main CLI entry point for CLI Agent Orchestrator."""

import click

from cli_agent_manager.cli.commands.flow import flow
from cli_agent_manager.cli.commands.init import init
from cli_agent_manager.cli.commands.install import install
from cli_agent_manager.cli.commands.launch import launch
from cli_agent_manager.cli.commands.shutdown import shutdown


@click.group()
def cli():
    """CLI Agent Orchestrator."""


# Register commands
cli.add_command(launch)
cli.add_command(init)
cli.add_command(install)
cli.add_command(shutdown)
cli.add_command(flow)


if __name__ == "__main__":
    cli()
