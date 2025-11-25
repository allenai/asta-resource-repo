"""Test client for interacting with the Handler A2A server."""

import asyncio
import uuid

from a2a.client import ClientFactory
from a2a.types import Message, Role, TextPart


async def main():
    """Run the test client."""
    handler_url = "http://localhost:9000"

    print("=== A2A Handler Test Client ===\n")

    # Connect to the Handler agent using A2A client
    print("Connecting to Handler agent...")
    try:
        client = await ClientFactory.connect(agent=handler_url)

        # Get agent card
        print("Fetching Handler agent card...")
        card = await client.get_card()
        print(f"Agent: {card.name}")
        print(f"Description: {card.description}")
        print(f"Version: {card.version}")
        print(f"Skills: {[skill.name for skill in card.skills]}")
        print()
    except Exception as e:
        print(f"Error connecting to agent: {e}")
        print("Make sure the Handler server is running on http://localhost:9000")
        print("Run: uv run python examples/run_handler.py")
        return

    # Interactive conversation loop
    print("Enter your messages (type 'quit' or 'exit' to stop, Ctrl+D for EOF):\n")

    try:
        while True:
            # Read user input
            try:
                text = input("You: ").strip()
            except EOFError:
                print("\nExiting...")
                break

            # Check for exit commands
            if text.lower() in ["quit", "exit", ""]:
                if text.lower() in ["quit", "exit"]:
                    print("Goodbye!")
                break

            try:
                # Create A2A message
                message = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.user,
                    parts=[TextPart(text=text)],
                )

                # Send message and collect responses

                print("Agent: ", end="", flush=True)
                response_printed = False

                async for event in client.send_message(message):
                    # Handle Message responses
                    if isinstance(event, Message):
                        for part in event.parts:
                            if isinstance(part.root, TextPart):
                                print(part.root.text)
                                response_printed = True

                    # Handle Task events (tuple of Task and UpdateEvent)
                    elif isinstance(event, tuple) and len(event) == 2:
                        task, update_event = event
                        # Extract final response from task output
                        if task.output and task.output.messages:
                            for msg in task.output.messages:
                                for part in msg.parts:
                                    if part.root.kind == "text":
                                        print(part.root.text)
                                        response_printed = True

                if not response_printed:
                    print("(no response)")

                print()

            except Exception as e:
                print(f"\nError: {e}\n")

    finally:
        # Clean up
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
