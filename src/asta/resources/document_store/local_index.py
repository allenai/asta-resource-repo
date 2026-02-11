"""Local YAML-based document metadata index"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import fcntl
import yaml
import logging

from ..model import (
    DocumentMetadata,
    SearchHit,
    construct_document_uri,
    parse_document_uri,
)
from ..exceptions import ValidationError, DocumentServiceError
from .base import DocumentStore
from .search_cache import SearchCache
from .bm25_ranker import BM25Ranker

# Optional embedding imports
try:
    from .embeddings import EmbeddingManager, EMBEDDINGS_AVAILABLE
    from .hybrid_search import HybridSearchRanker
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    EmbeddingManager = None
    HybridSearchRanker = None

logger = logging.getLogger(__name__)


class LocalIndexDocumentStore(DocumentStore):
    """Document store that maintains a local YAML index of document metadata

    Stores only metadata (no content) in a git-friendly YAML file at .asta/documents/index.yaml
    Designed for single-user, local-only usage with zero external dependencies.
    """

    def __init__(
        self,
        index_path: str = ".asta/documents/index.yaml",
        enable_cache: bool = True,
        enable_embeddings: bool = True,
    ):
        """Initialize the local index document store

        Args:
            index_path: Path to the YAML index file (default: ".asta/documents/index.yaml")
            enable_cache: Enable SQLite search cache for fast FTS5 search (default: True)
            enable_embeddings: Enable semantic search with embeddings (default: True, requires sentence-transformers)

        Note: Namespace is automatically derived from index location
        """
        self.index_path = Path(index_path)
        self.namespace: Optional[str] = None  # Set during initialize()
        self._documents: dict[str, DocumentMetadata] = {}
        self._initialized = False
        self._enable_cache = enable_cache
        self._enable_embeddings = enable_embeddings and EMBEDDINGS_AVAILABLE
        self._search_cache: Optional[SearchCache] = None
        self._embedding_manager: Optional[EmbeddingManager] = None

    async def initialize(self):
        """Initialize the document store by deriving namespace and loading index"""
        if self._initialized:
            return

        # Create .asta/documents directory if it doesn't exist
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # Derive namespace from index file location
        from ..utils.git_namespace import derive_namespace

        self.namespace = derive_namespace(self.index_path)

        # Create empty index file if it doesn't exist
        if not self.index_path.exists():
            self._save_index({"version": "1.0", "documents": []})

        # Load existing index
        self._load_index()

        # Initialize search cache if enabled
        if self._enable_cache:
            try:
                self._search_cache = SearchCache(self.index_path)
                self._search_cache.initialize()
                logger.info("Search cache initialized")

                # Initialize embedding manager if enabled
                if self._enable_embeddings and EMBEDDINGS_AVAILABLE:
                    try:
                        self._embedding_manager = EmbeddingManager(
                            self._search_cache.conn
                        )
                        logger.info("Embedding manager initialized")
                    except Exception as e:
                        logger.warning(
                            f"Failed to initialize embeddings: {e}. Semantic search unavailable."
                        )
                        self._embedding_manager = None
                elif self._enable_embeddings and not EMBEDDINGS_AVAILABLE:
                    logger.info(
                        "Embeddings disabled: sentence-transformers not available."
                    )

            except Exception as e:
                logger.warning(
                    f"Failed to initialize search cache: {e}. Falling back to simple search."
                )
                self._search_cache = None

        self._initialized = True

    async def close(self):
        """Close the document store"""
        # Close search cache if initialized
        if self._search_cache:
            self._search_cache.close()
            self._search_cache = None

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
        if "://" not in document.url:
            raise ValidationError(
                f"Invalid URL format: {document.url}. Must include a protocol scheme (e.g., http://, https://, file://, s3://, gs://)"
            )

        # Validate required fields
        if not document.summary:
            raise ValidationError("Document summary is required")

        # Generate UUID and URI if not provided
        if not document.uri:
            doc_uuid = str(uuid.uuid4())
            document.uri = construct_document_uri(self.namespace, doc_uuid)

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
        namespace, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
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

    async def search(
        self, query: str, limit: int = 10, search_mode: str = "auto"
    ) -> list[SearchHit]:
        """Search documents with multiple strategies

        Searches across name, summary, tags, and extra fields using the
        specified search mode. Auto mode selects the best available method.

        Args:
            query: Search query string
            limit: Maximum number of results
            search_mode: Search strategy - "auto", "simple", "keyword", "bm25", "semantic", or "hybrid" (default: "auto")

        Returns:
            List of search hits ranked by relevance score
        """
        if not self._initialized:
            await self.initialize()

        # Determine search mode
        if search_mode == "auto":
            search_mode = self._determine_search_mode()

        # Execute search based on mode with fallback logic
        try:
            if search_mode == "hybrid":
                return await self._search_hybrid(query, limit)
            elif search_mode == "semantic":
                return await self._search_semantic(query, limit)
            elif search_mode in ["keyword", "bm25"]:
                return await self._search_bm25(query, limit)
            elif search_mode == "fts5":
                return await self._search_fts5(query, limit)
            else:
                return await self._search_simple(query, limit)
        except ImportError as e:
            logger.warning(
                f"{search_mode} search not available: {e}. Falling back to keyword search."
            )
            if search_mode in ["hybrid", "semantic"]:
                # Fallback to keyword if embeddings not available
                return await self._search_bm25(query, limit)
            else:
                # Fallback to simple search
                return await self._search_simple(query, limit)

    def _determine_search_mode(self) -> str:
        """Auto-detect best search mode based on available features

        Returns:
            Search mode string ("hybrid", "bm25", "fts5", or "simple")
        """
        if self._search_cache and self._search_cache._initialized:
            # Check if embeddings are available
            if self._embedding_manager:
                return "hybrid"

            # Check if BM25 index is available
            try:
                cursor = self._search_cache.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM collection_stats")
                if cursor.fetchone()[0] > 0:
                    return "bm25"
            except Exception:
                pass
            return "fts5"
        return "simple"

    async def _search_bm25(self, query: str, limit: int) -> list[SearchHit]:
        """BM25-based search with TF-IDF weighting

        Uses BM25 ranking algorithm for relevance scoring.
        Provides better relevance than simple FTS5 ranking.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by BM25 score
        """
        # Ensure cache is synced
        await self._search_cache.ensure_synced(self._documents)

        # Create BM25 ranker
        ranker = BM25Ranker(
            self._search_cache.conn,
            k1=1.2,  # TODO: Get from config
            b=0.75,  # TODO: Get from config
            field_weights={
                "name": 2.0,
                "summary": 3.0,
                "tags": 1.5,
                "extra": 1.0,
            },
        )

        try:
            # Get ranked results
            ranked_docs = ranker.rank(query, limit)

            # Convert to SearchHit objects
            results = []
            for uri, score in ranked_docs:
                if uri in self._documents:
                    results.append(SearchHit(result=self._documents[uri], score=score))

            return results

        except Exception as e:
            logger.warning(f"BM25 search failed: {e}. Falling back to FTS5.")
            return await self._search_fts5(query, limit)

    async def _search_fts5(self, query: str, limit: int) -> list[SearchHit]:
        """FTS5-based search with field boosting

        Uses SQLite FTS5 for fast indexed full-text search.
        Field weights: summary=3, name=2, tags=1.5, extra=1

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by FTS5 BM25 score
        """
        # Ensure cache is synced
        await self._search_cache.ensure_synced(self._documents)

        cursor = self._search_cache.conn.cursor()

        # Build FTS5 query with field boosting
        # FTS5 uses bm25() function for ranking (negative values, lower is better)
        # We multiply by -1 to get positive scores where higher is better
        try:
            cursor.execute(
                """
                SELECT uri, bm25(documents_fts, 2.0, 3.0, 1.5, 1.0) * -1 as score
                FROM documents_fts
                WHERE documents_fts MATCH ?
                ORDER BY bm25(documents_fts, 2.0, 3.0, 1.5, 1.0)
                LIMIT ?
                """,
                (query, limit),
            )

            results = []
            for row in cursor.fetchall():
                uri = row["uri"]
                score = row["score"]
                if uri in self._documents:
                    results.append(SearchHit(result=self._documents[uri], score=score))

            return results

        except Exception as e:
            logger.warning(f"FTS5 search failed: {e}. Falling back to simple search.")
            return await self._search_simple(query, limit)

    async def _search_simple(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Simple in-memory substring search (fallback method)

        Searches across name, summary, tags, and extra fields using
        simple substring matching.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by number of matches
        """
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
        return [
            SearchHit(result=doc, score=float(score)) for score, doc in results[:limit]
        ]

    async def _search_semantic(self, query: str, limit: int) -> list[SearchHit]:
        """Pure semantic search using embeddings

        Uses sentence-transformers to embed the query and finds similar documents
        using cosine similarity.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by semantic similarity
        """
        if not self._embedding_manager:
            raise ImportError("Semantic search not available.")

        # Ensure all documents have embeddings
        await self._embedding_manager.ensure_embeddings(self._documents)

        # Generate query embedding
        query_embedding = self._embedding_manager.generate_embedding(query)

        # Search for similar documents
        results = self._embedding_manager.vector_search(query_embedding, limit)

        # Convert to SearchHit objects
        search_hits = []
        for uri, score in results:
            if uri in self._documents:
                search_hits.append(SearchHit(result=self._documents[uri], score=score))

        return search_hits

    async def _search_hybrid(self, query: str, limit: int) -> list[SearchHit]:
        """Hybrid search combining BM25 and semantic similarity

        Uses Reciprocal Rank Fusion (RRF) to combine BM25 keyword search
        and semantic similarity search for optimal results.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by hybrid score
        """
        if not self._embedding_manager:
            raise ImportError("Hybrid search not available.")

        # Ensure cache and embeddings ready
        await self._search_cache.ensure_synced(self._documents)
        await self._embedding_manager.ensure_embeddings(self._documents)

        # Get BM25 results
        bm25_ranker = BM25Ranker(
            self._search_cache.conn,
            k1=1.2,  # TODO: Get from config
            b=0.75,  # TODO: Get from config
        )
        bm25_results = bm25_ranker.rank(query, limit * 2)  # Get more for fusion

        # Get semantic results
        query_embedding = self._embedding_manager.generate_embedding(query)
        semantic_results = self._embedding_manager.vector_search(
            query_embedding, limit * 2
        )

        # Combine with Reciprocal Rank Fusion
        hybrid_ranker = HybridSearchRanker()
        final_results = hybrid_ranker.reciprocal_rank_fusion(
            bm25_results,
            semantic_results,
            bm25_weight=0.5,  # TODO: Get from config
            semantic_weight=0.5,  # TODO: Get from config
        )[:limit]

        # Convert to SearchHit objects
        search_hits = []
        for uri, score in final_results:
            if uri in self._documents:
                search_hits.append(SearchHit(result=self._documents[uri], score=score))

        return search_hits

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
        namespace, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
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
            namespace, _ = parse_document_uri(uri)
            if namespace != self.namespace:
                return False
        except ValidationError:
            return False

        return uri in self._documents

    async def update(
        self,
        uri: str,
        name: Optional[str] = None,
        url: Optional[str] = None,
        summary: Optional[str] = None,
        mime_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        extra: Optional[dict] = None,
    ) -> DocumentMetadata:
        """Update document metadata

        Args:
            uri: Document URI
            name: New document name (optional)
            url: New document URL (optional)
            summary: New summary (optional)
            mime_type: New MIME type (optional)
            tags: New tags list (optional)
            extra: New extra metadata (optional)

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If URI not found or update values are invalid
        """
        if not self._initialized:
            await self.initialize()

        # Validate URI format
        namespace, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
            )

        # Check if document exists
        if uri not in self._documents:
            raise ValidationError(f"Document not found: {uri}")

        # Get existing document
        doc = self._documents[uri]

        # Update fields if provided
        if name is not None:
            if not name.strip():
                raise ValidationError("Document name cannot be empty")
            doc.name = name

        if url is not None:
            if not url.strip():
                raise ValidationError("Document URL cannot be empty")
            if "://" not in url:
                raise ValidationError(
                    f"Invalid URL format: {url}. Must include a protocol scheme (e.g., http://, https://, file://)"
                )
            doc.url = url

        if summary is not None:
            if not summary.strip():
                raise ValidationError("Document summary cannot be empty")
            doc.summary = summary

        if mime_type is not None:
            doc.mime_type = mime_type

        if tags is not None:
            doc.tags = tags

        if extra is not None:
            doc.extra = extra

        # Update modified timestamp
        doc.modified_at = datetime.now(timezone.utc)

        # Save to disk
        self._save_index()

        return doc

    async def add_tags(self, uri: str, tags: list[str]) -> DocumentMetadata:
        """Add tags to a document without replacing existing ones

        Args:
            uri: Document URI
            tags: List of tags to add

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If URI not found or tags are invalid
        """
        if not self._initialized:
            await self.initialize()

        # Validate URI format
        namespace, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
            )

        # Check if document exists
        if uri not in self._documents:
            raise ValidationError(f"Document not found: {uri}")

        # Get existing document
        doc = self._documents[uri]

        # Add new tags without duplicates
        existing_tags = set(doc.tags or [])
        new_tags = set(tags)
        doc.tags = sorted(existing_tags | new_tags)

        # Update modified timestamp
        doc.modified_at = datetime.now(timezone.utc)

        # Save to disk
        self._save_index()

        return doc

    async def remove_tags(self, uri: str, tags: list[str]) -> DocumentMetadata:
        """Remove specific tags from a document

        Args:
            uri: Document URI
            tags: List of tags to remove

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If URI not found
        """
        if not self._initialized:
            await self.initialize()

        # Validate URI format
        namespace, _ = parse_document_uri(uri)
        if namespace != self.namespace:
            raise ValidationError(
                f"Namespace mismatch: expected {self.namespace}, got {namespace}"
            )

        # Check if document exists
        if uri not in self._documents:
            raise ValidationError(f"Document not found: {uri}")

        # Get existing document
        doc = self._documents[uri]

        # Remove specified tags
        existing_tags = set(doc.tags or [])
        tags_to_remove = set(tags)
        doc.tags = sorted(existing_tags - tags_to_remove)

        # Update modified timestamp
        doc.modified_at = datetime.now(timezone.utc)

        # Save to disk
        self._save_index()

        return doc

    async def get_documents_by_tags(
        self, tags: list[str], match_all: bool = False
    ) -> list[DocumentMetadata]:
        """Get all documents that have specific tags

        Args:
            tags: List of tags to filter by
            match_all: If True, require all tags; if False, require any tag (default: False)

        Returns:
            List of documents matching the tag criteria
        """
        if not self._initialized:
            await self.initialize()

        filter_tags = set(tags)
        results = []

        for doc in self._documents.values():
            if not doc.tags:
                continue

            doc_tags = set(doc.tags)

            if match_all:
                # All specified tags must be present
                if filter_tags.issubset(doc_tags):
                    results.append(doc)
            else:
                # Any of the specified tags must be present
                if filter_tags & doc_tags:
                    results.append(doc)

        return results
