from datetime import datetime
from typing import Any
import base64
import re

from pydantic import BaseModel, field_serializer, ConfigDict

from asta.resources.exceptions import ValidationError


class DocumentMetadata(BaseModel):
    """Document metadata for local index (no content storage)

    Storage format: Only `uuid` field is serialized to YAML (not full URI)
    Runtime format: `uri` property reconstructs full URI from namespace + uuid
    """

    model_config = ConfigDict(
        # Don't include computed properties in serialization
        ignored_types=(property,),
    )

    uuid: str = ""  # Short ID (10-char alphanumeric) - stored in YAML
    _namespace: str = ""  # Derived namespace - NOT serialized, injected at runtime
    name: str | None = None
    mime_type: str
    url: str  # Where the content actually lives (required)
    summary: str  # Text description for retrieval/search (required)
    tags: list[str] = []  # Tags for categorization (required, can be empty)
    created_at: datetime | None = None
    modified_at: datetime | None = None
    extra: dict[str, Any] | None = None

    @property
    def uri(self) -> str:
        """Reconstruct full URI from namespace and uuid

        Full URI format: asta://{namespace}/{uuid}
        This is computed at runtime and NOT stored in YAML.
        """
        if not self._namespace:
            # If namespace not set, return empty (will be set during load)
            return ""
        return f"asta://{self._namespace}/{self.uuid}"

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


def parse_document_uri(uri: str) -> tuple[str, str]:
    """Parse document URI in format asta://{namespace}/{uuid}

    Note: Namespace may contain slashes (e.g., owner/repo/branch)
    UUID is a 10-character base62-encoded short ID (alphanumeric: a-zA-Z0-9)

    Args:
        uri: Document URI

    Returns:
        Tuple of (namespace, uuid)

    Raises:
        ValidationError: If the URI format is invalid
    """
    # Match everything between asta:// and the last short ID pattern
    # The .+ will greedily match as much as possible (the namespace with slashes)
    # Then backtrack to find the last / followed by a 10-char alphanumeric ID
    pattern = r"^asta://(.+)/([a-zA-Z0-9]{10})$"
    match = re.match(pattern, uri)

    if not match:
        raise ValidationError(
            f"Document URI must be in format 'asta://{{namespace}}/{{uuid}}', got: {uri}. "
            f"UUID must be a 10-character alphanumeric ID (a-zA-Z0-9)."
        )

    namespace, uuid = match.groups()

    return namespace, uuid


def construct_document_uri(namespace: str, uuid: str) -> str:
    """Construct a document URI in format asta://{namespace}/{uuid}

    Args:
        namespace: Namespace identifier
        uuid: Short ID string (10-character alphanumeric: a-zA-Z0-9)

    Returns:
        Full document URI

    Raises:
        ValidationError: If UUID format is invalid
    """
    # Validate short ID format (10 chars, alphanumeric)
    if not re.match(r"^[a-zA-Z0-9]{10}$", uuid):
        raise ValidationError(
            f"Invalid UUID format: {uuid}. UUID must be a 10-character alphanumeric ID (a-zA-Z0-9)."
        )

    return f"asta://{namespace}/{uuid}"
