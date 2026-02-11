"""BM25 ranking implementation for search relevance"""

import math
import re
import sqlite3
from typing import List, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


class BM25Ranker:
    """Implements BM25 (Best Match 25) ranking algorithm

    BM25 is a probabilistic ranking function used to estimate the relevance
    of documents to a given search query. It considers:
    - Term frequency (TF): How often a term appears in a document
    - Inverse document frequency (IDF): How rare a term is across all documents
    - Document length normalization: Longer documents don't get unfair advantage

    Formula:
    BM25(q, d) = Σ IDF(qi) * (f(qi, d) * (k1 + 1)) / (f(qi, d) + k1 * (1 - b + b * |d| / avgdl))

    Where:
    - IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5))
    - f(qi, d) = term frequency in document
    - |d| = document length
    - avgdl = average document length
    - k1 = 1.2 (term saturation parameter)
    - b = 0.75 (length normalization parameter)
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        k1: float = 1.2,
        b: float = 0.75,
        field_weights: Dict[str, float] = None,
    ):
        """Initialize BM25 ranker

        Args:
            conn: SQLite database connection
            k1: Term saturation parameter (default: 1.2)
            b: Length normalization parameter (default: 0.75)
            field_weights: Field importance weights (default: equal weights)
        """
        self.conn = conn
        self.k1 = k1
        self.b = b
        self.field_weights = field_weights or {
            "name": 2.0,
            "summary": 3.0,
            "tags": 1.5,
            "extra": 1.0,
        }

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

    def _calculate_idf(self, term: str, total_docs: int) -> float:
        """Calculate IDF (Inverse Document Frequency) for a term

        IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5))

        Args:
            term: Search term
            total_docs: Total number of documents in collection

        Returns:
            IDF score (higher = more rare/important term)
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT doc_frequency FROM term_stats WHERE term = ?", (term,))
        row = cursor.fetchone()

        if row is None or row[0] == 0:
            # Term not in collection, return max IDF
            return math.log(total_docs + 1)

        doc_freq = row[0]

        # BM25 IDF formula
        idf = math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
        return max(0.0, idf)  # Ensure non-negative

    def _calculate_field_score(
        self,
        term_freq: int,
        field_length: int,
        avg_field_length: float,
        idf: float,
    ) -> float:
        """Calculate BM25 score for a single field

        Args:
            term_freq: Term frequency in this field
            field_length: Length of this field
            avg_field_length: Average field length across all documents
            idf: IDF score for the term

        Returns:
            BM25 score contribution from this field
        """
        if term_freq == 0 or field_length == 0:
            return 0.0

        # Avoid division by zero
        if avg_field_length == 0:
            avg_field_length = 1.0

        # BM25 formula
        numerator = term_freq * (self.k1 + 1)
        denominator = term_freq + self.k1 * (
            1 - self.b + self.b * (field_length / avg_field_length)
        )

        return idf * (numerator / denominator)

    def rank(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        """Rank documents by BM25 relevance score

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of (uri, score) tuples ranked by relevance
        """
        # Tokenize query
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # Get collection statistics
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM collection_stats WHERE key = 'total_docs'")
        row = cursor.fetchone()
        total_docs = int(float(row[0])) if row else 0

        if total_docs == 0:
            return []

        # Get average field lengths
        cursor.execute(
            "SELECT value FROM collection_stats WHERE key = 'avg_length_name'"
        )
        row = cursor.fetchone()
        avg_length_name = float(row[0]) if row else 1.0

        cursor.execute(
            "SELECT value FROM collection_stats WHERE key = 'avg_length_summary'"
        )
        row = cursor.fetchone()
        avg_length_summary = float(row[0]) if row else 1.0

        cursor.execute(
            "SELECT value FROM collection_stats WHERE key = 'avg_length_tags'"
        )
        row = cursor.fetchone()
        avg_length_tags = float(row[0]) if row else 1.0

        cursor.execute(
            "SELECT value FROM collection_stats WHERE key = 'avg_length_extra'"
        )
        row = cursor.fetchone()
        avg_length_extra = float(row[0]) if row else 1.0

        # Calculate scores for all documents
        doc_scores: Dict[str, float] = {}

        for term in query_terms:
            # Calculate IDF for this term
            idf = self._calculate_idf(term, total_docs)

            # Find all documents containing this term
            cursor.execute(
                """
                SELECT uri, field, frequency
                FROM document_terms
                WHERE term = ?
                """,
                (term,),
            )

            for uri, field, term_freq in cursor.fetchall():
                if uri not in doc_scores:
                    doc_scores[uri] = 0.0

                # Get document field length
                cursor.execute(
                    f"SELECT length_{field} FROM document_stats WHERE uri = ?",
                    (uri,),
                )
                row = cursor.fetchone()
                field_length = row[0] if row else 0

                # Select appropriate average length
                if field == "name":
                    avg_length = avg_length_name
                elif field == "summary":
                    avg_length = avg_length_summary
                elif field == "tags":
                    avg_length = avg_length_tags
                elif field == "extra":
                    avg_length = avg_length_extra
                else:
                    avg_length = 1.0

                # Calculate field score
                field_score = self._calculate_field_score(
                    term_freq, field_length, avg_length, idf
                )

                # Apply field weight
                field_weight = self.field_weights.get(field, 1.0)
                doc_scores[uri] += field_score * field_weight

        # Sort by score and return top results
        ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]
