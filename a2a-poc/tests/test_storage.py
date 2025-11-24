"""Tests for storage implementations."""

import tempfile
from pathlib import Path

import pytest
from a2a.types import DataPart, FileWithUri, Message, TextPart

from a2a_poc.storage import (
    FilesystemArtifactStore,
    FilesystemConversationHistory,
    InMemoryArtifactStore,
    InMemoryConversationHistory,
)

# Fixtures


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def fs_artifact_store(temp_dir):
    """Create a filesystem artifact store."""
    return FilesystemArtifactStore(temp_dir / "artifacts")


@pytest.fixture
def fs_conversation_history(temp_dir):
    """Create a filesystem conversation history."""
    return FilesystemConversationHistory(temp_dir / "conversations")


@pytest.fixture
def mem_artifact_store():
    """Create an in-memory artifact store."""
    return InMemoryArtifactStore()


@pytest.fixture
def mem_conversation_history():
    """Create an in-memory conversation history."""
    return InMemoryConversationHistory()


@pytest.fixture
def sample_artifact():
    """Create a sample text artifact."""
    return TextPart(
        text="Sample text content",
        metadata={"name": "test.txt", "mime_type": "text/plain"},
    )


@pytest.fixture
def sample_data_artifact():
    """Create a sample data artifact (structured data)."""
    return DataPart(
        data={"content": "test data", "type": "json"},
        metadata={"name": "test.json", "mime_type": "application/json"},
    )


@pytest.fixture
def sample_message():
    """Create a sample message."""
    return Message(
        message_id="msg-001",
        role="user",
        parts=[TextPart(text="Hello, world!")],
    )


# FilesystemArtifactStore Tests


@pytest.mark.asyncio
async def test_fs_artifact_store_initialization(temp_dir):
    """Test filesystem artifact store initialization."""
    store = FilesystemArtifactStore(temp_dir / "artifacts")

    assert store.base_path == temp_dir / "artifacts"
    assert store.artifacts_dir.exists()
    assert store.metadata_dir.exists()


@pytest.mark.asyncio
async def test_fs_artifact_store_store_text(fs_artifact_store, sample_artifact):
    """Test storing a text artifact."""
    file_ref = await fs_artifact_store.store(sample_artifact)

    assert file_ref.uri.startswith("asta://local/artifacts/")
    assert file_ref.name == "test.txt"
    assert file_ref.mime_type == "text/plain"

    # Verify files were created
    artifact_id = file_ref.uri.split("/")[-1]
    artifact_path = fs_artifact_store.artifacts_dir / artifact_id
    metadata_path = fs_artifact_store.metadata_dir / f"{artifact_id}.json"

    assert artifact_path.exists()
    assert metadata_path.exists()


@pytest.mark.asyncio
async def test_fs_artifact_store_store_data(fs_artifact_store, sample_data_artifact):
    """Test storing a data artifact (structured data)."""
    file_ref = await fs_artifact_store.store(sample_data_artifact)

    assert file_ref.uri.startswith("asta://local/artifacts/")
    assert file_ref.name == "test.json"
    assert file_ref.mime_type == "application/json"


@pytest.mark.asyncio
async def test_fs_artifact_store_get_text(fs_artifact_store, sample_artifact):
    """Test retrieving a text artifact."""
    file_ref = await fs_artifact_store.store(sample_artifact)
    retrieved = await fs_artifact_store.get(file_ref)

    assert retrieved is not None
    assert isinstance(retrieved, TextPart)
    assert retrieved.text == "Sample text content"
    assert retrieved.metadata == sample_artifact.metadata


@pytest.mark.asyncio
async def test_fs_artifact_store_get_data(fs_artifact_store, sample_data_artifact):
    """Test retrieving a data artifact."""
    file_ref = await fs_artifact_store.store(sample_data_artifact)
    retrieved = await fs_artifact_store.get(file_ref)

    assert retrieved is not None
    assert isinstance(retrieved, DataPart)
    assert retrieved.data == {"content": "test data", "type": "json"}
    assert retrieved.metadata == sample_data_artifact.metadata


@pytest.mark.asyncio
async def test_fs_artifact_store_get_nonexistent(fs_artifact_store):
    """Test retrieving a non-existent artifact."""
    fake_ref = FileWithUri(uri="asta://local/artifacts/nonexistent")
    retrieved = await fs_artifact_store.get(fake_ref)

    assert retrieved is None


@pytest.mark.asyncio
async def test_fs_artifact_store_delete(fs_artifact_store, sample_artifact):
    """Test deleting an artifact."""
    file_ref = await fs_artifact_store.store(sample_artifact)
    deleted = await fs_artifact_store.delete(file_ref)

    assert deleted is True

    # Verify artifact was deleted
    retrieved = await fs_artifact_store.get(file_ref)
    assert retrieved is None


@pytest.mark.asyncio
async def test_fs_artifact_store_delete_nonexistent(fs_artifact_store):
    """Test deleting a non-existent artifact."""
    fake_ref = FileWithUri(uri="asta://local/artifacts/nonexistent")
    deleted = await fs_artifact_store.delete(fake_ref)

    assert deleted is False


@pytest.mark.asyncio
async def test_fs_artifact_store_list_all(fs_artifact_store, sample_artifact):
    """Test listing all artifacts."""
    # Initially empty
    artifacts = await fs_artifact_store.list_all()
    assert len(artifacts) == 0

    # Add artifacts
    ref1 = await fs_artifact_store.store(sample_artifact)
    ref2 = await fs_artifact_store.store(
        TextPart(text="Another artifact", metadata={"name": "test2.txt"})
    )

    artifacts = await fs_artifact_store.list_all()
    assert len(artifacts) == 2

    uris = [a.uri for a in artifacts]
    assert ref1.uri in uris
    assert ref2.uri in uris


@pytest.mark.asyncio
async def test_fs_artifact_store_persistence(temp_dir, sample_artifact):
    """Test that artifacts persist across store instances."""
    # Create first store and save artifact
    store1 = FilesystemArtifactStore(temp_dir / "artifacts")
    file_ref = await store1.store(sample_artifact)

    # Create second store instance and retrieve artifact
    store2 = FilesystemArtifactStore(temp_dir / "artifacts")
    retrieved = await store2.get(file_ref)

    assert retrieved is not None
    assert isinstance(retrieved, TextPart)
    assert retrieved.text == "Sample text content"


# FilesystemConversationHistory Tests


@pytest.mark.asyncio
async def test_fs_conversation_history_initialization(temp_dir):
    """Test filesystem conversation history initialization."""
    history = FilesystemConversationHistory(temp_dir / "conversations")

    assert history.base_path == temp_dir / "conversations"
    assert history.messages_dir.exists()
    assert history.index_file.exists()


@pytest.mark.asyncio
async def test_fs_conversation_history_add_message(fs_conversation_history, sample_message):
    """Test adding a message to history."""
    await fs_conversation_history.add_message(sample_message)

    # Verify message was saved
    message_path = fs_conversation_history._get_message_path(sample_message.message_id)
    assert message_path.exists()

    # Verify index was updated
    assert sample_message.message_id in fs_conversation_history._message_ids


@pytest.mark.asyncio
async def test_fs_conversation_history_get_message_by_id(fs_conversation_history, sample_message):
    """Test retrieving a message by ID."""
    await fs_conversation_history.add_message(sample_message)
    retrieved = await fs_conversation_history.get_message_by_id(sample_message.message_id)

    assert retrieved is not None
    assert retrieved.message_id == sample_message.message_id
    assert retrieved.role == sample_message.role
    assert len(retrieved.parts) == len(sample_message.parts)


@pytest.mark.asyncio
async def test_fs_conversation_history_get_message_by_id_nonexistent(fs_conversation_history):
    """Test retrieving a non-existent message."""
    retrieved = await fs_conversation_history.get_message_by_id("nonexistent")
    assert retrieved is None


@pytest.mark.asyncio
async def test_fs_conversation_history_get_all_messages(fs_conversation_history):
    """Test retrieving all messages."""
    msg1 = Message(message_id="msg-001", role="user", parts=[TextPart(text="Message 1")])
    msg2 = Message(message_id="msg-002", role="agent", parts=[TextPart(text="Message 2")])
    msg3 = Message(message_id="msg-003", role="user", parts=[TextPart(text="Message 3")])

    await fs_conversation_history.add_message(msg1)
    await fs_conversation_history.add_message(msg2)
    await fs_conversation_history.add_message(msg3)

    messages = await fs_conversation_history.get_all_messages()
    assert len(messages) == 3
    assert messages[0].message_id == "msg-001"
    assert messages[1].message_id == "msg-002"
    assert messages[2].message_id == "msg-003"


@pytest.mark.asyncio
async def test_fs_conversation_history_get_all_messages_with_limit(fs_conversation_history):
    """Test retrieving messages with a limit."""
    msg1 = Message(message_id="msg-001", role="user", parts=[TextPart(text="Message 1")])
    msg2 = Message(message_id="msg-002", role="agent", parts=[TextPart(text="Message 2")])
    msg3 = Message(message_id="msg-003", role="user", parts=[TextPart(text="Message 3")])

    await fs_conversation_history.add_message(msg1)
    await fs_conversation_history.add_message(msg2)
    await fs_conversation_history.add_message(msg3)

    messages = await fs_conversation_history.get_all_messages(limit=2)
    assert len(messages) == 2
    assert messages[0].message_id == "msg-002"
    assert messages[1].message_id == "msg-003"


@pytest.mark.asyncio
async def test_fs_conversation_history_get_messages_flattened(fs_conversation_history):
    """Test retrieving flattened message parts."""
    msg1 = Message(
        message_id="msg-001",
        role="user",
        parts=[TextPart(text="Part 1"), TextPart(text="Part 2")],
    )
    msg2 = Message(message_id="msg-002", role="agent", parts=[TextPart(text="Part 3")])

    await fs_conversation_history.add_message(msg1)
    await fs_conversation_history.add_message(msg2)

    parts = await fs_conversation_history.get_messages()
    assert len(parts) == 3
    assert parts[0].root.text == "Part 1"
    assert parts[1].root.text == "Part 2"
    assert parts[2].root.text == "Part 3"


@pytest.mark.asyncio
async def test_fs_conversation_history_clear(fs_conversation_history, sample_message):
    """Test clearing conversation history."""
    await fs_conversation_history.add_message(sample_message)

    # Verify message exists
    messages = await fs_conversation_history.get_all_messages()
    assert len(messages) == 1

    # Clear history
    await fs_conversation_history.clear()

    # Verify history is empty
    messages = await fs_conversation_history.get_all_messages()
    assert len(messages) == 0
    assert len(fs_conversation_history._message_ids) == 0


@pytest.mark.asyncio
async def test_fs_conversation_history_persistence(temp_dir):
    """Test that conversation history persists across instances."""
    msg = Message(message_id="msg-001", role="user", parts=[TextPart(text="Test message")])

    # Create first history and add message
    history1 = FilesystemConversationHistory(temp_dir / "conversations")
    await history1.add_message(msg)

    # Create second history instance and retrieve message
    history2 = FilesystemConversationHistory(temp_dir / "conversations")
    messages = await history2.get_all_messages()

    assert len(messages) == 1
    assert messages[0].message_id == msg.message_id
    assert messages[0].parts[0].root.text == "Test message"


# In-Memory Implementation Tests (for comparison)


@pytest.mark.asyncio
async def test_mem_artifact_store_basic(mem_artifact_store, sample_artifact):
    """Test in-memory artifact store basic operations."""
    file_ref = await mem_artifact_store.store(sample_artifact)
    retrieved = await mem_artifact_store.get(file_ref)

    assert retrieved is not None
    assert isinstance(retrieved, TextPart)
    assert retrieved.text == sample_artifact.text


@pytest.mark.asyncio
async def test_mem_conversation_history_basic(mem_conversation_history, sample_message):
    """Test in-memory conversation history basic operations."""
    await mem_conversation_history.add_message(sample_message)
    messages = await mem_conversation_history.get_all_messages()

    assert len(messages) == 1
    assert messages[0].message_id == sample_message.message_id
