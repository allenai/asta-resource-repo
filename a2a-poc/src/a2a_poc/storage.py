"""Storage layer interfaces and implementations for artifacts and conversation history."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Union

from a2a.types import DataPart, FilePart, FileWithUri, Message, Part, TextPart

DataArtifact = TextPart | FilePart | DataPart

# Data Models - None needed, using A2A types


# Storage Interfaces


class IArtifactStore(ABC):
    """Interface for artifact storage."""

    @abstractmethod
    async def store(self, artifact: DataArtifact) -> FileWithUri:
        """
        Store an artifact and return a file reference.

        Args:
            artifact: The artifact data to store (as a DataPart)

        Returns:
            A FileWithUri reference to the stored artifact
        """
        pass

    @abstractmethod
    async def get(self, file_ref: FileWithUri) -> Optional[DataArtifact]:
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
        self._artifacts: dict[str, DataArtifact] = {}

    async def store(self, artifact: DataArtifact) -> FileWithUri:
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
