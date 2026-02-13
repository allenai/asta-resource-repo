from datetime import datetime
from typing import Any
import base64

from pydantic import BaseModel, field_serializer


class DocumentMetadata(BaseModel):
    """Document metadata for local index (no content storage)

    Documents are identified by their UUID (10-character alphanumeric short ID).
    """

    uuid: str = ""  # Short ID (10-char alphanumeric) - stored in YAML
    name: str | None = None
    mime_type: str
    url: str  # Where the content actually lives (required)
    summary: str  # Text description for retrieval/search (required)
    tags: list[str] = []  # Tags for categorization (required, can be empty)
    created_at: datetime | None = None
    modified_at: datetime | None = None
    extra: dict[str, Any] | None = None

    @field_serializer("created_at", "modified_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format string"""
        return dt.isoformat() if dt else None

    @property
    def is_binary(self) -> bool:
        """Check if the document is binary based on its MIME type

        Text MIME types: text/*, application/json
        All others are considered binary
        """
        text_mime_prefixes = ("text/",)
        text_mime_types = {"application/json"}

        return not (
            self.mime_type.startswith(text_mime_prefixes)
            or self.mime_type in text_mime_types
        )


class Document(BaseModel):
    """Document ready for wire serialization"""

    metadata: DocumentMetadata
    content: str

    def to_binary(self) -> "BinaryDocument":
        """Convert wire format to raw format (bytes)

        For binary files (is_binary=True): content is base64-encoded, decode it
        For text files (is_binary=False): content is UTF-8 string, encode it
        """
        return BinaryDocument(
            metadata=self.metadata,
            content=(
                base64.b64decode(self.content)
                if self.metadata.is_binary
                else self.content.encode("utf-8")
            ),
        )


class BinaryDocument(BaseModel):
    """Document with binary content"""

    metadata: DocumentMetadata
    content: bytes

    def to_serializable(self) -> Document:
        """Convert raw format (bytes) to wire format

        For binary files (is_binary=True): encode bytes to base64 string
        For text files (is_binary=False): decode bytes to UTF-8 string
        """
        return Document(
            metadata=self.metadata,
            content=(
                base64.b64encode(self.content).decode("utf-8")
                if self.metadata.is_binary
                else self.content.decode("utf-8")
            ),
        )


class SearchHit(BaseModel):
    """Search result representation"""

    result: DocumentMetadata
    score: float = 0.0  # Relevance score (higher is better)


class SearchResult(BaseModel):
    """Result of a search operation"""

    total: int
    hits: list[SearchHit]
