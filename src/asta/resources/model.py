from datetime import datetime
from typing import Any
import base64
import re
from uuid import UUID

from pydantic import BaseModel, field_serializer

from asta.resources.exceptions import ValidationError


class DocumentMetadata(BaseModel):
    """Document metadata"""

    uri: str = ""  # Full URI in format asta://{env}/{uuid}
    name: str | None = None
    mime_type: str
    tags: list[str] | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    extra: dict[str, Any] | None = None
    size: int = 0

    @field_serializer("created_at", "modified_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format string"""
        return dt.isoformat() if dt else None

    @property
    def is_binary(self) -> bool:
        """Check if the document is binary based on its MIME type"""
        binary_mime_types = {
            "application/pdf",
        }
        return self.mime_type in binary_mime_types


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
    snippet: str | None = None


class SearchResult(BaseModel):
    """Result of a search operation"""

    total: int
    hits: list[SearchHit]


def parse_document_uri(uri: str) -> tuple[str, str]:
    """Parse document URI in format asta://{env}/{uuid}

    Args:
        uri: Document URI

    Returns:
        Tuple of (env, uuid)

    Raises:
        ValueError: If the URI format is invalid
    """
    pattern = r"^asta://([^/]+)/([a-f0-9-]+)$"
    match = re.match(pattern, uri, re.IGNORECASE)

    if not match:
        raise ValidationError(
            f"Document URI must be in format 'asta://{{env_name}}/{{uuid}}', got: {uri}"
        )

    env, uuid = match.groups()
    # Validate UUID format
    try:
        # Validate it's a valid UUID format
        UUID(uuid)
    except ValueError:
        raise ValidationError(
            f"Invalid UUID format in document URI: {uri}. "
            f"UUID part '{uuid}' is not a valid UUID."
        )

    return env, uuid
