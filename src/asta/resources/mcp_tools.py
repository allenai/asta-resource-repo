"""MCP Tools for Asta Resource Repository"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP

from .document_store import DocumentStore
from .model import DocumentMetadata, SearchHit
from .exceptions import ValidationError


@dataclass
class AppContext:
    """Application context with initialized dependencies."""

    document_store: DocumentStore


def create_mcp_server(
    document_store: DocumentStore,
    allowed_mime_types: set[str],
) -> FastMCP:
    """Create MCP server with all tools

    Args:
        document_store: Document store instance
        allowed_mime_types: Set of allowed MIME types

    Returns:
        Configured FastMCP server
    """

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        """Manage application lifecycle with async initialization."""
        # Initialize document store on startup
        await document_store.initialize()
        try:
            yield AppContext(document_store=document_store)
        finally:
            # Cleanup on shutdown
            await document_store.close()

    mcp = FastMCP(
        "asta-resource-repository",
        instructions=(
            "This MCP server provides tools for managing document metadata in a local index. "
            "The stored documents are external URIs (e.g., http://) that point to the actual content, "
            "plus a set of user-provided tags and a plain-text description. "
            'Use this tool when the user asks "Asta" to store or retrieve a document. '
            'Use this tool when the users wants to store a document in the "Asta repository", or "in Asta". '
            "Use this tool when the user asks to retrieve an asta:// URI. "
        ),
        lifespan=app_lifespan,
    )

    @mcp.tool()
    async def search_documents(
        query: str, limit: int = 10, search_mode: str = "auto"
    ) -> list[SearchHit]:
        """Search through documents by query

        Searches across document names, summaries, tags, and extra fields.

        Args:
            query: Search query string
            limit: Maximum number of results (default: 10)
            search_mode: Search strategy - "auto" (default), "simple", "keyword", "semantic", or "hybrid"
                - auto: Automatically selects the best available method
                - simple: Basic substring matching (fastest, least accurate)
                - keyword: BM25 keyword search (fast, good for exact matches)
                - semantic: Embedding-based search (best for conceptual queries, requires sentence-transformers)
                - hybrid: Combines keyword + semantic (best overall, requires sentence-transformers)

        Returns:
            List of search hits with document metadata ranked by relevance
        """
        hits = await document_store.search(query, limit, search_mode)
        return hits

    @mcp.tool()
    async def get_document(document_uri: str) -> DocumentMetadata | None:
        """Get document metadata by URI

        Args:
            document_uri: Document URI in format asta://{namespace}/{uuid}

        Returns:
            Document metadata if found, None otherwise
        """
        document = await document_store.get(document_uri)
        return document

    @mcp.tool()
    async def list_documents() -> list[DocumentMetadata]:
        """List all documents in the index

        Returns:
            List of document metadata for all documents
        """
        documents = await document_store.list_docs()
        return documents

    @mcp.tool()
    async def add_document(
        url: str,
        name: str,
        summary: str,
        mime_type: str,
        tags: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> DocumentMetadata:
        """Add document metadata to the index

        Stores metadata about a document without storing the actual content.
        The document content should be accessible at the provided URL.

        Args:
            url: URL where the document content is located (must start with http:// or https://)
            name: Name/title of the document
            summary: Text description of the document (used for search)
            mime_type: MIME type of the document (e.g., application/pdf, text/plain)
            tags: List of tags for categorization (optional, defaults to empty list)
            extra_metadata: Additional metadata fields (author, year, venue, etc.)

        Returns:
            Document metadata with generated URI

        Raises:
            ValidationError: If input validation fails
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValidationError("Document name cannot be empty")

        if not url or not url.strip():
            raise ValidationError("Document URL cannot be empty")

        if not summary or not summary.strip():
            raise ValidationError("Document summary cannot be empty")

        # Validate MIME type
        if mime_type and mime_type not in allowed_mime_types:
            raise ValidationError(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed types: {', '.join(sorted(allowed_mime_types))}"
            )

        if tags is None:
            tags = []

        if extra_metadata is None:
            extra_metadata = {}

        # Create document metadata
        doc_metadata = DocumentMetadata(
            uri="",  # Will be generated by store()
            name=name,
            url=url,
            summary=summary,
            mime_type=mime_type,
            tags=tags,
            extra=extra_metadata,
        )

        # Store and get generated URI
        doc_metadata.uri = await document_store.store(doc_metadata)
        return doc_metadata

    @mcp.tool()
    async def update_document(
        document_uri: str,
        name: str | None = None,
        url: str | None = None,
        summary: str | None = None,
        mime_type: str | None = None,
        tags: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> DocumentMetadata:
        """Update document metadata

        Updates one or more fields of an existing document. Only provided fields will be updated.

        Args:
            document_uri: Document URI in format asta://{namespace}/{uuid}
            name: New document name (optional)
            url: New document URL (optional, must start with http:// or https://)
            summary: New text description (optional)
            mime_type: New MIME type (optional)
            tags: New list of tags (optional, replaces existing tags)
            extra_metadata: New extra metadata (optional, replaces existing extra)

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If document not found or update values are invalid
        """
        # Validate MIME type if provided
        if mime_type is not None and mime_type not in allowed_mime_types:
            raise ValidationError(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed types: {', '.join(sorted(allowed_mime_types))}"
            )

        # Update document
        updated_doc = await document_store.update(
            uri=document_uri,
            name=name,
            url=url,
            summary=summary,
            mime_type=mime_type,
            tags=tags,
            extra=extra_metadata,
        )

        return updated_doc

    @mcp.tool()
    async def add_tags_to_document(
        document_uri: str, tags: list[str]
    ) -> DocumentMetadata:
        """Add tags to a document without replacing existing tags

        Adds new tags to a document while preserving existing tags.
        Duplicate tags are automatically removed.

        Args:
            document_uri: Document URI in format asta://{namespace}/{uuid}
            tags: List of tags to add to the document

        Returns:
            Updated document metadata with combined tags

        Raises:
            ValidationError: If document not found or tags are invalid
        """
        if not tags:
            raise ValidationError("At least one tag must be provided")

        updated_doc = await document_store.add_tags(document_uri, tags)
        return updated_doc

    @mcp.tool()
    async def remove_tags_from_document(
        document_uri: str, tags: list[str]
    ) -> DocumentMetadata:
        """Remove specific tags from a document

        Removes specified tags from a document. Tags that don't exist
        on the document are silently ignored.

        Args:
            document_uri: Document URI in format asta://{namespace}/{uuid}
            tags: List of tags to remove from the document

        Returns:
            Updated document metadata with tags removed

        Raises:
            ValidationError: If document not found
        """
        if not tags:
            raise ValidationError("At least one tag must be provided")

        updated_doc = await document_store.remove_tags(document_uri, tags)
        return updated_doc

    @mcp.tool()
    async def get_documents_by_tags(
        tags: list[str], match_all: bool = False
    ) -> list[DocumentMetadata]:
        """Get documents that have specific tags

        Retrieves all documents that match the specified tag criteria.

        Args:
            tags: List of tags to filter by
            match_all: If True, require all tags; if False, require any tag (default: False)

        Returns:
            List of documents matching the tag criteria

        Examples:
            # Get documents with either "ai" or "ml" tags
            get_documents_by_tags(["ai", "ml"], match_all=False)

            # Get documents that have both "ai" AND "research" tags
            get_documents_by_tags(["ai", "research"], match_all=True)
        """
        if not tags:
            raise ValidationError("At least one tag must be provided")

        documents = await document_store.get_documents_by_tags(tags, match_all)
        return documents

    return mcp
