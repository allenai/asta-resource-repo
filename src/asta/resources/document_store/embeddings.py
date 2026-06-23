"""Embedding generation and vector search for semantic similarity"""

import os
import sqlite3
import struct
from typing import List, Tuple, Optional, TYPE_CHECKING
import logging

# Silence Hugging Face / transformers noise (LOAD REPORT, "Loading weights"
# progress bar, advisory warnings) before any transformers import happens.
# Users can still opt in to verbose output by setting these env vars themselves.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Check if sentence-transformers is available without importing it
# This avoids slow imports at module load time
try:
    import importlib.util

    EMBEDDINGS_AVAILABLE = importlib.util.find_spec("sentence_transformers") is not None
except Exception:
    EMBEDDINGS_AVAILABLE = False


class EmbeddingManager:
    """Manages document embeddings for semantic search

    Uses sentence-transformers to generate vector embeddings of document summaries.
    Provides vector similarity search using cosine distance.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        """Initialize embedding manager

        Args:
            conn: SQLite database connection
            model_name: Sentence-transformers model to use (default: all-MiniLM-L6-v2)
        """
        self.conn = conn
        self.model_name = model_name
        self._model: Optional["SentenceTransformer"] = None
        self._dimension: Optional[int] = None

        if not EMBEDDINGS_AVAILABLE:
            logger.warning(
                "sentence-transformers not available. Semantic search unavailable."
            )

    def _load_model(self):
        """Lazy load the sentence-transformers model"""
        if not EMBEDDINGS_AVAILABLE:
            raise ImportError("sentence-transformers not available.")

        if self._model is None:
            # Import heavy dependencies only when actually needed
            from sentence_transformers import SentenceTransformer

            # Belt-and-suspenders silencing in case env vars were set too late
            # (e.g. embeddings.py was imported after transformers already loaded).
            try:
                import transformers

                transformers.logging.set_verbosity_error()
                if hasattr(transformers.utils.logging, "disable_progress_bar"):
                    transformers.utils.logging.disable_progress_bar()
            except Exception:
                pass
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            # Get dimension by encoding a test string
            test_embedding = self._model.encode("test")
            self._dimension = len(test_embedding)
            logger.info(f"Model loaded. Dimension: {self._dimension}")

            # Persist model config only if it's actually missing or changed.
            # Writing unconditionally would touch the cache file on every
            # query-time call to _load_model().
            self._sync_model_config()

    def _sync_model_config(self):
        """Write model_name / dimension to embedding_config if not already current."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT key, value FROM embedding_config WHERE key IN ('model_name', 'dimension')"
        )
        stored = {row[0]: row[1] for row in cursor.fetchall()}
        desired = {"model_name": self.model_name, "dimension": str(self._dimension)}
        if stored == desired:
            return
        if self._connection_is_read_only():
            # The cache was opened immutable but has different (or no) model
            # config than what we'd load. Treat this like missing embeddings:
            # the cache was built for a different model and isn't usable here.
            raise RuntimeError(
                f"Cache embedding_config does not match model {self.model_name!r} "
                f"and the cache is read-only. Rebuild the cache with the "
                f"correct model, or set the embedding model to match what was "
                f"used to build the cache."
            )
        for key, value in desired.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO embedding_config (key, value) VALUES (?, ?)",
                (key, value),
            )
        self.conn.commit()

    def generate_embedding(self, text: str) -> "np.ndarray":
        """Generate embedding vector for text

        Args:
            text: Text to embed

        Returns:
            Embedding vector as numpy array (float32)
        """
        import numpy as np

        self._load_model()

        if not text:
            # Return zero vector for empty text
            return np.zeros(self._dimension, dtype=np.float32)

        # Generate embedding
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def _serialize_embedding(self, embedding: "np.ndarray") -> bytes:
        """Serialize numpy array to bytes for storage

        Args:
            embedding: Numpy array to serialize

        Returns:
            Serialized bytes
        """
        # Pack as: length (4 bytes) + float32 array
        length = len(embedding)
        return struct.pack(f"<I{length}f", length, *embedding)

    def _deserialize_embedding(self, data: bytes) -> "np.ndarray":
        """Deserialize bytes to numpy array

        Args:
            data: Serialized embedding bytes

        Returns:
            Numpy array (float32)
        """
        import numpy as np

        if not data:
            return None

        # Unpack: length + float32 array
        length = struct.unpack("<I", data[:4])[0]
        values = struct.unpack(f"<{length}f", data[4:])
        return np.array(values, dtype=np.float32)

    def store_embedding(self, uri: str, text: str):
        """Generate and store embedding for a document

        Args:
            uri: Document URI
            text: Text to embed (usually document summary)
        """
        # Generate embedding
        embedding = self.generate_embedding(text)

        # Serialize
        embedding_bytes = self._serialize_embedding(embedding)

        # Store in database
        self.conn.execute(
            """
            INSERT OR REPLACE INTO embeddings (uri, embedding, model_version)
            VALUES (?, ?, ?)
            """,
            (uri, embedding_bytes, self.model_name),
        )
        self.conn.commit()

    def get_embedding(self, uri: str) -> Optional["np.ndarray"]:
        """Retrieve stored embedding for a document

        Args:
            uri: Document URI

        Returns:
            Embedding vector or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT embedding FROM embeddings WHERE uri = ? AND model_version = ?",
            (uri, self.model_name),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return self._deserialize_embedding(row[0])

    async def ensure_embeddings(self, documents: dict):
        """Ensure all documents have embeddings

        Generates embeddings for documents that don't have them yet.

        Args:
            documents: Dictionary of URI -> DocumentMetadata
        """
        if not EMBEDDINGS_AVAILABLE:
            logger.warning(
                "Skipping embedding generation: sentence-transformers not installed"
            )
            return

        # Check which documents need embeddings
        existing_uris = set()
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT uri FROM embeddings WHERE model_version = ?",
            (self.model_name,),
        )
        for row in cursor.fetchall():
            existing_uris.add(row[0])

        # Detect missing embeddings up front so we can fail cleanly when the
        # cache was opened read-only (otherwise the first store_embedding()
        # would raise an opaque SQLITE_READONLY from inside the loop).
        missing_uris = [uri for uri in documents if uri not in existing_uris]
        if not missing_uris:
            return

        if self._connection_is_read_only():
            raise RuntimeError(
                f"{len(missing_uris)} document(s) are missing embeddings, but "
                f"the search cache is read-only. Rebuild the cache with write "
                f"access (or use --cache-dir to point to a writable location)."
            )

        for uri in missing_uris:
            self.store_embedding(uri, documents[uri].summary or "")
        logger.info(f"Generated embeddings for {len(missing_uris)} documents")

    def _connection_is_read_only(self) -> bool:
        """Return True if the underlying SQLite connection refuses writes."""
        try:
            row = self.conn.execute("PRAGMA query_only").fetchone()
        except sqlite3.Error:
            return False
        return bool(row and row[0])

    def _cosine_similarity(self, vec1: "np.ndarray", vec2: "np.ndarray") -> float:
        """Calculate cosine similarity between two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0-1, higher is more similar)
        """
        import numpy as np

        # Normalize vectors
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Cosine similarity = dot product of normalized vectors
        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def vector_search(
        self, query_embedding: "np.ndarray", limit: int = 10
    ) -> List[Tuple[str, float]]:
        """Search for similar documents using vector similarity

        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results

        Returns:
            List of (uri, similarity_score) tuples ranked by similarity
        """
        # Get all embeddings
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT uri, embedding FROM embeddings WHERE model_version = ?",
            (self.model_name,),
        )

        # Calculate similarities
        similarities = []
        for uri, embedding_bytes in cursor.fetchall():
            doc_embedding = self._deserialize_embedding(embedding_bytes)
            if doc_embedding is not None:
                similarity = self._cosine_similarity(query_embedding, doc_embedding)
                similarities.append((uri, similarity))

        # Sort by similarity (descending) and limit
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]
