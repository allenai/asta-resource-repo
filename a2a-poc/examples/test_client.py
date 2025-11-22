"""Test client for interacting with the Handler A2A server."""

import asyncio
import uuid

import httpx


async def get_agent_card(base_url: str) -> dict:
    """
    Fetch the agent card from an A2A server.

    Args:
        base_url: Base URL of the A2A server

    Returns:
        Agent card as dictionary
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/.well-known/agent-card.json", timeout=10.0)
        response.raise_for_status()
        return response.json()


async def send_task(base_url: str, message: str) -> dict:
    """
    Send a task to an A2A server using JSON-RPC.

    Args:
        base_url: Base URL of the A2A server
        message: Message text to send

    Returns:
        Task response as dictionary
    """
    message_id = str(uuid.uuid4())

    # A2A uses JSON-RPC protocol
    rpc_request = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
            }
        },
        "id": str(uuid.uuid4()),
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(base_url, json=rpc_request, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def main():
    """Run the test client."""
    handler_url = "http://localhost:9000"

    print("=== A2A Handler Test Client ===\n")

    # Get agent card
    print("Fetching Handler agent card...")
    try:
        card = await get_agent_card(handler_url)
        print(f"Agent: {card.get('name')}")
        print(f"Description: {card.get('description')}")
        print(f"Version: {card.get('version')}")
        print(f"Skills: {[skill.get('name') for skill in card.get('skills', [])]}")
        print()
    except Exception as e:
        print(f"Error fetching agent card: {e}")
        print("Make sure the Handler server is running on http://localhost:9000")
        print("Run: uv run python examples/run_handler.py")
        return

    # Test conversation with multiple messages
    messages = [
        "Hello! Can you help me process some data?",
        "What about analyzing numbers?",
        "Thanks for your help!",
    ]

    for i, message in enumerate(messages, 1):
        print(f"Message {i}: {message}")
        try:
            result = await send_task(handler_url, message)

            # Extract response from JSON-RPC result
            if "result" in result:
                rpc_result = result["result"]
                if "output" in rpc_result:
                    output = rpc_result["output"]
                    if "messages" in output:
                        for msg in output["messages"]:
                            for part in msg.get("parts", []):
                                if part.get("kind") == "text" and "text" in part:
                                    print(f"Response: {part['text']}")

            print(f"RPC ID: {result.get('id')}")
            print()

        except Exception as e:
            print(f"Error: {e}")
            print()

        # Small delay between messages
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
