"""Abstract base class for document storage backends"""

from abc import ABC, abstractmethod
from typing import Optional

from ..model import DocumentMetadata, SearchHit


class DocumentStore(ABC):
    """Abstract base class for document storage implementations

    All document store backends must implement this interface to ensure
    consistent API across different storage backends (PostgreSQL, GitHub, S3, etc.)
    """

    @abstractmethod
    async def initialize(self):
        """Initialize the document store (connections, pools, caches, etc.)

        This method should be called before any other operations.
        It should be idempotent - calling it multiple times should be safe.
        """
        pass

    @abstractmethod
    async def close(self):
        """Close connections and cleanup resources

        This method should be called when the document store is no longer needed.
        It should be idempotent - calling it multiple times should be safe.
        """
        pass

    @abstractmethod
    async def __aenter__(self):
        """Async context manager entry - initialize the store"""
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close the store"""
        pass

    @abstractmethod
    async def store(self, document: DocumentMetadata) -> str:
        """Store document metadata and return its URI

        Args:
            document: The document metadata to store (no content, only metadata)

        Returns:
            The document URI in format asta://{namespace}/{resource_type}/{uuid}

        Raises:
            ValidationError: If document metadata is invalid
            DocumentServiceError: If storage operation fails
        """
        pass

    @abstractmethod
    async def get(self, uri: str) -> Optional[DocumentMetadata]:
        """Retrieve document metadata by URI

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Returns:
            The document metadata if found, None otherwise

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
            DocumentServiceError: If retrieval operation fails
        """
        pass

    @abstractmethod
    async def list_docs(self) -> list[DocumentMetadata]:
        """List all documents in the index

        Returns:
            List of document metadata for all documents

        Raises:
            DocumentServiceError: If list operation fails
        """
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Search documents by query

        Args:
            query: Search query string
            limit: Maximum number of results to return (default: 10)

        Returns:
            List of search hits for matching documents

        Raises:
            DocumentServiceError: If search operation fails
        """
        pass

    @abstractmethod
    async def delete(self, uri: str) -> bool:
        """Delete a document by URI

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Returns:
            True if document was deleted, False if not found

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
            DocumentServiceError: If delete operation fails
        """
        pass

    @abstractmethod
    async def exists(self, uri: str) -> bool:
        """Check if a document exists

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Returns:
            True if document exists, False otherwise

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
        """
        pass
