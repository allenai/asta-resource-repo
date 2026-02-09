"""Hybrid search combining BM25 and semantic similarity"""

from typing import List, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


class HybridSearchRanker:
    """Combines multiple search strategies using Reciprocal Rank Fusion (RRF)

    RRF is a simple but effective method for combining rankings from multiple sources.
    It assigns scores based on the rank position rather than the raw scores,
    which makes it robust to different score scales.
    """

    def reciprocal_rank_fusion(
        self,
        bm25_results: List[Tuple[str, float]],
        semantic_results: List[Tuple[str, float]],
        bm25_weight: float = 0.5,
        semantic_weight: float = 0.5,
        k: int = 60,
    ) -> List[Tuple[str, float]]:
        """Combine BM25 and semantic search results using RRF

        Reciprocal Rank Fusion formula:
        RRF(d) = Σ (weight / (k + rank(d)))

        Where:
        - rank(d) is the position of document d in the ranking (1-indexed)
        - k is a constant (typically 60) to avoid high scores for top-ranked items
        - weight is the importance weight for each ranking source

        Args:
            bm25_results: List of (uri, score) from BM25 search
            semantic_results: List of (uri, score) from semantic search
            bm25_weight: Weight for BM25 results (default: 0.5)
            semantic_weight: Weight for semantic results (default: 0.5)
            k: RRF constant (default: 60)

        Returns:
            Combined list of (uri, rrf_score) tuples ranked by RRF score
        """
        # Normalize weights
        total_weight = bm25_weight + semantic_weight
        if total_weight > 0:
            bm25_weight = bm25_weight / total_weight
            semantic_weight = semantic_weight / total_weight

        # Calculate RRF scores
        rrf_scores: Dict[str, float] = {}

        # Add BM25 contributions
        for rank, (uri, _) in enumerate(bm25_results, start=1):
            rrf_score = bm25_weight / (k + rank)
            rrf_scores[uri] = rrf_scores.get(uri, 0.0) + rrf_score

        # Add semantic contributions
        for rank, (uri, _) in enumerate(semantic_results, start=1):
            rrf_score = semantic_weight / (k + rank)
            rrf_scores[uri] = rrf_scores.get(uri, 0.0) + rrf_score

        # Sort by RRF score (descending)
        combined_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        return combined_results

    def weighted_score_fusion(
        self,
        bm25_results: List[Tuple[str, float]],
        semantic_results: List[Tuple[str, float]],
        bm25_weight: float = 0.5,
        semantic_weight: float = 0.5,
    ) -> List[Tuple[str, float]]:
        """Combine results using weighted score fusion (alternative to RRF)

        Simply weights and combines the raw scores from each method.
        Less robust than RRF but simpler.

        Args:
            bm25_results: List of (uri, score) from BM25 search
            semantic_results: List of (uri, score) from semantic search
            bm25_weight: Weight for BM25 results (default: 0.5)
            semantic_weight: Weight for semantic results (default: 0.5)

        Returns:
            Combined list of (uri, weighted_score) tuples
        """
        # Normalize weights
        total_weight = bm25_weight + semantic_weight
        if total_weight > 0:
            bm25_weight = bm25_weight / total_weight
            semantic_weight = semantic_weight / total_weight

        # Combine scores
        combined_scores: Dict[str, float] = {}

        # Add BM25 scores
        for uri, score in bm25_results:
            combined_scores[uri] = combined_scores.get(uri, 0.0) + (score * bm25_weight)

        # Add semantic scores
        for uri, score in semantic_results:
            combined_scores[uri] = combined_scores.get(uri, 0.0) + (
                score * semantic_weight
            )

        # Sort by combined score (descending)
        combined_results = sorted(
            combined_scores.items(), key=lambda x: x[1], reverse=True
        )

        return combined_results
