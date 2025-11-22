"""Run the Subagent A2A server."""

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from a2a_poc.subagent import SubagentExecutor


def create_subagent_server(host: str = "0.0.0.0", port: int = 9001) -> A2AStarletteApplication:
    """
    Create and configure the Subagent A2A server.

    Args:
        host: Host to bind to
        port: Port to bind to

    Returns:
        Configured A2A server application
    """
    # Define subagent skills
    skills = [
        AgentSkill(
            id="process_task",
            name="Process Task",
            description="Process a task request and return results with artifacts",
            tags=["processing", "tasks"],
            examples=["Process this data", "Analyze this request"],
        )
    ]

    # Create public agent card
    agent_card = AgentCard(
        name="Asta Subagent",
        description="Stateless task processing agent that returns results with artifacts",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=skills,
        supportsAuthenticatedExtendedCard=False,
    )

    # Initialize request handler with subagent executor
    request_handler = DefaultRequestHandler(
        agent_executor=SubagentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # Create A2A server
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    return server


def main():
    """Run the Subagent server."""
    host = "0.0.0.0"
    port = 9001

    print(f"Starting Subagent A2A server on {host}:{port}")
    print(f"Agent card available at: http://localhost:{port}/.well-known/agent-card.json")

    server = create_subagent_server(host, port)
    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()
