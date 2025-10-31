"""MCP Tools for Asta Resource Repository"""

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from .document_store import PostgresDocumentStore
from .model import DocumentMetadata, Document, SearchHit
from .exceptions import InvalidMimeTypeError, DocumentTooLargeError, ValidationError


@dataclass
class AppContext:
    """Application context with initialized dependencies."""

    document_store: PostgresDocumentStore


def create_mcp_server(
    document_store: PostgresDocumentStore,
    max_file_size_bytes: int,
    allowed_mime_types: set[str],
) -> FastMCP:
    """Create MCP server with all tools

    Args:
        document_store: Document store instance
        max_file_size_bytes: Maximum file size in bytes
        allowed_mime_types: Set of allowed MIME types

    Returns:
        Configured FastMCP server
    """

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        """Manage application lifecycle with async initialization."""
        # Initialize document store connection pool on startup
        await document_store.initialize()
        try:
            yield AppContext(document_store=document_store)
        finally:
            # Cleanup on shutdown
            await document_store.close()

    mcp = FastMCP(
        "asta-resource-repository",
        instructions=(
            f"This MCP server provides tools for managing documents in the Asta Resource Repository. "
            f"Use these tools to handle URIs of the form asta://{document_store.namespace}/{document_store.resource_type}/{{document_id}}."
        ),
        lifespan=app_lifespan,
    )

    @mcp.tool()
    async def search_documents(query: str, limit: int = 10) -> list[SearchHit]:
        """Search through user documents

        Args:
            query: Search query string
            limit: Maximum number of results (default: 10)

        Returns:
            List of search hits with document metadata and snippets
        """
        hits = await document_store.search(query, limit)
        return hits

    @mcp.tool()
    async def get_document(document_uri: str) -> Document | None:
        """Get a specific document by URI

        Args:
            document_uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Returns:
            Document object with metadata and content, or None if not found
        """
        document = await document_store.get(document_uri)
        return document.to_serializable() if document else None

    @mcp.tool()
    async def list_documents() -> list[DocumentMetadata]:
        """List all available documents

        Returns:
            List of document metadata for all documents
        """
        documents = await document_store.list_docs()
        return documents

    @mcp.tool()
    async def upload_document(
        content: str,
        filename: str,
        mime_type: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> DocumentMetadata:
        """Upload a new document to the collection

        Args:
            content: Document content (UTF-8 string for text files, base64 for binary files)
            filename: Name of the document file
            mime_type: MIME type of the document (must be application/json, application/pdf, or text/plain)
            extra_metadata: Additional metadata for the document (title, author, tags, category, description, etc.)

        Returns:
            Document metadata for the uploaded document

        Raises:
            InvalidMimeTypeError: If the MIME type is not supported
            DocumentTooLargeError: If the document exceeds the maximum allowed size
            ValidationError: If input validation fails
        """
        # Validate inputs
        if not filename or not filename.strip():
            raise ValidationError("Filename cannot be empty")

        if not content:
            raise ValidationError("Content cannot be empty")

        # Validate MIME type
        if mime_type not in allowed_mime_types:
            raise InvalidMimeTypeError(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed types: {', '.join(sorted(allowed_mime_types))}"
            )

        if extra_metadata is None:
            extra_metadata = {}

        # Create document metadata first to check if binary
        doc_metadata = DocumentMetadata(
            uri="",
            name=filename,
            mime_type=mime_type,
            extra=extra_metadata,
            created_at=datetime.now(),
        )

        # Validate file size based on content type
        try:
            if doc_metadata.is_binary:
                # Binary files: content is base64, decode to check size
                content_bytes = base64.b64decode(content)
            else:
                # Text files: content is UTF-8 string, encode to check size
                content_bytes = content.encode("utf-8")

            content_size = len(content_bytes)

            if content_size > max_file_size_bytes:
                max_mb = max_file_size_bytes / (1024 * 1024)
                actual_mb = content_size / (1024 * 1024)
                raise DocumentTooLargeError(
                    f"Document size ({actual_mb:.2f} MB) exceeds "
                    f"maximum allowed size ({max_mb:.0f} MB)"
                )
        except Exception as e:
            if isinstance(
                e, (DocumentTooLargeError, InvalidMimeTypeError, ValidationError)
            ):
                raise
            if doc_metadata.is_binary:
                raise ValidationError(f"Invalid base64 content: {str(e)}")
            else:
                raise ValidationError(f"Invalid UTF-8 content: {str(e)}")

        # Create and store document
        document = Document(
            metadata=doc_metadata,
            content=content,
        ).to_binary()

        doc_metadata.uri = await document_store.store(document)
        return doc_metadata

    return mcp
