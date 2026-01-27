import click

from autopack.research.orchestrator import ResearchOrchestrator


@click.group()
def research():
    """Research-related commands."""
    pass


@research.command()
@click.argument("intent")
def start(intent):
    """Start a new research session with the given intent."""
    orchestrator = ResearchOrchestrator()
    session_id = orchestrator.start_session(intent)
    click.echo(f"Research session started with ID: {session_id}")


@research.command()
@click.argument("session_id")
def validate(session_id):
    """Validate the research session with the given ID."""
    orchestrator = ResearchOrchestrator()
    validation_report = orchestrator.validate_session(session_id)
    click.echo(f"Validation report for session {session_id}:")
    click.echo(validation_report)


@research.command()
@click.argument("session_id")
def publish(session_id):
    """Publish the research findings for the session with the given ID."""
    orchestrator = ResearchOrchestrator()
    success = orchestrator.publish_session(session_id)
    if success:
        click.echo(f"Research findings for session {session_id} published successfully.")
    else:
        click.echo(f"Failed to publish research findings for session {session_id}.")


if __name__ == "__main__":
    research()

# To use this CLI, run the following commands:
# Start a session: python research.py start "Research Intent"
# Validate a session: python research.py validate <session_id>
# Publish findings: python research.py publish <session_id>
