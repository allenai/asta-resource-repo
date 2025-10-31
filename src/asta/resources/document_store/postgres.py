"""PostgreSQL-based document store implementation"""

import json
import uuid
from datetime import datetime
from typing import Optional

import asyncpg

from ..model import (
    DocumentMetadata,
    BinaryDocument,
    SearchHit,
    parse_document_uri,
    construct_document_uri,
)
from ..exceptions import ValidationError


class PostgresDocumentStore:
    """PostgreSQL-based document storage"""

    def __init__(
        self,
        namespace: str,
        connection_string: str | None = None,
    ):
        """Initialize PostgreSQL document store

        Args:
            namespace: Namespace identifier for URIs
            connection_string: PostgreSQL connection string (takes precedence if provided)
        """
        self.namespace = namespace
        self.resource_type = "document"
        self.connection_string = connection_string
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def pool(self) -> Optional[asyncpg.Pool]:
        """Get the connection pool"""
        return self._pool

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.connection_string)
        return self._pool

    async def initialize(self):
        """Initialize the database connection pool"""
        await self._get_pool()

    async def close(self):
        """Close the connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self):
        """Initialize database schema"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the connection pool"""
        await self.close()

    def _validate_uri_and_extract_uuid(self, uri: str) -> str:
        """Validate document URI format and extract UUID

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Returns:
            The UUID part of the URI

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
        """
        if not uri or not isinstance(uri, str):
            raise ValidationError(
                f"Document URI must be a non-empty string, got: {uri}"
            )

        namespace_part, resource_type_part, uuid_part = parse_document_uri(uri)

        # Validate namespace matches
        if namespace_part != self.namespace:
            raise ValidationError(
                f"Unknown URI namespace '{namespace_part}'"
                f" (expected '{self.namespace}')"
            )

        # Validate resource_type matches
        if resource_type_part != self.resource_type:
            raise ValidationError(
                f"Unknown resource_type '{resource_type_part}'"
                f" (expected '{self.resource_type}')"
            )

        return uuid_part

    async def store(self, document: BinaryDocument) -> str:
        """Store a document and return its URI in format asta://{namespace}/{resource_type}/{uuid}"""
        pool = await self._get_pool()
        doc_uuid = str(uuid.uuid4())

        # Construct full document URI (uses configured resource_type)
        doc_uri = construct_document_uri(self.namespace, self.resource_type, doc_uuid)

        # Set metadata fields
        document.metadata.uri = doc_uri
        if document.metadata.created_at is None:
            document.metadata.created_at = datetime.now()
        if document.metadata.modified_at is None:
            document.metadata.modified_at = datetime.now()
        if document.metadata.size == 0:
            document.metadata.size = len(document.content)

        # Store content in appropriate column based on type
        if document.metadata.is_binary:
            binary_content = document.content
            text_content = None
        else:
            binary_content = None
            text_content = document.content.decode("utf-8")

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (
                    uuid, name, mime_type, tags, created_at, modified_at,
                    extra, size, binary_content, text_content
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                doc_uuid,  # Store UUID in database
                document.metadata.name,
                document.metadata.mime_type,
                json.dumps(document.metadata.tags) if document.metadata.tags else None,
                document.metadata.created_at,
                document.metadata.modified_at,
                (
                    json.dumps(document.metadata.extra)
                    if document.metadata.extra
                    else None
                ),
                document.metadata.size,
                binary_content,
                text_content,
            )

        return doc_uri

    async def get(self, uri: str) -> Optional[BinaryDocument]:
        """Retrieve a document by URI

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
        """
        # Validate and extract UUID
        doc_uuid = self._validate_uri_and_extract_uuid(uri)

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT uuid, name, mime_type, tags, created_at, modified_at,
                       extra, size, binary_content, text_content
                FROM documents
                WHERE uuid = $1
                """,
                doc_uuid,
            )

        if row is None:
            return None

        return self._row_to_raw_document(row)

    async def list_docs(self) -> list[DocumentMetadata]:
        """List all documents"""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT uuid, name, mime_type, tags, created_at, modified_at,
                       extra, size
                FROM documents
                ORDER BY created_at DESC
                """
            )

        return [self._row_to_metadata(row) for row in rows]

    async def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Search documents by query"""
        pool = await self._get_pool()
        query_pattern = f"%{query.lower()}%"

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT uuid, name, mime_type, tags, created_at, modified_at,
                       extra, size, binary_content, text_content
                FROM documents
                WHERE
                    LOWER(name) LIKE $1
                    OR LOWER(text_content) LIKE $1
                    OR LOWER(convert_from(binary_content, 'UTF8')) LIKE $1
                    OR LOWER(extra::text) LIKE $1
                    OR tags::text ILIKE $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                query_pattern,
                limit,
            )

        results = []
        for row in rows:
            metadata = self._row_to_metadata(row)
            results.append(SearchHit(result=metadata))

        return results

    async def delete(self, uri: str) -> bool:
        """Delete a document by URI, return True if deleted

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
        """
        # Validate and extract UUID
        doc_uuid = self._validate_uri_and_extract_uuid(uri)

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE uuid = $1",
                doc_uuid,
            )

        # result is like "DELETE 1" or "DELETE 0"
        return result.endswith("1")

    async def exists(self, uri: str) -> bool:
        """Check if a document exists

        Args:
            uri: Document URI in format asta://{namespace}/{resource_type}/{uuid}

        Raises:
            ValidationError: If URI format is invalid or namespace/resource_type doesn't match
        """
        # Validate and extract UUID
        doc_uuid = self._validate_uri_and_extract_uuid(uri)

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM documents WHERE uuid = $1",
                doc_uuid,
            )

        return row is not None

    def _row_to_metadata(self, row: asyncpg.Record) -> DocumentMetadata:
        """Convert database row to DocumentMetadata"""
        # Construct full URI from namespace, resource_type, and UUID
        doc_uri = construct_document_uri(
            self.namespace, self.resource_type, row["uuid"]
        )

        return DocumentMetadata(
            uri=doc_uri,
            name=row["name"],
            mime_type=row["mime_type"],
            tags=json.loads(row["tags"]) if row["tags"] else None,
            created_at=row["created_at"],
            modified_at=row["modified_at"],
            extra=json.loads(row["extra"]) if row["extra"] else None,
            size=row["size"],
        )

    def _row_to_raw_document(self, row: asyncpg.Record) -> BinaryDocument:
        """Convert database row to RawDocument"""
        metadata = self._row_to_metadata(row)

        # Get content from appropriate column based on resource_type
        if row["text_content"] is not None:  # text
            content = row["text_content"].encode("utf-8")
        else:  # binary
            content = row["binary_content"]

        return BinaryDocument(
            metadata=metadata,
            content=content,
        )
