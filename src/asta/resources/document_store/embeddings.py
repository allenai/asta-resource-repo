"""Embedding generation and vector search for semantic similarity"""

import sqlite3
import struct
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import sentence-transformers, but make it optional
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    SentenceTransformer = None
    np = None


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
        self._model: Optional[SentenceTransformer] = None
        self._dimension: Optional[int] = None

        if not EMBEDDINGS_AVAILABLE:
            logger.warning(
                "sentence-transformers not installed. Semantic search unavailable. "
                "Install with: uv sync --extra search"
            )

    def _load_model(self):
        """Lazy load the sentence-transformers model"""
        if not EMBEDDINGS_AVAILABLE:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: uv sync --extra search"
            )

        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            # Get dimension by encoding a test string
            test_embedding = self._model.encode("test")
            self._dimension = len(test_embedding)
            logger.info(f"Model loaded. Dimension: {self._dimension}")

            # Store model config
            self.conn.execute(
                "INSERT OR REPLACE INTO embedding_config (key, value) VALUES (?, ?)",
                ("model_name", self.model_name),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO embedding_config (key, value) VALUES (?, ?)",
                ("dimension", str(self._dimension)),
            )
            self.conn.commit()

    def generate_embedding(self, text: str) -> "np.ndarray":
        """Generate embedding vector for text

        Args:
            text: Text to embed

        Returns:
            Embedding vector as numpy array (float32)
        """
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

        # Generate embeddings for missing documents
        missing_count = 0
        for uri, doc in documents.items():
            if uri not in existing_uris:
                self.store_embedding(uri, doc.summary or "")
                missing_count += 1

        if missing_count > 0:
            logger.info(f"Generated embeddings for {missing_count} documents")

    def _cosine_similarity(self, vec1: "np.ndarray", vec2: "np.ndarray") -> float:
        """Calculate cosine similarity between two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0-1, higher is more similar)
        """
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
