"""SQLite-based search cache for fast full-text search"""

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class SearchCache:
    """Manages SQLite cache for fast search operations

    The cache is automatically synced when the YAML index changes.
    Uses FTS5 for full-text search with field boosting.
    """

    def __init__(self, index_path: Path, cache_filename: str = "search.db"):
        """Initialize search cache

        Args:
            index_path: Path to YAML index file
            cache_filename: Name of SQLite cache file (default: "search.db")
        """
        self.index_path = index_path
        # Store cache in .cache directory alongside index file
        cache_dir = index_path.parent / ".cache"
        self.cache_path = cache_dir / cache_filename
        self.conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    def initialize(self):
        """Initialize the SQLite cache"""
        if self._initialized:
            return

        # Create cache directory if needed
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite database
        self.conn = sqlite3.connect(str(self.cache_path))
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        # Initialize schema
        self._init_schema()
        self._initialized = True

    def _init_schema(self):
        """Initialize database schema from SQL file"""
        schema_path = Path(__file__).parent / "schema.sql"

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        # Execute schema creation
        self.conn.executescript(schema_sql)
        self.conn.commit()

    def _calculate_yaml_hash(self) -> str:
        """Calculate SHA256 hash of YAML index file

        Returns:
            Hex string of SHA256 hash
        """
        if not self.index_path.exists():
            return ""

        hasher = hashlib.sha256()
        with open(self.index_path, "rb") as f:
            # Read in chunks for memory efficiency
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)

        return hasher.hexdigest()

    def _get_stored_hash(self) -> Optional[str]:
        """Get stored YAML hash from sync_metadata table

        Returns:
            Stored hash or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM sync_metadata WHERE key = 'yaml_hash'")
        row = cursor.fetchone()
        return row["value"] if row else None

    def _store_hash(self, hash_value: str):
        """Store YAML hash in sync_metadata table

        Args:
            hash_value: Hash to store
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO sync_metadata (key, value, updated_at)
            VALUES ('yaml_hash', ?, CURRENT_TIMESTAMP)
            """,
            (hash_value,),
        )
        self.conn.commit()

    def is_cache_stale(self) -> bool:
        """Check if cache is stale (YAML changed since last sync)

        Returns:
            True if cache needs rebuild, False otherwise
        """
        current_hash = self._calculate_yaml_hash()
        stored_hash = self._get_stored_hash()

        return current_hash != stored_hash

    async def ensure_synced(self, documents: dict):
        """Ensure cache is synced with YAML index

        Rebuilds cache if YAML has changed.

        Args:
            documents: Dictionary of URI -> DocumentMetadata from YAML
        """
        if not self._initialized:
            self.initialize()

        if self.is_cache_stale():
            logger.info("YAML index changed, rebuilding search cache")
            await self._rebuild_cache(documents)

    async def _rebuild_cache(self, documents: dict):
        """Rebuild entire cache from documents dictionary

        Args:
            documents: Dictionary of URI -> DocumentMetadata
        """
        # Clear existing data
        self.conn.execute("DELETE FROM documents")
        self.conn.execute("DELETE FROM documents_fts")
        self.conn.commit()

        # Insert all documents
        for uri, doc in documents.items():
            # Serialize tags as JSON
            tags_json = json.dumps(doc.tags) if doc.tags else "[]"

            # Flatten extra fields for search
            extra_text = ""
            if doc.extra:
                extra_text = " ".join(
                    str(v) for v in doc.extra.values() if v is not None
                )
            extra_json = json.dumps(doc.extra) if doc.extra else "{}"

            # Flatten tags for FTS5 (convert list to space-separated string)
            tags_text = " ".join(doc.tags) if doc.tags else ""

            # Insert into documents table
            self.conn.execute(
                """
                INSERT INTO documents (
                    uri, name, url, summary, mime_type, tags, extra,
                    created_at, modified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uri,
                    doc.name,
                    doc.url,
                    doc.summary,
                    doc.mime_type,
                    tags_json,
                    extra_json,
                    doc.created_at.isoformat() if doc.created_at else None,
                    doc.modified_at.isoformat() if doc.modified_at else None,
                ),
            )

            # Insert into FTS5 table
            self.conn.execute(
                """
                INSERT INTO documents_fts (uri, name, summary, tags, extra_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    uri,
                    doc.name or "",
                    doc.summary or "",
                    tags_text,
                    extra_text,
                ),
            )

        self.conn.commit()

        # Build BM25 index
        await self._rebuild_bm25_index(documents)

        # Store new hash
        current_hash = self._calculate_yaml_hash()
        self._store_hash(current_hash)

        logger.info(f"Search cache rebuilt with {len(documents)} documents")

    def close(self):
        """Close SQLite connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
        self._initialized = False

    def __enter__(self):
        """Context manager entry"""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms

        Simple tokenization: lowercase, split on non-alphanumeric characters.

        Args:
            text: Text to tokenize

        Returns:
            List of lowercase terms
        """
        if not text:
            return []

        # Convert to lowercase and split on non-alphanumeric
        terms = re.findall(r"\w+", text.lower())
        return terms

    async def _rebuild_bm25_index(self, documents: dict):
        """Build BM25 index structures from documents

        Args:
            documents: Dictionary of URI -> DocumentMetadata
        """
        # Clear existing BM25 data
        self.conn.execute("DELETE FROM document_terms")
        self.conn.execute("DELETE FROM document_stats")
        self.conn.execute("DELETE FROM term_stats")
        self.conn.execute("DELETE FROM collection_stats")
        self.conn.commit()

        if not documents:
            return

        # Track term frequencies across collection
        term_doc_freq = {}  # term -> set of doc URIs containing it
        term_collection_freq = {}  # term -> total occurrences

        # Process each document
        total_length_name = 0
        total_length_summary = 0
        total_length_tags = 0
        total_length_extra = 0
        total_length_total = 0

        for uri, doc in documents.items():
            doc_term_counts = {}  # (field, term) -> frequency

            # Tokenize name field
            name_terms = self._tokenize(doc.name or "")
            for term in name_terms:
                key = ("name", term)
                doc_term_counts[key] = doc_term_counts.get(key, 0) + 1

                # Track for collection stats
                if term not in term_doc_freq:
                    term_doc_freq[term] = set()
                term_doc_freq[term].add(uri)
                term_collection_freq[term] = term_collection_freq.get(term, 0) + 1

            # Tokenize summary field
            summary_terms = self._tokenize(doc.summary or "")
            for term in summary_terms:
                key = ("summary", term)
                doc_term_counts[key] = doc_term_counts.get(key, 0) + 1

                if term not in term_doc_freq:
                    term_doc_freq[term] = set()
                term_doc_freq[term].add(uri)
                term_collection_freq[term] = term_collection_freq.get(term, 0) + 1

            # Tokenize tags field
            tags_text = " ".join(doc.tags) if doc.tags else ""
            tags_terms = self._tokenize(tags_text)
            for term in tags_terms:
                key = ("tags", term)
                doc_term_counts[key] = doc_term_counts.get(key, 0) + 1

                if term not in term_doc_freq:
                    term_doc_freq[term] = set()
                term_doc_freq[term].add(uri)
                term_collection_freq[term] = term_collection_freq.get(term, 0) + 1

            # Tokenize extra fields
            if doc.extra:
                extra_text = " ".join(
                    str(v) for v in doc.extra.values() if v is not None
                )
                extra_terms = self._tokenize(extra_text)
                for term in extra_terms:
                    key = ("extra", term)
                    doc_term_counts[key] = doc_term_counts.get(key, 0) + 1

                    if term not in term_doc_freq:
                        term_doc_freq[term] = set()
                    term_doc_freq[term].add(uri)
                    term_collection_freq[term] = term_collection_freq.get(term, 0) + 1

            # Insert document terms
            for (field, term), frequency in doc_term_counts.items():
                self.conn.execute(
                    """
                    INSERT INTO document_terms (uri, field, term, frequency)
                    VALUES (?, ?, ?, ?)
                    """,
                    (uri, field, term, frequency),
                )

            # Calculate document statistics
            length_name = len(name_terms)
            length_summary = len(summary_terms)
            length_tags = len(tags_terms)
            length_extra = len(extra_terms) if doc.extra else 0
            length_total = length_name + length_summary + length_tags + length_extra

            self.conn.execute(
                """
                INSERT INTO document_stats (uri, length_name, length_summary, length_tags, length_extra, length_total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uri,
                    length_name,
                    length_summary,
                    length_tags,
                    length_extra,
                    length_total,
                ),
            )

            total_length_name += length_name
            total_length_summary += length_summary
            total_length_tags += length_tags
            total_length_extra += length_extra
            total_length_total += length_total

        # Insert term statistics
        for term, doc_freq in term_doc_freq.items():
            self.conn.execute(
                """
                INSERT INTO term_stats (term, doc_frequency, collection_frequency)
                VALUES (?, ?, ?)
                """,
                (term, len(doc_freq), term_collection_freq.get(term, 0)),
            )

        # Insert collection statistics
        num_docs = len(documents)
        avg_length_name = total_length_name / num_docs if num_docs > 0 else 0
        avg_length_summary = total_length_summary / num_docs if num_docs > 0 else 0
        avg_length_tags = total_length_tags / num_docs if num_docs > 0 else 0
        avg_length_extra = total_length_extra / num_docs if num_docs > 0 else 0
        avg_length_total = total_length_total / num_docs if num_docs > 0 else 0

        stats = [
            ("total_docs", float(num_docs)),
            ("avg_length_name", avg_length_name),
            ("avg_length_summary", avg_length_summary),
            ("avg_length_tags", avg_length_tags),
            ("avg_length_extra", avg_length_extra),
            ("avg_length_total", avg_length_total),
        ]

        for key, value in stats:
            self.conn.execute(
                "INSERT INTO collection_stats (key, value) VALUES (?, ?)",
                (key, value),
            )

        self.conn.commit()
        logger.info(f"BM25 index built: {len(term_doc_freq)} unique terms")
