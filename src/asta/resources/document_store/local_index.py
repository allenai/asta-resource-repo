"""Local YAML-based document metadata index"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import fcntl
import yaml

from ..model import (
    DocumentMetadata,
    SearchHit,
    construct_document_uri,
    parse_document_uri,
)
from ..exceptions import ValidationError, DocumentServiceError
from .base import DocumentStore


class LocalIndexDocumentStore(DocumentStore):
    """Document store that maintains a local YAML index of document metadata

    Stores only metadata (no content) in a git-friendly YAML file at .asta/index.yaml
    Designed for single-user, local-only usage with zero external dependencies.
    """

    def __init__(
        self, namespace: str, resource_type: str, index_path: str = ".asta/index.yaml"
    ):
        """Initialize the local index document store

        Args:
            namespace: Namespace identifier for URIs
            resource_type: Resource type for documents (default: "document")
            index_path: Path to the YAML index file (default: ".asta/index.yaml")
        """
        self.namespace = namespace
        self.resource_type = resource_type
        self.index_path = Path(index_path)
        self._documents: dict[str, DocumentMetadata] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the document store by loading the index file"""
        if self._initialized:
            return

        # Create .asta directory if it doesn't exist
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # Create empty index file if it doesn't exist
        if not self.index_path.exists():
            self._save_index(
                {"version": "1.0", "namespace": self.namespace, "documents": []}
            )

        # Load existing index
        self._load_index()
        self._initialized = True

    async def close(self):
        """Close the document store (no-op for file-based storage)"""
        # No connections to close for file-based storage
        pass

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    def _load_index(self):
        """Load the YAML index file into memory"""
        try:
            with open(self.index_path, "r") as f:
                # Use file locking to prevent concurrent reads during writes
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = yaml.safe_load(f) or {}
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Parse documents from YAML
            self._documents = {}
            for doc_data in data.get("documents", []):
                # Convert datetime strings back to datetime objects
                if "created_at" in doc_data and isinstance(doc_data["created_at"], str):
                    doc_data["created_at"] = datetime.fromisoformat(
                        doc_data["created_at"]
                    )
                if "modified_at" in doc_data and isinstance(
                    doc_data["modified_at"], str
                ):
                    doc_data["modified_at"] = datetime.fromisoformat(
                        doc_data["modified_at"]
                    )

                doc = DocumentMetadata(**doc_data)
                self._documents[doc.uri] = doc

        except Exception as e:
            raise DocumentServiceError(f"Failed to load index file: {e}")

    def _save_index(self, data: dict = None):
        """Save the in-memory index to the YAML file

        Args:
            data: Optional dict to save directly (for initialization)
        """
        try:
            if data is None:
                # Convert documents to dict format for YAML
                # model_dump() already serializes datetimes to ISO strings via field_serializer
                docs_list = [doc.model_dump() for doc in self._documents.values()]

                data = {
                    "version": "1.0",
                    "namespace": self.namespace,
                    "documents": docs_list,
                }

            # Write with exclusive lock for thread safety
            with open(self.index_path, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    yaml.dump(
                        data,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        allow_unicode=True,
                    )
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        except Exception as e:
            raise DocumentServiceError(f"Failed to save index file: {e}")

    async def store(self, document: DocumentMetadata) -> str:
        """Store document metadata and return its URI

        Args:
            document: Document metadata to store

        Returns:
            Document URI

        Raises:
            ValidationError: If URL is invalid
        """
        if not self._initialized:
            await self.initialize()

        # Validate URL format
        if not document.url:
            raise ValidationError("Document URL is required")
        if not (
            document.url.startswith("http://") or document.url.startswith("https://")
        ):
            raise ValidationError(
                f"Invalid URL format: {document.url}. Must start with http:// or https://"
            )

        # Validate required fields
        if not document.summary:
            raise ValidationError("Document summary is required")

        # Generate UUID and URI if not provided
        if not document.uri:
            doc_uuid = str(uuid.uuid4())
            document.uri = construct_document_uri(
                self.namespace, self.resource_type, doc_uuid
            )

        # Set timestamps
        now = datetime.now(timezone.utc)
        if not document.created_at:
            document.created_at = now
        document.modified_at = now

        # Store in memory and save to disk
        self._documents[document.uri] = document
        self._save_index()

        return document.uri

    async def get(self, uri: str) -> Optional[DocumentMetadata]:
        """Retrieve document metadata by URI

        Args:
            uri: Document URI

        Returns:
            Document metadata if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        # Validate URI format
        namespace, resource_type, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
            )
        if resource_type != self.resource_type:
            raise ValidationError(
                f"Resource type mismatch: expected {self.resource_type}, got {resource_type}"
            )

        return self._documents.get(uri)

    async def list_docs(self) -> list[DocumentMetadata]:
        """List all documents in the index

        Returns:
            List of all document metadata
        """
        if not self._initialized:
            await self.initialize()

        return list(self._documents.values())

    async def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Search documents by query (simple in-memory search)

        Searches across name, summary, tags, and extra fields.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by number of matches
        """
        if not self._initialized:
            await self.initialize()

        query_lower = query.lower()
        results = []

        for doc in self._documents.values():
            score = 0

            # Search in name
            if doc.name and query_lower in doc.name.lower():
                score += 2  # Name matches are more important

            # Search in summary
            if doc.summary and query_lower in doc.summary.lower():
                score += 3  # Summary matches are most important

            # Search in tags
            if doc.tags:
                for tag in doc.tags:
                    if query_lower in tag.lower():
                        score += 1

            # Search in extra fields
            if doc.extra:
                for key, value in doc.extra.items():
                    if isinstance(value, str) and query_lower in value.lower():
                        score += 1

            if score > 0:
                results.append((score, doc))

        # Sort by score (descending) and limit
        results.sort(key=lambda x: x[0], reverse=True)
        return [SearchHit(result=doc) for score, doc in results[:limit]]

    async def delete(self, uri: str) -> bool:
        """Delete a document by URI

        Args:
            uri: Document URI

        Returns:
            True if deleted, False if not found
        """
        if not self._initialized:
            await self.initialize()

        # Validate URI format
        namespace, resource_type, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
            )
        if resource_type != self.resource_type:
            raise ValidationError(
                f"Resource type mismatch: expected {self.resource_type}, got {resource_type}"
            )

        if uri in self._documents:
            del self._documents[uri]
            self._save_index()
            return True

        return False

    async def exists(self, uri: str) -> bool:
        """Check if a document exists

        Args:
            uri: Document URI

        Returns:
            True if exists, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        # Validate URI format
        try:
            namespace, resource_type, _ = parse_document_uri(uri)
            if namespace != self.namespace or resource_type != self.resource_type:
                return False
        except ValidationError:
            return False

        return uri in self._documents
