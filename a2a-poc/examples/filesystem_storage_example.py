"""Example of using filesystem-based storage implementations."""

import asyncio
from pathlib import Path

from a2a.types import Message, TextPart

from a2a_poc import FilesystemArtifactStore, FilesystemConversationHistory


async def main():
    """Demonstrate filesystem storage usage."""
    # Create storage directory
    storage_dir = Path("./example_storage")
    storage_dir.mkdir(exist_ok=True)

    print("=== Filesystem Storage Example ===\n")

    # Initialize filesystem stores
    print("1. Initializing filesystem stores...")
    artifact_store = FilesystemArtifactStore(storage_dir / "artifacts")
    conversation_history = FilesystemConversationHistory(storage_dir / "conversations")
    print(f"   - Artifact store: {artifact_store.base_path}")
    print(f"   - Conversation history: {conversation_history.base_path}\n")

    # Store an artifact
    print("2. Storing an artifact...")
    artifact = TextPart(
        text="This is sample content for a text artifact.",
        metadata={"name": "sample.txt", "mime_type": "text/plain"},
    )
    file_ref = await artifact_store.store(artifact)
    print(f"   - Stored artifact with URI: {file_ref.uri}")
    print(f"   - Name: {file_ref.name}")
    print(f"   - MIME type: {file_ref.mime_type}\n")

    # Retrieve the artifact
    print("3. Retrieving the artifact...")
    retrieved_artifact = await artifact_store.get(file_ref)
    if retrieved_artifact:
        print(f"   - Retrieved text: {retrieved_artifact.text}")
        print(f"   - Metadata: {retrieved_artifact.metadata}\n")

    # List all artifacts
    print("4. Listing all artifacts...")
    all_artifacts = await artifact_store.list_all()
    print(f"   - Total artifacts: {len(all_artifacts)}")
    for i, ref in enumerate(all_artifacts, 1):
        print(f"   - Artifact {i}: {ref.uri}\n")

    # Add messages to conversation history
    print("5. Adding messages to conversation history...")
    msg1 = Message(
        message_id="msg-001",
        role="user",
        parts=[TextPart(text="Hello, how are you?")],
    )
    msg2 = Message(
        message_id="msg-002",
        role="agent",
        parts=[TextPart(text="I'm doing well, thank you!")],
    )

    await conversation_history.add_message(msg1)
    await conversation_history.add_message(msg2)
    print("   - Added 2 messages\n")

    # Retrieve conversation history
    print("6. Retrieving conversation history...")
    all_messages = await conversation_history.get_all_messages()
    print(f"   - Total messages: {len(all_messages)}")
    for msg in all_messages:
        role = msg.role
        text = msg.parts[0].root.text if msg.parts else "(no parts)"
        print(f"   - [{role}] {text}")
    print()

    # Retrieve a specific message
    print("7. Retrieving specific message by ID...")
    specific_msg = await conversation_history.get_message_by_id("msg-001")
    if specific_msg:
        print(f"   - Message ID: {specific_msg.message_id}")
        print(f"   - Role: {specific_msg.role}")
        print(f"   - Text: {specific_msg.parts[0].root.text}\n")

    # Demonstrate persistence
    print("8. Demonstrating persistence...")
    print("   - Creating new store instances...")
    new_artifact_store = FilesystemArtifactStore(storage_dir / "artifacts")
    new_conversation_history = FilesystemConversationHistory(storage_dir / "conversations")

    persisted_artifacts = await new_artifact_store.list_all()
    persisted_messages = await new_conversation_history.get_all_messages()

    print(f"   - Persisted artifacts: {len(persisted_artifacts)}")
    print(f"   - Persisted messages: {len(persisted_messages)}")
    print("   - Data persists across store instances!\n")

    # Cleanup example
    print("9. Cleaning up (optional)...")
    await artifact_store.delete(file_ref)
    await conversation_history.clear()
    print("   - Deleted artifact and cleared conversation history\n")

    print("=== Example Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
