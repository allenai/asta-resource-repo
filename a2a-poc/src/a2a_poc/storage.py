"""Storage layer interfaces and implementations for artifacts and conversation history."""

import asyncio
import base64
import json
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from a2a.types import DataPart, FilePart, FileWithBytes, FileWithUri, Message, Part, TextPart

# Data Models - None needed, using A2A types


# Storage Interfaces


class IArtifactStore(ABC):
    """Interface for artifact storage."""

    @abstractmethod
    async def store(self, part: TextPart | FilePart | DataPart) -> Optional[FilePart]:
        """
        Store any in-line data attached to a DataPart or FilePart, and replace with a FileWithUri.

        Args:
            part: The artifact data to store (as a DataPart)

        Returns:
            A FilePart with a URI reference to the data, if stored, else None
        """
        pass

    async def persist(self, parts: list[Part]) -> list[Part]:
        """
        Store any in-line data attached to a DataPart or FilePart, and replace with a FileWithUri.
        Leave TextPart and FileWithUri parts unchanged.

        Args:
            parts: List of parts to persist
        """
        async def store_part(part: Part) -> Part:
            stored_part = await self.store(part.root)
            if stored_part:
                return Part(root=stored_part)
            return part
        modified_parts = await asyncio.gather(*(store_part(part) for part in parts))
        return modified_parts

    @abstractmethod
    async def get(self, part: Part) -> Optional[Part]:
        """
        Retrieve an artifact.
        If part is a FileWithUri, fetch the corresponding DataPart or FilePart.

        Args:
            part: The file reference (FileWithUri) to the artifact

        Returns:
            The artifact data if found, None otherwise
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

    def __init__(self, url_prefix: str = "asta://local/artifacts/"):
        self._artifacts: dict[str, DataPart | FilePart] = {}
        self._url_prefix = url_prefix

    async def store(self, part: TextPart | FilePart | DataPart) -> Optional[FilePart]:
        """Store an artifact and return a file reference."""

        if part.kind == "text":
            # Text parts are not stored as artifacts
            return None
        if part.kind == "file" and isinstance(part.file, FileWithUri):
            # Already a file reference. Don't store
            return None

        # Generate a unique URI for the artifact
        artifact_id = str(uuid.uuid4())
        uri = f"{self._url_prefix}{artifact_id}"

        # Store the artifact data
        self._artifacts[uri] = part

        if part.kind == "data":
            # Return a FileWithUri reference
            file = FileWithUri(uri=uri, name=None, mime_type="application/json")
            return FilePart(file=file, metadata = part.metadata)
        elif part.kind == "file":
            # Return a FileWithUri reference
            file = FileWithUri(uri=uri, name=part.name, mime_type=part.file.mime_type)
            return FilePart(file=file, metadata = part.metadata)
        else:
            raise ValueError("Artifact must be of kind 'data' or 'file'")

    async def get(self, part: Part) -> Optional[Part]:
        """Retrieve an artifact by file reference."""
        if part.root.kind == "file" and isinstance(part.root.file, FileWithUri):
            if not part.root.file.uri.startswith(self._url_prefix):
                return None
            artifact = self._artifacts.get(part.root.file.uri)
            return Part(root=artifact) if artifact else None
        else:
            return None


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

    def __init__(self, base_path: str | Path, url_prefix: str = "asta://local/artifacts/"):
        """
        Initialize the filesystem artifact store.

        Args:
            base_path: Base directory for storing artifacts
        """
        self.base_path = Path(base_path)
        self.artifacts_dir = self.base_path / "artifacts"
        self._url_prefix = url_prefix

        # Create directories if they don't exist
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _get_artifact_path(self, artifact_id: str) -> Path:
        """Get the filesystem path for an artifact."""
        return self.artifacts_dir / artifact_id

    async def store(self, part: TextPart | DataPart | FilePart) -> Optional[FilePart]:
        """Store an artifact and return a file reference."""
        if part.kind == "text":
            # Text parts are not stored as artifacts
            return None
        if part.kind == "file" and isinstance(part.file, FileWithUri):
            # Already a file reference. Don't store
            return None

        # Generate a unique ID for the artifact
        artifact_id = str(uuid.uuid4())
        uri = f"{self._url_prefix}{artifact_id}"

        # Extract name and mime_type from metadata if available
        if part.kind == "data":
            artifact_path = self._get_artifact_path(artifact_id)
            artifact_data = part.model_dump()
            artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
            file = FileWithUri(uri=uri, name=None, mime_type="application/json")
            return FilePart(file=file, metadata=part.metadata)
        elif part.kind == "file":
            artifact_path = self._get_artifact_path(artifact_id)
            artifact_path.write_bytes(base64.b64decode(part.file.bytes))
            file = FileWithUri(uri=uri, name=None, mime_type=part.file.mime_type)
            return FilePart(file=file, metadata=part.metadata)
        else:
            raise ValueError("Artifact must be of kind 'data' or 'file'")


    async def get(self, part: Part) -> Optional[Part]:
        """Retrieve an artifact by file reference."""
        if part.root.kind  in ("text", "data"):
            # Text parts are not stored as artifacts
            return None
        if part.root.kind == "file" and not isinstance(part.root.file, FileWithUri):
            return None

        if not part.root.file.uri.startswith(self._url_prefix):
            return None

        file: FileWithUri = part.root.file
        try:
            artifact_id = file.uri.split("/")[-1]
        except (IndexError, AttributeError):
            raise ValueError("Invalid FileWithUri format")

        artifact_path = self._get_artifact_path(artifact_id)

        if not artifact_path.exists():
            raise ValueError(f"Could not find artifact {artifact_id}")

        artifact_bytes = artifact_path.read_bytes()
        if file.mime_type == "application/json":
            try:
                artifact_data = json.loads(artifact_bytes)
                return Part(root = DataPart(data=artifact_data, metadata = part.root.metadata))
            except (json.JSONDecodeError, OSError):
                raise ValueError(f"Could not decode artifact {artifact_id}")
        else:
            encoded_bytes = base64.b64encode(artifact_bytes)
            return Part(root = FilePart(file=FileWithBytes(bytes=encoded_bytes, name=file.name, mime_type=file.mime_type), metadata = part.root.metadata))


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
