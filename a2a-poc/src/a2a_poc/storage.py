"""Storage layer interfaces and implementations for artifacts and conversation history."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from a2a.types import DataPart, FilePart, FileWithUri, Message, TextPart

MessageAttachment = FilePart | DataPart

# Data Models - None needed, using A2A types


# Storage Interfaces


class IArtifactStore(ABC):
    """Interface for artifact storage."""

    @abstractmethod
    async def store(self, artifact: MessageAttachment) -> FileWithUri:
        """
        Store an artifact and return a file reference.

        Args:
            artifact: The artifact data to store (as a DataPart)

        Returns:
            A FileWithUri reference to the stored artifact
        """
        pass

    async def persist(self, artifacts: list[MessageAttachment]) -> list[MessageAttachment]:
        """
        Store multiple artifacts and return their file references.

        Args:
            artifacts: List of artifact data to store
        """
        ref_parts = []
        for artifact in artifacts:
            file_ref = await self.store(artifact)
            ref_part = FilePart(file = file_ref, metadata = artifact.metadata)
            ref_parts.append(ref_part)
        return ref_parts

    @abstractmethod
    async def get(self, file_ref: FileWithUri) -> Optional[MessageAttachment]:
        """
        Retrieve an artifact by file reference.

        Args:
            file_ref: The file reference (FileWithUri) to the artifact

        Returns:
            The artifact data if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete(self, file_ref: FileWithUri) -> bool:
        """
        Delete an artifact by file reference.

        Args:
            file_ref: The file reference (FileWithUri) to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def list_all(self) -> list[FileWithUri]:
        """
        List all artifact references.

        Returns:
            List of all artifact file references
        """
        pass


class IConversationHistory(ABC):
    """Interface for conversation history storage."""

    @abstractmethod
    async def add_message(self, message: Message) -> None:
        """
        Add a message to the history.

        Args:
            message: The A2A Message to add
        """
        pass

    @abstractmethod
    async def get_messages(self, limit: Optional[int] = None) -> list[Message]:
        """
        Retrieve all message parts from conversation history, flattened into a single list.

        Args:
            limit: Maximum number of recent messages to include (None for all)

        Returns:
            List of all parts from messages, flattened
        """
        pass

    @abstractmethod
    async def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """
        Retrieve a specific message by ID.

        Args:
            message_id: The message identifier

        Returns:
            The A2A Message if found, None otherwise
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all messages from history."""
        pass

    @abstractmethod
    async def get_all_messages(self, limit: Optional[int] = None) -> list[Message]:
        """
        Retrieve full message objects, optionally limited to most recent N.

        Args:
            limit: Maximum number of recent messages to return (None for all)

        Returns:
            List of A2A Message objects
        """
        pass


# In-Memory Implementations


class InMemoryArtifactStore(IArtifactStore):
    """Simple in-memory implementation of artifact storage for testing."""

    def __init__(self):
        self._artifacts: dict[str, MessageAttachment] = {}

    async def store(self, artifact: MessageAttachment) -> FileWithUri:
        """Store an artifact and return a file reference."""
        import uuid

        # Generate a unique URI for the artifact
        artifact_id = str(uuid.uuid4())
        uri = f"asta://local/artifacts/{artifact_id}"

        # Store the artifact data
        self._artifacts[uri] = artifact

        # Extract name and mime_type from metadata if available
        name = None
        mime_type = None
        if artifact.metadata:
            name = artifact.metadata.get("name")
            mime_type = artifact.metadata.get("mime_type")

        # Return a file reference
        return FileWithUri(uri=uri, name=name, mime_type=mime_type)

    async def get(self, file_ref: FileWithUri) -> Optional[DataPart]:
        """Retrieve an artifact by file reference."""
        return self._artifacts.get(file_ref.uri)

    async def delete(self, file_ref: FileWithUri) -> bool:
        """Delete an artifact by file reference."""
        if file_ref.uri in self._artifacts:
            del self._artifacts[file_ref.uri]
            return True
        return False

    async def list_all(self) -> list[FileWithUri]:
        """List all artifact references."""
        return [
            FileWithUri(
                uri=uri,
                name=artifact.metadata.get("name") if artifact.metadata else None,
                mime_type=artifact.metadata.get("mime_type") if artifact.metadata else None,
            )
            for uri, artifact in self._artifacts.items()
        ]


class InMemoryConversationHistory(IConversationHistory):
    """Simple in-memory implementation of conversation history for testing."""

    def __init__(self):
        self._messages: list[Message] = []

    async def add_message(self, message: Message) -> None:
        """Add a message to the history."""
        self._messages.append(message)

    async def get_messages(self, limit: Optional[int] = None) -> list[Union[TextPart, FilePart, DataPart]]:
        """Retrieve all message parts from conversation history, flattened into a single list."""
        messages = self._messages if limit is None else self._messages[-limit:]
        parts = []
        for message in messages:
            parts.extend(message.parts)
        return parts

    async def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """Retrieve a specific message by ID."""
        for message in self._messages:
            if message.message_id == message_id:
                return message
        return None

    async def clear(self) -> None:
        """Clear all messages from history."""
        self._messages.clear()

    async def get_all_messages(self, limit: Optional[int] = None) -> list[Message]:
        """Retrieve full message objects, optionally limited to most recent N."""
        if limit is None:
            return self._messages.copy()
        return self._messages[-limit:]


# Filesystem Implementations


class FilesystemArtifactStore(IArtifactStore):
    """Filesystem-based implementation of artifact storage."""

    def __init__(self, base_path: str | Path):
        """
        Initialize the filesystem artifact store.

        Args:
            base_path: Base directory for storing artifacts
        """
        self.base_path = Path(base_path)
        self.artifacts_dir = self.base_path / "artifacts"
        self.metadata_dir = self.base_path / "metadata"

        # Create directories if they don't exist
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def _get_artifact_path(self, artifact_id: str) -> Path:
        """Get the filesystem path for an artifact."""
        return self.artifacts_dir / artifact_id

    def _get_metadata_path(self, artifact_id: str) -> Path:
        """Get the filesystem path for artifact metadata."""
        return self.metadata_dir / f"{artifact_id}.json"

    async def store(self, artifact: MessageAttachment) -> FileWithUri:
        """Store an artifact and return a file reference."""
        import uuid

        # Generate a unique ID for the artifact
        artifact_id = str(uuid.uuid4())
        uri = f"asta://local/artifacts/{artifact_id}"

        # Extract name and mime_type from metadata if available
        name = None
        mime_type = None
        if artifact.metadata:
            name = artifact.metadata.get("name")
            mime_type = artifact.metadata.get("mime_type")

        # Store the full artifact object as JSON
        artifact_path = self._get_artifact_path(artifact_id)
        artifact_data = artifact.model_dump()
        artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

        # Store reference metadata separately for quick lookups
        metadata = {
            "uri": uri,
            "name": name,
            "mime_type": mime_type,
            "kind": artifact.kind,
        }
        metadata_path = self._get_metadata_path(artifact_id)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Return a file reference
        return FileWithUri(uri=uri, name=name, mime_type=mime_type)

    async def get(self, file_ref: FileWithUri) -> Optional[MessageAttachment]:
        """Retrieve an artifact by file reference."""
        # Extract artifact ID from URI
        # URI format: asta://local/artifacts/{artifact_id}
        try:
            artifact_id = file_ref.uri.split("/")[-1]
        except (IndexError, AttributeError):
            return None

        artifact_path = self._get_artifact_path(artifact_id)
        metadata_path = self._get_metadata_path(artifact_id)

        if not artifact_path.exists() or not metadata_path.exists():
            return None

        # Load metadata to determine the kind of artifact
        try:
            metadata_content = metadata_path.read_text(encoding="utf-8")
            metadata = json.loads(metadata_content)
            kind = metadata.get("kind")
        except (json.JSONDecodeError, OSError):
            return None

        # Load artifact data
        try:
            artifact_content = artifact_path.read_text(encoding="utf-8")
            artifact_data = json.loads(artifact_content)
        except (json.JSONDecodeError, OSError):
            return None

        # Deserialize to the correct type based on kind
        if kind == "text":
            return TextPart.model_validate(artifact_data)
        elif kind == "data":
            return DataPart.model_validate(artifact_data)
        elif kind == "file":
            return FilePart.model_validate(artifact_data)
        else:
            return None

    async def delete(self, file_ref: FileWithUri) -> bool:
        """Delete an artifact by file reference."""
        try:
            artifact_id = file_ref.uri.split("/")[-1]
        except (IndexError, AttributeError):
            return False

        artifact_path = self._get_artifact_path(artifact_id)
        metadata_path = self._get_metadata_path(artifact_id)

        deleted = False
        if artifact_path.exists():
            artifact_path.unlink()
            deleted = True

        if metadata_path.exists():
            metadata_path.unlink()
            deleted = True

        return deleted

    async def list_all(self) -> list[FileWithUri]:
        """List all artifact references."""
        result = []

        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                metadata_content = metadata_file.read_text(encoding="utf-8")
                metadata = json.loads(metadata_content)

                result.append(
                    FileWithUri(
                        uri=metadata["uri"],
                        name=metadata.get("name"),
                        mime_type=metadata.get("mime_type"),
                    )
                )
            except (json.JSONDecodeError, OSError, KeyError):
                # Skip invalid metadata files
                continue

        return result


class FilesystemConversationHistory(IConversationHistory):
    """Filesystem-based implementation of conversation history storage."""

    def __init__(self, base_path: str | Path):
        """
        Initialize the filesystem conversation history.

        Args:
            base_path: Base directory for storing conversation history
        """
        self.base_path = Path(base_path)
        self.messages_dir = self.base_path / "messages"
        self.index_file = self.base_path / "message_index.json"

        # Create directories if they don't exist
        self.messages_dir.mkdir(parents=True, exist_ok=True)

        # Load or initialize the message index
        self._load_index()

    def _load_index(self) -> None:
        """Load the message index from disk."""
        if self.index_file.exists():
            try:
                content = self.index_file.read_text(encoding="utf-8")
                self._message_ids = json.loads(content)
            except (json.JSONDecodeError, OSError):
                self._message_ids = []
                self._save_index()
        else:
            self._message_ids = []
            self._save_index()

    def _save_index(self) -> None:
        """Save the message index to disk."""
        self.index_file.write_text(json.dumps(self._message_ids, indent=2), encoding="utf-8")

    def _get_message_path(self, message_id: str) -> Path:
        """Get the filesystem path for a message."""
        # Use safe filename by replacing problematic characters
        safe_id = message_id.replace("/", "_").replace("\\", "_")
        return self.messages_dir / f"{safe_id}.json"

    def _serialize_message(self, message: Message) -> dict:
        """Serialize a message to a dictionary."""
        return message.model_dump()

    def _deserialize_message(self, data: dict) -> Message:
        """Deserialize a message from a dictionary."""
        return Message.model_validate(data)

    async def add_message(self, message: Message) -> None:
        """Add a message to the history."""
        # Save the message to disk
        message_path = self._get_message_path(message.message_id)
        serialized = self._serialize_message(message)
        message_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

        # Add to index if not already present
        if message.message_id not in self._message_ids:
            self._message_ids.append(message.message_id)
            self._save_index()

    async def get_messages(self, limit: Optional[int] = None) -> list[Union[TextPart, FilePart, DataPart]]:
        """Retrieve all message parts from conversation history, flattened into a single list."""
        messages = await self.get_all_messages(limit=limit)
        parts = []
        for message in messages:
            parts.extend(message.parts)
        return parts

    async def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """Retrieve a specific message by ID."""
        message_path = self._get_message_path(message_id)

        if not message_path.exists():
            return None

        try:
            content = message_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return self._deserialize_message(data)
        except (json.JSONDecodeError, OSError):
            return None

    async def clear(self) -> None:
        """Clear all messages from history."""
        # Delete all message files
        for message_file in self.messages_dir.glob("*.json"):
            message_file.unlink()

        # Clear the index
        self._message_ids = []
        self._save_index()

    async def get_all_messages(self, limit: Optional[int] = None) -> list[Message]:
        """Retrieve full message objects, optionally limited to most recent N."""
        message_ids = self._message_ids if limit is None else self._message_ids[-limit:]

        messages = []
        for message_id in message_ids:
            message = await self.get_message_by_id(message_id)
            if message:
                messages.append(message)

        return messages
