"""Local YAML-based document metadata index"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import fcntl
import yaml
import logging

from ..model import (
    DocumentMetadata,
    SearchHit,
)
from ..exceptions import ValidationError, DocumentServiceError
from ..utils.short_id import generate_unique_short_id
from ..utils.path_utils import normalize_file_url
from .base import DocumentStore
from .search_cache import SearchCache
from .bm25_ranker import BM25Ranker

# Import Config types for from_config method
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Config

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

    Stores only metadata (no content) in a git-friendly YAML file.
    Designed for single-user, local-only usage with zero external dependencies.
    """

    def __init__(
        self,
        index_path: str = ".asta/documents/index.yaml",
        enable_cache: bool = True,
        enable_embeddings: bool = True,
        bm25_k1: float = 1.2,
        bm25_b: float = 0.75,
        field_weights: Optional[dict[str, float]] = None,
        hybrid_bm25_weight: float = 0.5,
        hybrid_semantic_weight: float = 0.5,
    ):
        """Initialize the local index document store

        Args:
            index_path: Path to the YAML index file (default: ".asta/documents/index.yaml")
            enable_cache: Enable SQLite search cache for fast FTS5 search (default: True)
            enable_embeddings: Enable semantic search with embeddings (default: True, requires sentence-transformers)
            bm25_k1: BM25 term saturation parameter (default: 1.2)
            bm25_b: BM25 length normalization parameter (default: 0.75)
            field_weights: Field weights for ranking (default: {"summary": 3.0, "name": 2.0, "tags": 1.5, "extra": 1.0})
            hybrid_bm25_weight: Weight for BM25 in hybrid search (default: 0.5)
            hybrid_semantic_weight: Weight for semantic search in hybrid search (default: 0.5)
        """
        self.index_path = Path(index_path)
        self._documents: dict[str, DocumentMetadata] = {}  # Keyed by UUID
        self._initialized = False
        self._enable_cache = enable_cache
        self._enable_embeddings = enable_embeddings and EMBEDDINGS_AVAILABLE
        self._search_cache: Optional[SearchCache] = None
        self._embedding_manager: Optional[EmbeddingManager] = None

        # Search configuration
        self._bm25_k1 = bm25_k1
        self._bm25_b = bm25_b
        self._field_weights = field_weights or {
            "summary": 3.0,
            "name": 2.0,
            "tags": 1.5,
            "extra": 1.0,
        }
        self._hybrid_bm25_weight = hybrid_bm25_weight
        self._hybrid_semantic_weight = hybrid_semantic_weight

    @classmethod
    def from_config(cls, config: "Config") -> "LocalIndexDocumentStore":
        """Create LocalIndexDocumentStore from Config object

        Args:
            config: Config object containing index and search settings

        Returns:
            Initialized LocalIndexDocumentStore instance
        """
        return cls(
            index_path=config.index_path,
            enable_cache=config.search.enable_cache,
            enable_embeddings=config.search.enable_embeddings,
            bm25_k1=config.search.bm25_k1,
            bm25_b=config.search.bm25_b,
            field_weights=config.search.field_weights,
            hybrid_bm25_weight=config.search.hybrid_bm25_weight,
            hybrid_semantic_weight=config.search.hybrid_semantic_weight,
        )

    async def initialize(self):
        """Initialize the document store by loading index"""
        if self._initialized:
            return

        # Create parent directory for index file if it doesn't exist
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

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
                    # Use C-based YAML loader for 10-15x faster parsing
                    Loader = (
                        yaml.CSafeLoader
                        if hasattr(yaml, "CSafeLoader")
                        else yaml.SafeLoader
                    )
                    data = yaml.load(f, Loader=Loader) or {}
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

                # Create document metadata
                doc = DocumentMetadata(**doc_data)

                # Store by UUID
                self._documents[doc.uuid] = doc

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
                docs_list = [
                    doc.model_dump(exclude_none=False)
                    for doc in self._documents.values()
                ]

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
            Document URI (full URI with namespace)

        Raises:
            ValidationError: If URL is invalid
        """
        if not self._initialized:
            await self.initialize()

        # Validate URL format
        if not document.url:
            raise ValidationError("Document URL is required")

        # Normalize file URLs to relative paths when within repository
        document.url = normalize_file_url(document.url, self.index_path)

        # Validate URL format
        if "://" in document.url:
            # Has protocol scheme - valid
            pass
        elif Path(document.url).is_absolute():
            # Absolute path without protocol - should have been converted by normalize_file_url
            # If it wasn't, it means it couldn't be processed properly
            raise ValidationError(
                f"Invalid URL format: {document.url}. Absolute paths should include file:// protocol."
            )
        else:
            # Relative path or invalid format
            # Valid relative paths should contain path separators or file extensions
            url_path = Path(document.url)
            if "/" in document.url or "\\" in document.url or url_path.suffix:
                # Looks like a valid relative path (has separators or file extension)
                pass
            else:
                # Doesn't look like a valid path or URL
                raise ValidationError(
                    f"Invalid URL format: {document.url}. Must include a protocol scheme (e.g., http://, https://, file://, s3://, gs://) or be a valid file path."
                )

        # Validate required fields
        if not document.summary:
            raise ValidationError("Document summary is required")

        # Generate short UUID if not provided
        if not document.uuid:
            # Get existing UUIDs for collision checking
            existing_uuids = {doc.uuid for doc in self._documents.values()}
            document.uuid = generate_unique_short_id(existing_uuids)

        # Set timestamps
        now = datetime.now(timezone.utc)
        if not document.created_at:
            document.created_at = now
        document.modified_at = now

        # Store in memory by UUID
        self._documents[document.uuid] = document
        self._save_index()

        return document.uuid

    async def get(self, uuid: str) -> Optional[DocumentMetadata]:
        """Retrieve document metadata by UUID

        Args:
            uuid: Document UUID (10-character alphanumeric)

        Returns:
            Document metadata if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        return self._documents.get(uuid)

    async def list_docs(self) -> list[DocumentMetadata]:
        """List all documents in the index

        Returns:
            List of all document metadata
        """
        if not self._initialized:
            await self.initialize()

        return list(self._documents.values())

    async def search(
        self,
        query: str,
        limit: int = 10,
        search_mode: str = "auto",
        search_field: str = "summary",
    ) -> list[SearchHit]:
        """Search documents with field-specific strategies

        Routes search to appropriate method based on search_field.
        Summary field uses semantic/hybrid search by default.

        Args:
            query: Search query string
            limit: Maximum number of results
            search_mode: Legacy parameter (ignored, kept for backward compatibility)
            search_field: Field to search - "name", "tags", "summary", or "extra" (default: "summary")

        Returns:
            List of search hits ranked by relevance score
        """
        if not self._initialized:
            await self.initialize()

        # Route to field-specific search method
        if search_field == "name":
            return await self._search_by_name(query, limit)
        elif search_field == "tags":
            return await self._search_by_tags(query, limit)
        elif search_field == "extra":
            return await self._search_by_extra(query, limit)
        else:
            # Default: summary field
            return await self._search_by_summary(query, limit)

    async def multi_field_search(
        self,
        field_queries: dict[str, str],
        limit: int = 10,
        combine_mode: str = "intersection",
    ) -> list[SearchHit]:
        """Search multiple fields and combine results

        Executes separate searches for each field and combines results using
        either intersection (documents matching ALL queries) or union
        (documents matching ANY query).

        Args:
            field_queries: Dict mapping field names to query strings
                          e.g., {"summary": "transformers", "tags": "ai,nlp"}
            limit: Maximum number of results to return
            combine_mode: "intersection" (default) or "union"

        Returns:
            List of search hits with combined scores

        Raises:
            ValueError: If field_queries is empty or combine_mode is invalid
        """
        if not self._initialized:
            await self.initialize()

        if not field_queries:
            raise ValueError("field_queries cannot be empty")

        if combine_mode not in ("intersection", "union"):
            raise ValueError(f"Invalid combine_mode: {combine_mode}")

        # Execute search for each field
        all_results: dict[str, list[SearchHit]] = {}
        for field, query in field_queries.items():
            if field == "name":
                results = await self._search_by_name(
                    query, limit=None
                )  # Get all results for combining
            elif field == "tags":
                results = await self._search_by_tags(query, limit=None)
            elif field == "summary":
                results = await self._search_by_summary(query, limit=None)
            elif field == "extra":
                results = await self._search_by_extra(query, limit=None)
            else:
                raise ValueError(f"Invalid field: {field}")

            all_results[field] = results

        # Combine results based on mode
        if combine_mode == "intersection":
            combined = self._combine_intersection(all_results)
        else:  # union
            combined = self._combine_union(all_results)

        # Sort by combined score (descending) and limit
        combined.sort(key=lambda x: x.score, reverse=True)
        return combined[:limit]

    def _combine_intersection(
        self, field_results: dict[str, list[SearchHit]]
    ) -> list[SearchHit]:
        """Combine search results using intersection

        Only returns documents that appear in ALL field results.
        Tags and extra fields act as filters. Sort order determined by:
        1. Summary score (if summary query present)
        2. Name score (if name query present)
        3. Document created_at timestamp

        Args:
            field_results: Dict mapping field names to search results

        Returns:
            List of search hits appearing in all result sets
        """
        if not field_results:
            return []

        # Find documents that appear in all result sets
        # Track scores separately by field type
        doc_matches: dict[str, dict[str, float]] = {}  # uuid -> {field: score}

        for field, hits in field_results.items():
            for hit in hits:
                uuid = hit.result.uuid
                if uuid not in doc_matches:
                    doc_matches[uuid] = {}
                doc_matches[uuid][field] = hit.score

        # Filter to documents appearing in all fields (intersection)
        num_fields = len(field_results)
        combined = []
        for uuid, field_scores in doc_matches.items():
            if len(field_scores) == num_fields:
                # Determine score based on hierarchy:
                # 1. Summary score (semantic relevance)
                # 2. Name score (word matching)
                # 3. Created timestamp (for sorting)
                if "summary" in field_scores:
                    score = field_scores["summary"]
                elif "name" in field_scores:
                    score = field_scores["name"]
                else:
                    # Use timestamp for sorting (tags/extra only)
                    # Convert to float for score field
                    score = float(self._documents[uuid].created_at.timestamp())

                combined.append(SearchHit(result=self._documents[uuid], score=score))

        return combined

    def _combine_union(
        self, field_results: dict[str, list[SearchHit]]
    ) -> list[SearchHit]:
        """Combine search results using union

        Returns all documents from any field result.
        Tags and extra fields act as filters. Sort order determined by:
        1. Summary score (if summary query present)
        2. Name score (if name query present)
        3. Document created_at timestamp

        Args:
            field_results: Dict mapping field names to search results

        Returns:
            List of all unique search hits
        """
        if not field_results:
            return []

        # Track scores by field type for each document
        doc_scores: dict[str, dict[str, float]] = {}  # uuid -> {field: score}

        for field, hits in field_results.items():
            for hit in hits:
                uuid = hit.result.uuid
                if uuid not in doc_scores:
                    doc_scores[uuid] = {}
                # For union, keep the score from each field (documents may match multiple)
                if field not in doc_scores[uuid] or hit.score > doc_scores[uuid][field]:
                    doc_scores[uuid][field] = hit.score

        # Create SearchHit objects with hierarchical scoring
        combined = []
        for uuid, field_scores in doc_scores.items():
            # Determine score based on hierarchy:
            # 1. Summary score (semantic relevance)
            # 2. Name score (word matching)
            # 3. Created timestamp (for sorting)
            if "summary" in field_scores:
                score = field_scores["summary"]
            elif "name" in field_scores:
                score = field_scores["name"]
            else:
                # Use timestamp for sorting (tags/extra only)
                score = float(self._documents[uuid].created_at.timestamp())

            combined.append(SearchHit(result=self._documents[uuid], score=score))

        return combined

    async def _search_by_summary(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Search document summaries using semantic/hybrid search

        Uses the best available search method with automatic fallback:
        1. Hybrid (BM25 + semantic embeddings)
        2. BM25 (keyword relevance ranking)
        3. FTS5 (full-text search)
        4. Simple (in-memory substring matching)

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by relevance score
        """
        # Try hybrid search first (best quality)
        if self._embedding_manager:
            try:
                logger.debug("Using hybrid search (BM25 + semantic)")
                return await self._search_hybrid(query, limit)
            except ImportError:
                logger.debug(
                    "Hybrid search unavailable (missing sentence-transformers)"
                )
            except Exception as e:
                logger.warning(f"Hybrid search failed: {e}")

        # Fall back to BM25
        if self._search_cache and self._search_cache._initialized:
            try:
                logger.debug("Using BM25 search")
                return await self._search_bm25(query, limit)
            except Exception as e:
                logger.debug(f"BM25 search failed: {e}")

            # Fall back to FTS5
            try:
                logger.debug("Using FTS5 search")
                return await self._search_fts5(query, limit)
            except Exception as e:
                logger.debug(f"FTS5 search failed: {e}")

        # Last resort: simple search
        logger.debug("Using simple search (fallback)")
        return await self._search_simple(query, limit)

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
            k1=self._bm25_k1,
            b=self._bm25_b,
            field_weights=self._field_weights,
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
        # Field order in FTS5 table: name, summary, tags, extra
        name_weight = self._field_weights.get("name", 2.0)
        summary_weight = self._field_weights.get("summary", 3.0)
        tags_weight = self._field_weights.get("tags", 1.5)
        extra_weight = self._field_weights.get("extra", 1.0)

        try:
            cursor.execute(
                """
                SELECT uri, bm25(documents_fts, ?, ?, ?, ?) * -1 as score
                FROM documents_fts
                WHERE documents_fts MATCH ?
                ORDER BY bm25(documents_fts, ?, ?, ?, ?)
                LIMIT ?
                """,
                (
                    name_weight,
                    summary_weight,
                    tags_weight,
                    extra_weight,
                    query,
                    name_weight,
                    summary_weight,
                    tags_weight,
                    extra_weight,
                    limit,
                ),
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

    async def _search_by_name(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Simple word matching for name field search

        Case-insensitive substring matching against document names.
        Splits query into words and matches any word against the name.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of search hits ranked by match count
        """
        query_words = query.lower().split()
        results = []

        for doc in self._documents.values():
            if not doc.name:
                continue

            name_lower = doc.name.lower()
            matches = sum(1 for word in query_words if word in name_lower)

            if matches > 0:
                # Score is the fraction of query words that matched
                score = matches / len(query_words)
                results.append((score, doc))

        # Sort by score (descending) and limit
        results.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHit(result=doc, score=float(score)) for score, doc in results[:limit]
        ]

    async def _search_by_tags(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Tag-based search with comma-separated tag matching

        Case-insensitive tag matching. Supports comma-separated tags.
        Returns documents with any matching tags, scored by match percentage.

        Args:
            query: Comma-separated tags to search for
            limit: Maximum number of results

        Returns:
            List of search hits ranked by tag match percentage
        """
        query_tags = {tag.strip().lower() for tag in query.split(",")}
        results = []

        for doc in self._documents.values():
            if not doc.tags:
                continue

            doc_tags = {tag.lower() for tag in doc.tags}
            matching = query_tags & doc_tags

            if matching:
                # Score is the fraction of query tags that matched
                score = len(matching) / len(query_tags)
                results.append((score, doc))

        # Sort by score (descending) and limit
        results.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHit(result=doc, score=float(score)) for score, doc in results[:limit]
        ]

    def _parse_extra_query(self, query: str) -> tuple[str, str, str]:
        """Parse extra metadata query into field, operator, and value

        Supports queries like:
        - .year > 2020
        - .author contains "Smith"
        - .venue == NeurIPS

        Args:
            query: Query string with JSONPath-like syntax

        Returns:
            Tuple of (field, operator, value)

        Raises:
            ValueError: If query format is invalid
        """
        import re

        # Remove leading dot if present
        query = query.strip()
        if query.startswith("."):
            query = query[1:]

        # Try to match: field operator value
        # Operators: contains, >, >=, <, <=, ==
        pattern = r"(\w+)\s*(contains|>=|<=|>|<|==)\s*(.+)"
        match = re.match(pattern, query)

        if not match:
            raise ValueError(
                f"Invalid extra metadata query: {query}. Expected format: '.field operator value'"
            )

        field, operator, value = match.groups()

        # Clean up value (remove quotes if present)
        value = value.strip().strip('"').strip("'")

        return field, operator, value

    def _match_extra_query(
        self, doc: DocumentMetadata, field: str, operator: str, value: str
    ) -> bool:
        """Check if document's extra metadata matches the query

        Args:
            doc: Document to check
            field: Field name in extra metadata
            operator: Comparison operator (contains, >, >=, <, <=, ==)
            value: Value to compare against

        Returns:
            True if document matches query, False otherwise
        """
        if not doc.extra or field not in doc.extra:
            return False

        field_value = doc.extra[field]

        try:
            if operator == "contains":
                # String containment (case-insensitive)
                return value.lower() in str(field_value).lower()
            elif operator in (">", ">=", "<", "<=", "=="):
                # Numeric/string comparison
                # Try to convert to numbers if possible
                try:
                    field_num = float(field_value)
                    value_num = float(value)
                    if operator == ">":
                        return field_num > value_num
                    elif operator == ">=":
                        return field_num >= value_num
                    elif operator == "<":
                        return field_num < value_num
                    elif operator == "<=":
                        return field_num <= value_num
                    elif operator == "==":
                        return field_num == value_num
                except (ValueError, TypeError):
                    # Fall back to string comparison
                    if operator == "==":
                        return str(field_value).lower() == value.lower()
                    else:
                        # Non-numeric comparisons only work with ==
                        return False
        except Exception:
            return False

        return False

    async def _search_by_extra(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Search extra metadata fields with JSONPath-like syntax

        Supports queries like:
        - .year > 2020
        - .author contains "Smith"
        - .venue == NeurIPS

        Args:
            query: JSONPath-like query string
            limit: Maximum number of results

        Returns:
            List of search hits (score=1.0 for all matches)
        """
        try:
            field, operator, value = self._parse_extra_query(query)
        except ValueError as e:
            logger.error(f"Failed to parse extra metadata query: {e}")
            return []

        results = []

        for doc in self._documents.values():
            if self._match_extra_query(doc, field, operator, value):
                results.append(SearchHit(result=doc, score=1.0))

        return results[:limit]

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
            k1=self._bm25_k1,
            b=self._bm25_b,
            field_weights=self._field_weights,
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
            bm25_weight=self._hybrid_bm25_weight,
            semantic_weight=self._hybrid_semantic_weight,
        )[:limit]

        # Convert to SearchHit objects
        search_hits = []
        for uri, score in final_results:
            if uri in self._documents:
                search_hits.append(SearchHit(result=self._documents[uri], score=score))

        return search_hits

    async def delete(self, uuid: str) -> bool:
        """Delete a document by UUID

        Args:
            uuid: Document UUID (10-character alphanumeric)

        Returns:
            True if deleted, False if not found
        """
        if not self._initialized:
            await self.initialize()

        if uuid in self._documents:
            del self._documents[uuid]
            self._save_index()
            return True

        return False

    async def exists(self, uuid: str) -> bool:
        """Check if a document exists

        Args:
            uuid: Document UUID (10-character alphanumeric)

        Returns:
            True if exists, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        return uuid in self._documents

    async def update(
        self,
        uuid: str,
        name: Optional[str] = None,
        url: Optional[str] = None,
        summary: Optional[str] = None,
        mime_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        extra: Optional[dict] = None,
    ) -> DocumentMetadata:
        """Update document metadata

        Args:
            uuid: Document UUID (10-character alphanumeric)
            name: New document name (optional)
            url: New document URL (optional)
            summary: New summary (optional)
            mime_type: New MIME type (optional)
            tags: New tags list (optional)
            extra: New extra metadata (optional)

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If document not found or update values are invalid
        """
        if not self._initialized:
            await self.initialize()

        # Check if document exists
        if uuid not in self._documents:
            raise ValidationError(f"Document not found: {uuid}")

        # Get existing document
        doc = self._documents[uuid]

        # Update fields if provided
        if name is not None:
            if not name.strip():
                raise ValidationError("Document name cannot be empty")
            doc.name = name

        if url is not None:
            if not url.strip():
                raise ValidationError("Document URL cannot be empty")

            # Normalize file URLs to relative paths when within repository
            url = normalize_file_url(url, self.index_path)

            # Validate URL format
            if "://" in url:
                # Has protocol scheme - valid
                pass
            elif Path(url).is_absolute():
                # Absolute path without protocol
                raise ValidationError(
                    f"Invalid URL format: {url}. Absolute paths should include file:// protocol."
                )
            else:
                # Relative path or invalid format
                # Valid relative paths should contain path separators or file extensions
                url_path = Path(url)
                if "/" in url or "\\" in url or url_path.suffix:
                    # Looks like a valid relative path (has separators or file extension)
                    pass
                else:
                    # Doesn't look like a valid path or URL
                    raise ValidationError(
                        f"Invalid URL format: {url}. Must include a protocol scheme (e.g., http://, https://, file://) or be a valid file path."
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

    async def add_tags(self, uuid: str, tags: list[str]) -> DocumentMetadata:
        """Add tags to a document without replacing existing ones

        Args:
            uuid: Document UUID (10-character alphanumeric)
            tags: List of tags to add

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If document not found or tags are invalid
        """
        if not self._initialized:
            await self.initialize()

        # Check if document exists
        if uuid not in self._documents:
            raise ValidationError(f"Document not found: {uuid}")

        # Get existing document
        doc = self._documents[uuid]

        # Add new tags without duplicates
        existing_tags = set(doc.tags or [])
        new_tags = set(tags)
        doc.tags = sorted(existing_tags | new_tags)

        # Update modified timestamp
        doc.modified_at = datetime.now(timezone.utc)

        # Save to disk
        self._save_index()

        return doc

    async def remove_tags(self, uuid: str, tags: list[str]) -> DocumentMetadata:
        """Remove specific tags from a document

        Args:
            uuid: Document UUID (10-character alphanumeric)
            tags: List of tags to remove

        Returns:
            Updated document metadata

        Raises:
            ValidationError: If document not found
        """
        if not self._initialized:
            await self.initialize()

        # Check if document exists
        if uuid not in self._documents:
            raise ValidationError(f"Document not found: {uuid}")

        # Get existing document
        doc = self._documents[uuid]

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
