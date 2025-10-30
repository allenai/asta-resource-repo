"""PostgreSQL-based document store implementation"""

import json
import uuid
from datetime import datetime
from typing import Optional

import asyncpg

from ..model import DocumentMetadata, BinaryDocument, SearchHit, parse_document_uri
from ..exceptions import ValidationError


class PostgresDocumentStore:
    """PostgreSQL-based document storage"""

    def __init__(
        self,
        env_name: str,
        connection_string: str | None = None,
    ):
        """Initialize PostgreSQL document store

        Args:
            connection_string: PostgreSQL connection string (takes precedence if provided)
        """
        self.env_name = env_name
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
            uri: Document URI in format asta://{env_name}/{uuid}

        Returns:
            The UUID part of the URI

        Raises:
            ValidationError: If URI format is invalid or env_name doesn't match
        """
        if not uri or not isinstance(uri, str):
            raise ValidationError(
                f"Document URI must be a non-empty string, got: {uri}"
            )

        env_part, uuid_part = parse_document_uri(uri)

        # Validate env_name matches
        if env_part != self.env_name:
            raise ValidationError(
                f"Document URI env_name '{env_part}' does not match "
                f"document store env_name '{self.env_name}'"
            )

        return uuid_part

    async def store(self, document: BinaryDocument) -> str:
        """Store a document and return its URI in format asta://{env_name}/{uuid}"""
        pool = await self._get_pool()
        doc_uuid = str(uuid.uuid4())

        # Full document URI format: asta://{env_name}/{uuid}
        doc_uri = f"asta://{self.env_name}/{doc_uuid}"

        # Set metadata fields
        document.metadata.uri = doc_uri
        if document.metadata.created_at is None:
            document.metadata.created_at = datetime.now()
        if document.metadata.modified_at is None:
            document.metadata.modified_at = datetime.now()
        if document.metadata.size == 0:
            document.metadata.size = len(document.content)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (
                    uuid, name, mime_type, tags, created_at, modified_at,
                    extra, size, content
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                doc_uuid,  # Store only UUID in database
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
                document.content,
            )

        return doc_uri

    async def get(self, uri: str) -> Optional[BinaryDocument]:
        """Retrieve a document by URI

        Args:
            uri: Document URI in format asta://{env_name}/{uuid}

        Raises:
            ValidationError: If URI format is invalid or env_name doesn't match
        """
        # Validate and extract UUID
        doc_uuid = self._validate_uri_and_extract_uuid(uri)

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT uuid, name, mime_type, tags, created_at, modified_at,
                       extra, size, content
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
                       extra, size, content
                FROM documents
                WHERE
                    LOWER(name) LIKE $1
                    OR LOWER(convert_from(content, 'UTF8')) LIKE $1
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

            # Extract snippet from content
            snippet = None
            try:
                content = row["content"].decode("utf-8")
                query_lower = query.lower()
                idx = content.lower().find(query_lower)
                if idx != -1:
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    snippet = content[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(content):
                        snippet = snippet + "..."
            except (UnicodeDecodeError, AttributeError):
                pass

            results.append(SearchHit(result=metadata, snippet=snippet))

        return results

    async def delete(self, uri: str) -> bool:
        """Delete a document by URI, return True if deleted

        Args:
            uri: Document URI in format asta://{env_name}/{uuid}

        Raises:
            ValidationError: If URI format is invalid or env_name doesn't match
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
            uri: Document URI in format asta://{env_name}/{uuid}

        Raises:
            ValidationError: If URI format is invalid or env_name doesn't match
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
        # row['uuid'] contains just the UUID, construct full URI with asta:// prefix
        doc_uri = f"asta://{self.env_name}/{row['uuid']}"

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
        return BinaryDocument(
            metadata=metadata,
            content=row["content"],
        )
