"""Tests for BM25 ranking algorithm"""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from asta.resources.document_store.search_cache import SearchCache
from asta.resources.document_store.bm25_ranker import BM25Ranker
from asta.resources.model import DocumentMetadata


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def index_path(temp_dir):
    """Create a test index file path"""
    return temp_dir / ".asta" / "index.yaml"


@pytest_asyncio.fixture
async def search_cache_with_docs(index_path):
    """Create a SearchCache with sample documents"""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    # Create empty index file
    index_path.write_text("version: '1.0'\ndocuments: []\n")

    cache = SearchCache(index_path)
    cache.initialize()

    # Create sample documents
    documents = {
        "asta://test/doc1": DocumentMetadata(
            uri="asta://test/doc1",
            name="Python Programming Guide",
            url="https://example.com/python.pdf",
            summary="A comprehensive guide to Python programming with examples",
            mime_type="application/pdf",
            tags=["python", "programming"],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
        ),
        "asta://test/doc2": DocumentMetadata(
            uri="asta://test/doc2",
            name="Advanced Python Techniques",
            url="https://example.com/advanced-python.pdf",
            summary="Advanced techniques and patterns in Python programming",
            mime_type="application/pdf",
            tags=["python", "advanced"],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
        ),
        "asta://test/doc3": DocumentMetadata(
            uri="asta://test/doc3",
            name="JavaScript Basics",
            url="https://example.com/javascript.pdf",
            summary="Introduction to JavaScript programming for beginners",
            mime_type="application/pdf",
            tags=["javascript", "programming"],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
        ),
    }

    # Rebuild cache with documents
    await cache._rebuild_cache(documents)

    yield cache

    cache.close()


def test_bm25_tokenization():
    """Test BM25 tokenization"""
    ranker = BM25Ranker(None)  # Don't need connection for tokenization

    # Test basic tokenization
    terms = ranker._tokenize("Hello World")
    assert terms == ["hello", "world"]

    # Test with punctuation
    terms = ranker._tokenize("Python 3.9, JavaScript & C++")
    assert "python" in terms
    assert "javascript" in terms

    # Test empty string
    terms = ranker._tokenize("")
    assert terms == []


@pytest.mark.asyncio
async def test_bm25_idf_calculation(search_cache_with_docs):
    """Test IDF calculation"""
    ranker = BM25Ranker(search_cache_with_docs.conn)

    # Get total docs
    cursor = search_cache_with_docs.conn.cursor()
    cursor.execute("SELECT value FROM collection_stats WHERE key = 'total_docs'")
    total_docs = int(float(cursor.fetchone()[0]))

    # Calculate IDF for common term (appears in 2 docs)
    idf_python = ranker._calculate_idf("python", total_docs)

    # Calculate IDF for rare term (appears in 1 doc)
    idf_javascript = ranker._calculate_idf("javascript", total_docs)

    # Rare terms should have higher IDF
    assert idf_javascript > idf_python

    # Calculate IDF for non-existent term
    idf_nonexistent = ranker._calculate_idf("nonexistent", total_docs)
    assert idf_nonexistent > 0  # Should return max IDF


@pytest.mark.asyncio
async def test_bm25_field_score(search_cache_with_docs):
    """Test field score calculation"""
    ranker = BM25Ranker(search_cache_with_docs.conn, k1=1.2, b=0.75)

    # Test with various parameters
    score1 = ranker._calculate_field_score(
        term_freq=2,
        field_length=10,
        avg_field_length=10,
        idf=1.0,
    )
    assert score1 > 0

    # Higher term frequency should increase score
    score2 = ranker._calculate_field_score(
        term_freq=5,
        field_length=10,
        avg_field_length=10,
        idf=1.0,
    )
    assert score2 > score1

    # Test zero term frequency
    score3 = ranker._calculate_field_score(
        term_freq=0,
        field_length=10,
        avg_field_length=10,
        idf=1.0,
    )
    assert score3 == 0


@pytest.mark.asyncio
async def test_bm25_ranking(search_cache_with_docs):
    """Test BM25 ranking of documents"""
    ranker = BM25Ranker(search_cache_with_docs.conn)

    # Search for "python"
    results = ranker.rank("python", limit=10)

    # Should find 2 documents with "python"
    assert len(results) == 2

    # Results should be ranked by score (descending)
    assert results[0][1] >= results[1][1]

    # Check that URIs are correct
    uris = [uri for uri, score in results]
    assert "asta://test/doc1" in uris
    assert "asta://test/doc2" in uris


@pytest.mark.asyncio
async def test_bm25_ranking_order(search_cache_with_docs):
    """Test that BM25 ranks documents in correct order"""
    ranker = BM25Ranker(search_cache_with_docs.conn)

    # "programming" appears in multiple documents
    results = ranker.rank("programming", limit=10)

    # Should find 3 documents
    assert len(results) == 3

    # Scores should be descending
    for i in range(len(results) - 1):
        assert results[i][1] >= results[i + 1][1]


@pytest.mark.asyncio
async def test_bm25_term_saturation(search_cache_with_docs):
    """Test k1 parameter (term saturation)"""
    # Low k1 = quick saturation
    ranker_low = BM25Ranker(search_cache_with_docs.conn, k1=0.5)
    # High k1 = slow saturation
    ranker_high = BM25Ranker(search_cache_with_docs.conn, k1=2.0)

    # Both should find same documents but with different scores
    results_low = ranker_low.rank("python", limit=10)
    results_high = ranker_high.rank("python", limit=10)

    assert len(results_low) == len(results_high)


@pytest.mark.asyncio
async def test_bm25_length_normalization(search_cache_with_docs):
    """Test b parameter (length normalization)"""
    # b=0 = no length normalization
    ranker_no_norm = BM25Ranker(search_cache_with_docs.conn, b=0.0)
    # b=1 = full length normalization
    ranker_full_norm = BM25Ranker(search_cache_with_docs.conn, b=1.0)

    # Both should find same documents
    results_no_norm = ranker_no_norm.rank("python", limit=10)
    results_full_norm = ranker_full_norm.rank("python", limit=10)

    assert len(results_no_norm) == len(results_full_norm)


@pytest.mark.asyncio
async def test_bm25_field_weights(search_cache_with_docs):
    """Test field weight boosting"""
    # Boost summary field heavily
    ranker_summary_boost = BM25Ranker(
        search_cache_with_docs.conn,
        field_weights={"name": 1.0, "summary": 10.0, "tags": 1.0, "extra": 1.0},
    )

    # Boost name field heavily
    ranker_name_boost = BM25Ranker(
        search_cache_with_docs.conn,
        field_weights={"name": 10.0, "summary": 1.0, "tags": 1.0, "extra": 1.0},
    )

    results_summary = ranker_summary_boost.rank("programming", limit=10)
    results_name = ranker_name_boost.rank("programming", limit=10)

    # Both should find documents
    assert len(results_summary) > 0
    assert len(results_name) > 0


@pytest.mark.asyncio
async def test_bm25_multi_term_query(search_cache_with_docs):
    """Test BM25 with multi-term queries"""
    ranker = BM25Ranker(search_cache_with_docs.conn)

    # Search with multiple terms
    results = ranker.rank("python programming", limit=10)

    # Should find documents containing either or both terms
    assert len(results) > 0

    # Documents with both terms should rank higher
    # (This is implicit in the BM25 algorithm)


@pytest.mark.asyncio
async def test_bm25_empty_query(search_cache_with_docs):
    """Test BM25 with empty query"""
    ranker = BM25Ranker(search_cache_with_docs.conn)

    results = ranker.rank("", limit=10)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_bm25_nonexistent_term(search_cache_with_docs):
    """Test BM25 with term not in collection"""
    ranker = BM25Ranker(search_cache_with_docs.conn)

    results = ranker.rank("nonexistent_term_xyz", limit=10)
    assert len(results) == 0
