"""Run the Handler A2A server."""

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from a2a_poc.handler import HandlerExecutor
from a2a_poc.storage import InMemoryArtifactStore, InMemoryConversationHistory


def create_handler_server(
    host: str = "0.0.0.0",
    port: int = 9000,
    subagent_url: str = "http://localhost:9001",
) -> A2AStarletteApplication:
    """
    Create and configure the Handler A2A server.

    Args:
        host: Host to bind to
        port: Port to bind to
        subagent_url: URL of the Subagent server

    Returns:
        Configured A2A server application
    """
    # Define handler skills
    skills = [
        AgentSkill(
            id="handle_request",
            name="Handle User Request",
            description="Handle user requests with conversation history and artifact management",
            tags=["conversation", "artifacts", "delegation"],
            examples=[
                "Help me with this task",
                "Process this information",
                "Continue our conversation",
            ],
        )
    ]

    # Create public agent card
    agent_card = AgentCard(
        name="Asta Handler",
        description="Handler agent that manages conversations, artifacts, and delegates to subagent",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=skills,
        supportsAuthenticatedExtendedCard=False,
    )

    # Initialize storage
    artifact_store = InMemoryArtifactStore()
    conversation_history = InMemoryConversationHistory()

    # Initialize request handler with handler executor
    request_handler = DefaultRequestHandler(
        agent_executor=HandlerExecutor(
            subagent_url=subagent_url,
            artifact_store=artifact_store,
            conversation_history=conversation_history,
        ),
        task_store=InMemoryTaskStore(),
    )

    # Create A2A server
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    return server


def main():
    """Run the Handler server."""
    host = "0.0.0.0"
    port = 9000
    subagent_url = "http://localhost:9001"

    print(f"Starting Handler A2A server on {host}:{port}")
    print(f"Agent card available at: http://localhost:{port}/.well-known/agent-card.json")
    print(f"Subagent URL: {subagent_url}")

    server = create_handler_server(host, port, subagent_url)
    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()
