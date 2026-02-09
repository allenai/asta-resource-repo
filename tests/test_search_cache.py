"""Tests for SQLite search cache functionality"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from asta.resources.document_store.search_cache import SearchCache
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


@pytest.fixture
def search_cache(index_path):
    """Create a SearchCache instance"""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    # Create empty index file
    index_path.write_text("version: '1.0'\ndocuments: []\n")

    cache = SearchCache(index_path)
    cache.initialize()
    yield cache
    cache.close()


@pytest.fixture
def sample_documents():
    """Create sample documents for testing"""
    return {
        "asta://test/doc1": DocumentMetadata(
            uri="asta://test/doc1",
            name="Attention Is All You Need",
            url="https://arxiv.org/pdf/1706.03762.pdf",
            summary="Seminal paper introducing the Transformer architecture for NLP",
            mime_type="application/pdf",
            tags=["ai", "nlp", "transformers"],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            extra={"author": "Vaswani et al", "year": 2017},
        ),
        "asta://test/doc2": DocumentMetadata(
            uri="asta://test/doc2",
            name="BERT: Pre-training of Deep Bidirectional Transformers",
            url="https://arxiv.org/pdf/1810.04805.pdf",
            summary="BERT model for language understanding using transformers",
            mime_type="application/pdf",
            tags=["ai", "nlp", "bert"],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            extra={"author": "Devlin et al", "year": 2018},
        ),
        "asta://test/doc3": DocumentMetadata(
            uri="asta://test/doc3",
            name="ResNet: Deep Residual Learning",
            url="https://arxiv.org/pdf/1512.03385.pdf",
            summary="Residual networks for image recognition",
            mime_type="application/pdf",
            tags=["ai", "vision", "cnn"],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            extra={"author": "He et al", "year": 2015},
        ),
    }


def test_cache_initialization(search_cache):
    """Test that cache initializes correctly"""
    assert search_cache._initialized
    assert search_cache.conn is not None

    # Check that schema was created
    cursor = search_cache.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    assert "documents" in tables
    assert "documents_fts" in tables
    assert "sync_metadata" in tables
    assert "schema_version" in tables


def test_yaml_hash_calculation(search_cache, index_path):
    """Test YAML hash calculation"""
    # Write some content to index
    content = "test content\n"
    index_path.write_text(content)

    hash1 = search_cache._calculate_yaml_hash()
    assert hash1  # Should be non-empty

    # Same content should produce same hash
    hash2 = search_cache._calculate_yaml_hash()
    assert hash1 == hash2

    # Different content should produce different hash
    index_path.write_text("different content\n")
    hash3 = search_cache._calculate_yaml_hash()
    assert hash1 != hash3


@pytest.mark.asyncio
async def test_cache_sync(search_cache, sample_documents):
    """Test cache syncing with documents"""
    # Initially cache should be empty
    cursor = search_cache.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    assert cursor.fetchone()[0] == 0

    # Sync cache
    await search_cache.ensure_synced(sample_documents)

    # Check documents were inserted
    cursor.execute("SELECT COUNT(*) FROM documents")
    assert cursor.fetchone()[0] == len(sample_documents)

    # Check specific document
    cursor.execute(
        "SELECT name, summary FROM documents WHERE uri = ?", ("asta://test/doc1",)
    )
    row = cursor.fetchone()
    assert row[0] == "Attention Is All You Need"
    assert "Transformer" in row[1]


@pytest.mark.asyncio
async def test_cache_stale_detection(search_cache, index_path, sample_documents):
    """Test cache detects when YAML changes"""
    # Sync cache
    await search_cache.ensure_synced(sample_documents)

    # Cache should not be stale
    assert not search_cache.is_cache_stale()

    # Modify YAML file
    index_path.write_text("modified content\n")

    # Cache should now be stale
    assert search_cache.is_cache_stale()


@pytest.mark.asyncio
async def test_rebuild_cache(search_cache, sample_documents):
    """Test cache rebuild"""
    # Initial sync
    await search_cache._rebuild_cache(sample_documents)

    cursor = search_cache.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    initial_count = cursor.fetchone()[0]
    assert initial_count == len(sample_documents)

    # Add more documents
    new_doc = DocumentMetadata(
        uri="asta://test/doc4",
        name="New Document",
        url="https://example.com/doc4.pdf",
        summary="A new document",
        mime_type="application/pdf",
        tags=["test"],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc),
    )
    sample_documents["asta://test/doc4"] = new_doc

    # Rebuild cache
    await search_cache._rebuild_cache(sample_documents)

    # Check count increased
    cursor.execute("SELECT COUNT(*) FROM documents")
    new_count = cursor.fetchone()[0]
    assert new_count == len(sample_documents)


@pytest.mark.asyncio
async def test_fts5_sync(search_cache, sample_documents):
    """Test FTS5 table stays in sync with documents table"""
    await search_cache._rebuild_cache(sample_documents)

    # Check FTS5 table has same number of entries
    cursor = search_cache.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    doc_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM documents_fts")
    fts_count = cursor.fetchone()[0]

    assert doc_count == fts_count

    # Test FTS5 search works
    cursor.execute(
        "SELECT uri FROM documents_fts WHERE documents_fts MATCH 'transformer'"
    )
    results = cursor.fetchall()
    assert len(results) > 0  # Should find documents with "transformer"


def test_context_manager(index_path):
    """Test SearchCache context manager"""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("version: '1.0'\ndocuments: []\n")

    with SearchCache(index_path) as cache:
        assert cache._initialized
        assert cache.conn is not None

    # After context exit, connection should be closed
    assert cache.conn is None
    assert not cache._initialized
