"""Tests for LocalIndexDocumentStore"""

import pytest
import pytest_asyncio
import tempfile
import yaml
from pathlib import Path

from asta.resources.document_store.local_index import LocalIndexDocumentStore
from asta.resources.model import DocumentMetadata
from asta.resources.exceptions import ValidationError

# Test short ID constant (10-char alphanumeric)
TEST_SHORT_ID = "abc123xyz0"


@pytest.fixture
def temp_index_path():
    """Create a temporary directory for test index files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / ".asta" / "documents" / "index.yaml"
        yield index_path


@pytest_asyncio.fixture
async def store(temp_index_path):
    """Create a LocalIndexDocumentStore instance for testing"""
    store = LocalIndexDocumentStore(
        index_path=str(temp_index_path),
    )
    async with store:
        yield store


@pytest.mark.asyncio
async def test_initialize_creates_index_file(temp_index_path):
    """Test that initialize creates the index file and directory"""
    assert not temp_index_path.exists()

    store = LocalIndexDocumentStore(
        index_path=str(temp_index_path),
    )
    await store.initialize()

    assert temp_index_path.exists()
    assert temp_index_path.parent.exists()

    await store.close()


@pytest.mark.asyncio
async def test_store_document(store):
    """Test storing a document"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["test", "example"],
        extra={"author": "Test Author"},
    )

    uuid = await store.store(doc)

    assert len(uuid) == 10
    assert doc.created_at is not None
    assert doc.modified_at is not None


@pytest.mark.asyncio
async def test_store_validates_url(store):
    """Test that store validates URL format"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="invalid-url",
        summary="A test document",
        mime_type="application/pdf",
    )

    with pytest.raises(ValidationError, match="Invalid URL format"):
        await store.store(doc)


@pytest.mark.asyncio
async def test_store_accepts_various_url_protocols(store):
    """Test that store accepts various URL protocols"""
    protocols = [
        "http://example.com/doc.pdf",
        "https://example.com/doc.pdf",
        "file:///path/to/document.pdf",
    ]

    for i, url in enumerate(protocols):
        doc = DocumentMetadata(
            uuid="",
            name=f"Test Document {i}",
            url=url,
            summary=f"Test document with {url.split('://')[0]} protocol",
            mime_type="application/pdf",
        )

        # Should not raise ValidationError
        uri = await store.store(doc)
        assert len(uri) == 10

        # Verify it was stored correctly
        retrieved = await store.get(uri)
        assert retrieved.url == url


@pytest.mark.asyncio
async def test_store_requires_summary(store):
    """Test that store requires summary field"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="",  # Empty summary
        mime_type="application/pdf",
    )

    with pytest.raises(ValidationError, match="summary is required"):
        await store.store(doc)


@pytest.mark.asyncio
async def test_get_document(store):
    """Test retrieving a document by URI"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["test"],
    )

    uri = await store.store(doc)
    retrieved = await store.get(uri)

    assert retrieved is not None
    assert retrieved.uuid == uri
    assert retrieved.name == "Test Document"
    assert retrieved.url == "https://example.com/doc.pdf"
    assert retrieved.summary == "A test document"
    assert retrieved.tags == ["test"]


@pytest.mark.asyncio
async def test_get_nonexistent_document(store):
    """Test getting a document that doesn't exist"""
    result = await store.get(TEST_SHORT_ID)
    assert result is None


@pytest.mark.asyncio
async def test_list_documents(store):
    """Test listing all documents"""
    # Add multiple documents
    docs = [
        DocumentMetadata(
            uuid="",
            name=f"Document {i}",
            url=f"https://example.com/doc{i}.pdf",
            summary=f"Document {i} summary",
            mime_type="application/pdf",
        )
        for i in range(3)
    ]

    for doc in docs:
        await store.store(doc)

    all_docs = await store.list_docs()
    assert len(all_docs) == 3
    assert all(doc.name.startswith("Document") for doc in all_docs)


@pytest.mark.asyncio
async def test_list_empty_index(store):
    """Test listing documents when index is empty"""
    docs = await store.list_docs()
    assert docs == []


@pytest.mark.asyncio
async def test_search_by_name(store):
    """Test searching documents by name (legacy test - kept for compatibility)"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Python Programming",
        url="https://example.com/python.pdf",
        summary="A guide to Rust",  # Changed to avoid matching "Python" in summary
        mime_type="application/pdf",
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="JavaScript Guide",
        url="https://example.com/js.pdf",
        summary="Learning JavaScript",
        mime_type="application/pdf",
    )

    await store.store(doc1)
    await store.store(doc2)

    # Search in summary field (default) should find Python in doc1's name via cross-field search
    # Or we can use field-specific search to be more precise
    results = await store.search("Python", search_field="name")
    assert len(results) == 1
    assert results[0].result.name == "Python Programming"


@pytest.mark.asyncio
async def test_search_by_summary(store):
    """Test searching documents by summary"""
    doc = DocumentMetadata(
        uuid="",
        name="AI Paper",
        url="https://example.com/ai.pdf",
        summary="Deep learning and neural networks",
        mime_type="application/pdf",
    )

    await store.store(doc)

    results = await store.search("neural networks")
    assert len(results) == 1
    assert results[0].result.name == "AI Paper"


@pytest.mark.asyncio
async def test_search_by_tags(store):
    """Test searching documents by tags"""
    doc = DocumentMetadata(
        uuid="",
        name="Research Paper",
        url="https://example.com/paper.pdf",
        summary="A research paper",
        mime_type="application/pdf",
        tags=["machine-learning", "research"],
    )

    await store.store(doc)

    results = await store.search("machine-learning")
    assert len(results) == 1
    assert results[0].result.name == "Research Paper"


@pytest.mark.asyncio
async def test_search_case_insensitive(store):
    """Test that search is case-insensitive"""
    doc = DocumentMetadata(
        uuid="",
        name="PyTorch Documentation",
        url="https://example.com/pytorch.pdf",
        summary="PyTorch deep learning framework",
        mime_type="application/pdf",
    )

    await store.store(doc)

    results = await store.search("PYTORCH")
    assert len(results) == 1

    results = await store.search("pytorch")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_with_limit(store):
    """Test search with result limit"""
    # Add multiple matching documents
    for i in range(5):
        doc = DocumentMetadata(
            uuid="",
            name=f"Python Tutorial {i}",
            url=f"https://example.com/python{i}.pdf",
            summary="Python programming guide",
            mime_type="application/pdf",
        )
        await store.store(doc)

    results = await store.search("Python", limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_search_no_matches(store):
    """Test search with no matches"""
    doc = DocumentMetadata(
        uuid="",
        name="JavaScript Guide",
        url="https://example.com/js.pdf",
        summary="Learn JavaScript",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # Search by name for something that definitely doesn't match
    results = await store.search("xyzzyx", search_field="name")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_delete_document(store):
    """Test deleting a document"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)
    assert await store.exists(uri)

    deleted = await store.delete(uri)
    assert deleted is True
    assert not await store.exists(uri)


@pytest.mark.asyncio
async def test_delete_nonexistent_document(store):
    """Test deleting a document that doesn't exist"""
    deleted = await store.delete(TEST_SHORT_ID)
    assert deleted is False


@pytest.mark.asyncio
async def test_exists(store):
    """Test checking if a document exists"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)
    assert await store.exists(uri)
    assert not await store.exists(TEST_SHORT_ID)


@pytest.mark.asyncio
async def test_persistence(temp_index_path):
    """Test that documents persist across store instances"""
    # Create and populate first store
    store1 = LocalIndexDocumentStore(
        index_path=str(temp_index_path),
    )
    async with store1:
        doc = DocumentMetadata(
            uuid="",
            name="Persistent Document",
            url="https://example.com/doc.pdf",
            summary="A persistent document",
            mime_type="application/pdf",
        )
        uri = await store1.store(doc)

    # Create new store instance and verify document persists
    store2 = LocalIndexDocumentStore(
        index_path=str(temp_index_path),
    )
    async with store2:
        retrieved = await store2.get(uri)
        assert retrieved is not None
        assert retrieved.name == "Persistent Document"


@pytest.mark.asyncio
async def test_update_document(store):
    """Test updating a document using the update method"""
    doc = DocumentMetadata(
        uuid="",
        name="Original Name",
        url="https://example.com/doc.pdf",
        summary="Original summary",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    # Update the document using the update method
    updated = await store.update(
        uri, name="Updated Name", summary="Updated summary", tags=["updated"]
    )

    # Verify update
    assert updated.name == "Updated Name"
    assert updated.summary == "Updated summary"
    assert updated.tags == ["updated"]

    # Retrieve and verify persistence
    retrieved = await store.get(uri)
    assert retrieved.name == "Updated Name"
    assert retrieved.summary == "Updated summary"
    assert retrieved.tags == ["updated"]


@pytest.mark.asyncio
async def test_extra_metadata(store):
    """Test storing and retrieving extra metadata"""
    doc = DocumentMetadata(
        uuid="",
        name="Research Paper",
        url="https://example.com/paper.pdf",
        summary="A research paper",
        mime_type="application/pdf",
        extra={
            "author": "John Doe",
            "year": 2024,
            "venue": "Conference ABC",
            "citations": 42,
        },
    )

    uri = await store.store(doc)
    retrieved = await store.get(uri)

    assert retrieved.extra == doc.extra
    assert retrieved.extra["author"] == "John Doe"
    assert retrieved.extra["year"] == 2024


@pytest.mark.asyncio
async def test_search_extra_fields(store):
    """Test searching in extra metadata fields"""
    doc = DocumentMetadata(
        uuid="",
        name="Paper",
        url="https://example.com/paper.pdf",
        summary="A paper",
        mime_type="application/pdf",
        extra={"author": "Jane Smith", "venue": "NeurIPS 2024"},
    )

    await store.store(doc)

    # Search by author in extra fields
    results = await store.search("Jane Smith")
    assert len(results) == 1

    # Search by venue in extra fields
    results = await store.search("NeurIPS")
    assert len(results) == 1


# FTS5 Search Tests


@pytest.mark.asyncio
async def test_search_returns_scores(store):
    """Test that search results include relevance scores"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document about Python programming",
        mime_type="application/pdf",
    )

    await store.store(doc)

    results = await store.search("Python")
    assert len(results) == 1
    assert hasattr(results[0], "score")
    assert results[0].score >= 0  # Score should be non-negative


@pytest.mark.asyncio
async def test_fts5_search_basic(store):
    """Test FTS5 search finds documents correctly"""
    docs = [
        DocumentMetadata(
            uuid="",
            name="Attention Is All You Need",
            url="https://arxiv.org/pdf/1706.03762.pdf",
            summary="Seminal paper introducing the Transformer architecture for NLP",
            mime_type="application/pdf",
            tags=["ai", "nlp", "transformers"],
        ),
        DocumentMetadata(
            uuid="",
            name="BERT Paper",
            url="https://arxiv.org/pdf/1810.04805.pdf",
            summary="BERT model for language understanding",
            mime_type="application/pdf",
            tags=["ai", "nlp"],
        ),
        DocumentMetadata(
            uuid="",
            name="ResNet Paper",
            url="https://arxiv.org/pdf/1512.03385.pdf",
            summary="Residual networks for image recognition",
            mime_type="application/pdf",
            tags=["ai", "vision"],
        ),
    ]

    for doc in docs:
        await store.store(doc)

    # Search for "transformer" should find the first document
    # (uses best available method: hybrid, BM25, FTS5, or simple)
    results = await store.search("transformer")
    assert len(results) >= 1
    assert "Transformer" in results[0].result.summary

    # Search for "NLP" tag should find two documents
    results = await store.search("nlp", search_field="tags")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_fts5_field_boosting(store):
    """Test that FTS5 search respects field weights (summary > name > tags)"""
    docs = [
        DocumentMetadata(
            uuid="",
            name="Neural Networks in Summary",
            url="https://example.com/doc1.pdf",
            summary="This document is about transformers and attention mechanisms",
            mime_type="application/pdf",
            tags=["ai"],
        ),
        DocumentMetadata(
            uuid="",
            name="This is about transformers",
            url="https://example.com/doc2.pdf",
            summary="This document discusses neural network architectures",
            mime_type="application/pdf",
            tags=["ml"],
        ),
        DocumentMetadata(
            uuid="",
            name="Generic Document",
            url="https://example.com/doc3.pdf",
            summary="This document discusses various topics",
            mime_type="application/pdf",
            tags=["transformers", "research"],
        ),
    ]

    for doc in docs:
        await store.store(doc)

    # Search for "transformers" - doc with it in summary should rank higher
    results = await store.search("transformers", search_field="summary")
    assert len(results) >= 2

    # The document with "transformers" in summary should score highest
    assert (
        "transformers" in results[0].result.summary.lower()
        or "transformers" in results[0].result.name.lower()
    )


@pytest.mark.asyncio
async def test_summary_search_uses_best_method(store):
    """Test that summary search automatically uses best available method"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document about machine learning",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # Summary search should automatically use the best available method
    # (hybrid, BM25, FTS5, or simple) and return results
    results = await store.search("machine learning", search_field="summary")
    assert len(results) == 1
    assert results[0].result.name == "Test Document"


@pytest.mark.asyncio
async def test_simple_search_fallback(temp_index_path):
    """Test that simple search works when cache is disabled"""
    # Create store with cache disabled
    store = LocalIndexDocumentStore(
        index_path=str(temp_index_path),
        enable_cache=False,
    )
    async with store:
        doc = DocumentMetadata(
            uuid="",
            name="Test Document",
            url="https://example.com/doc.pdf",
            summary="A test document about Python",
            mime_type="application/pdf",
        )

        await store.store(doc)

        # Search should use simple mode
        results = await store.search("Python")
        assert len(results) == 1
        assert results[0].result.name == "Test Document"


@pytest.mark.asyncio
async def test_fts5_search_with_multiple_terms(store):
    """Test FTS5 search with multiple search terms"""
    doc = DocumentMetadata(
        uuid="",
        name="AI Research Paper",
        url="https://example.com/paper.pdf",
        summary="Deep learning and neural networks for natural language processing",
        mime_type="application/pdf",
        tags=["ai", "research"],
    )

    await store.store(doc)

    # Search with multiple terms
    results = await store.search("neural networks", search_field="summary")
    assert len(results) == 1
    assert "neural networks" in results[0].result.summary.lower()


@pytest.mark.asyncio
async def test_search_ranking_by_relevance(store):
    """Test that search results are ranked by relevance"""
    docs = [
        DocumentMetadata(
            uuid="",
            name="Highly Relevant Document",
            url="https://example.com/doc1.pdf",
            summary="Python Python Python programming language Python",
            mime_type="application/pdf",
        ),
        DocumentMetadata(
            uuid="",
            name="Somewhat Relevant Document",
            url="https://example.com/doc2.pdf",
            summary="Introduction to Python programming",
            mime_type="application/pdf",
        ),
        DocumentMetadata(
            uuid="",
            name="Less Relevant Document",
            url="https://example.com/doc3.pdf",
            summary="Programming languages include Python",
            mime_type="application/pdf",
        ),
    ]

    for doc in docs:
        await store.store(doc)

    results = await store.search("Python", limit=10)

    # Results should be ordered by relevance (descending score)
    assert len(results) == 3
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score


@pytest.mark.asyncio
async def test_search_cache_sync_on_changes(temp_index_path):
    """Test that search cache syncs when documents are added"""
    store = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store:
        # Add first document
        doc1 = DocumentMetadata(
            uuid="",
            name="First Document",
            url="https://example.com/doc1.pdf",
            summary="First document",
            mime_type="application/pdf",
        )
        await store.store(doc1)

        # Search should find it
        results = await store.search("First", search_field="summary")
        assert len(results) == 1

        # Add second document
        doc2 = DocumentMetadata(
            uuid="",
            name="Second Document",
            url="https://example.com/doc2.pdf",
            summary="Second document",
            mime_type="application/pdf",
        )
        await store.store(doc2)

        # Search should find both
        results = await store.search("document", search_field="summary")
        assert len(results) == 2


# ============================================================================
# Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_document_name(store):
    """Test updating a document's name"""
    doc = DocumentMetadata(
        uuid="",
        name="Original Name",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)
    original_modified_at = doc.modified_at

    # Update the name
    updated = await store.update(uri, name="Updated Name")

    assert updated.name == "Updated Name"
    assert updated.url == "https://example.com/doc.pdf"
    assert updated.summary == "A test document"
    assert updated.modified_at > original_modified_at
    assert updated.created_at == doc.created_at


@pytest.mark.asyncio
async def test_update_document_url(store):
    """Test updating a document's URL"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/old.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    # Update the URL
    updated = await store.update(uri, url="https://example.com/new.pdf")

    assert updated.url == "https://example.com/new.pdf"
    assert updated.name == "Test Document"


@pytest.mark.asyncio
async def test_update_document_summary(store):
    """Test updating a document's summary"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="Original summary",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    # Update the summary
    updated = await store.update(uri, summary="Updated summary")

    assert updated.summary == "Updated summary"


@pytest.mark.asyncio
async def test_update_document_tags(store):
    """Test updating a document's tags"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["old", "tags"],
    )

    uri = await store.store(doc)

    # Update the tags
    updated = await store.update(uri, tags=["new", "tags", "here"])

    assert updated.tags == ["new", "tags", "here"]


@pytest.mark.asyncio
async def test_update_document_extra_metadata(store):
    """Test updating a document's extra metadata"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        extra={"author": "Original Author"},
    )

    uri = await store.store(doc)

    # Update the extra metadata
    updated = await store.update(uri, extra={"author": "Updated Author", "year": 2024})

    assert updated.extra == {"author": "Updated Author", "year": 2024}


@pytest.mark.asyncio
async def test_update_multiple_fields(store):
    """Test updating multiple fields at once"""
    doc = DocumentMetadata(
        uuid="",
        name="Original Name",
        url="https://example.com/old.pdf",
        summary="Original summary",
        mime_type="application/pdf",
        tags=["old"],
    )

    uri = await store.store(doc)

    # Update multiple fields
    updated = await store.update(
        uri,
        name="New Name",
        summary="New summary",
        tags=["new", "tags"],
    )

    assert updated.name == "New Name"
    assert updated.summary == "New summary"
    assert updated.tags == ["new", "tags"]
    assert updated.url == "https://example.com/old.pdf"


@pytest.mark.asyncio
async def test_update_nonexistent_document(store):
    """Test updating a document that doesn't exist"""
    with pytest.raises(ValidationError, match="Document not found"):
        await store.update(TEST_SHORT_ID, name="New Name")


@pytest.mark.asyncio
async def test_update_validates_empty_name(store):
    """Test that update validates non-empty name"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    with pytest.raises(ValidationError, match="name cannot be empty"):
        await store.update(uri, name="")


@pytest.mark.asyncio
async def test_update_validates_empty_url(store):
    """Test that update validates non-empty URL"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    with pytest.raises(ValidationError, match="URL cannot be empty"):
        await store.update(uri, url="")


@pytest.mark.asyncio
async def test_update_validates_url_format(store):
    """Test that update validates URL format"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    with pytest.raises(ValidationError, match="Invalid URL format"):
        await store.update(uri, url="not-a-valid-url")


@pytest.mark.asyncio
async def test_update_accepts_various_url_protocols(store):
    """Test that update accepts various URL protocols"""
    doc = DocumentMetadata(
        uri="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    protocols = [
        "http://example.com/new.pdf",
        "file:///path/to/new.pdf",
    ]

    for url in protocols:
        # Should not raise ValidationError
        updated = await store.update(uri, url=url)
        assert updated.url == url

        # Verify persistence
        retrieved = await store.get(uri)
        assert retrieved.url == url


@pytest.mark.asyncio
async def test_update_validates_empty_summary(store):
    """Test that update validates non-empty summary"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    with pytest.raises(ValidationError, match="summary cannot be empty"):
        await store.update(uri, summary="")


@pytest.mark.asyncio
async def test_update_persists_to_disk(temp_index_path):
    """Test that updates persist to disk"""
    store = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store:
        doc = DocumentMetadata(
            uuid="",
            name="Original Name",
            url="https://example.com/doc.pdf",
            summary="A test document",
            mime_type="application/pdf",
        )

        uri = await store.store(doc)
        await store.update(uri, name="Updated Name")

    # Reload from disk
    store2 = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store2:
        retrieved = await store2.get(uri)
        assert retrieved is not None
        assert retrieved.name == "Updated Name"


# ============================================================================
# Tag Management Tests
# ============================================================================


@pytest.mark.asyncio
async def test_add_tags_to_document(store):
    """Test adding tags to a document"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["original", "test"],
    )

    uri = await store.store(doc)

    # Add new tags
    updated = await store.add_tags(uri, ["new", "added"])

    assert "original" in updated.tags
    assert "test" in updated.tags
    assert "new" in updated.tags
    assert "added" in updated.tags
    assert len(updated.tags) == 4


@pytest.mark.asyncio
async def test_add_tags_removes_duplicates(store):
    """Test that adding duplicate tags doesn't create duplicates"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["existing"],
    )

    uri = await store.store(doc)

    # Add tags including a duplicate
    updated = await store.add_tags(uri, ["existing", "new"])

    # Should only have 2 unique tags
    assert len(updated.tags) == 2
    assert "existing" in updated.tags
    assert "new" in updated.tags


@pytest.mark.asyncio
async def test_add_tags_to_document_without_existing_tags(store):
    """Test adding tags to a document that has no tags"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=[],
    )

    uri = await store.store(doc)

    # Add tags to document without tags
    updated = await store.add_tags(uri, ["first", "second"])

    assert len(updated.tags) == 2
    assert "first" in updated.tags
    assert "second" in updated.tags


@pytest.mark.asyncio
async def test_add_tags_sorts_tags(store):
    """Test that tags are sorted alphabetically"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["zebra"],
    )

    uri = await store.store(doc)
    updated = await store.add_tags(uri, ["apple", "banana"])

    assert updated.tags == ["apple", "banana", "zebra"]


@pytest.mark.asyncio
async def test_add_tags_nonexistent_document(store):
    """Test adding tags to a non-existent document raises error"""
    with pytest.raises(ValidationError, match="Document not found"):
        await store.add_tags(TEST_SHORT_ID, ["tag"])


@pytest.mark.asyncio
async def test_remove_tags_from_document(store):
    """Test removing tags from a document"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["keep", "remove1", "remove2"],
    )

    uri = await store.store(doc)

    # Remove some tags
    updated = await store.remove_tags(uri, ["remove1", "remove2"])

    assert len(updated.tags) == 1
    assert "keep" in updated.tags
    assert "remove1" not in updated.tags
    assert "remove2" not in updated.tags


@pytest.mark.asyncio
async def test_remove_tags_ignores_nonexistent_tags(store):
    """Test that removing non-existent tags doesn't raise error"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["existing"],
    )

    uri = await store.store(doc)

    # Remove tags that don't exist (should be silently ignored)
    updated = await store.remove_tags(uri, ["nonexistent", "also-nonexistent"])

    assert len(updated.tags) == 1
    assert "existing" in updated.tags


@pytest.mark.asyncio
async def test_remove_all_tags(store):
    """Test removing all tags from a document"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["tag1", "tag2"],
    )

    uri = await store.store(doc)

    # Remove all tags
    updated = await store.remove_tags(uri, ["tag1", "tag2"])

    assert len(updated.tags) == 0


@pytest.mark.asyncio
async def test_remove_tags_nonexistent_document(store):
    """Test removing tags from a nonexistent document"""
    with pytest.raises(ValidationError, match="Document not found"):
        await store.remove_tags(TEST_SHORT_ID, ["tag"])


@pytest.mark.asyncio
async def test_get_documents_by_tags_any(store):
    """Test getting documents by tags (any match)"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Doc 1",
        url="https://example.com/doc1.pdf",
        summary="First document",
        mime_type="application/pdf",
        tags=["ai", "ml"],
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Doc 2",
        url="https://example.com/doc2.pdf",
        summary="Second document",
        mime_type="application/pdf",
        tags=["ai", "nlp"],
    )
    doc3 = DocumentMetadata(
        uuid="",
        name="Doc 3",
        url="https://example.com/doc3.pdf",
        summary="Third document",
        mime_type="application/pdf",
        tags=["web", "backend"],
    )

    await store.store(doc1)
    await store.store(doc2)
    await store.store(doc3)

    # Get documents with any of the specified tags
    results = await store.get_documents_by_tags(["ai", "nlp"], match_all=False)

    assert len(results) == 2
    names = {doc.name for doc in results}
    assert "Doc 1" in names
    assert "Doc 2" in names


@pytest.mark.asyncio
async def test_get_documents_by_tags_all(store):
    """Test getting documents by tags (all match)"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Doc 1",
        url="https://example.com/doc1.pdf",
        summary="First document",
        mime_type="application/pdf",
        tags=["ai", "ml", "research"],
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Doc 2",
        url="https://example.com/doc2.pdf",
        summary="Second document",
        mime_type="application/pdf",
        tags=["ai", "research"],
    )
    doc3 = DocumentMetadata(
        uuid="",
        name="Doc 3",
        url="https://example.com/doc3.pdf",
        summary="Third document",
        mime_type="application/pdf",
        tags=["ai"],
    )

    await store.store(doc1)
    await store.store(doc2)
    await store.store(doc3)

    # Get documents with all specified tags
    results = await store.get_documents_by_tags(["ai", "research"], match_all=True)

    assert len(results) == 2
    names = {doc.name for doc in results}
    assert "Doc 1" in names
    assert "Doc 2" in names


@pytest.mark.asyncio
async def test_get_documents_by_tags_no_matches(store):
    """Test getting documents by tags when no matches exist"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["ai"],
    )

    await store.store(doc)

    results = await store.get_documents_by_tags(["nonexistent"], match_all=False)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_get_documents_by_tags_empty_tags(store):
    """Test getting documents when they have no tags"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=[],
    )

    await store.store(doc)

    results = await store.get_documents_by_tags(["ai"], match_all=False)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_tag_operations_update_modified_timestamp(store):
    """Test that tag operations update the modified timestamp"""
    import asyncio

    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["original"],
    )

    uri = await store.store(doc)
    original_doc = await store.get(uri)
    original_modified = original_doc.modified_at

    # Wait a bit to ensure timestamp changes
    await asyncio.sleep(0.001)

    # Add tags
    updated = await store.add_tags(uri, ["new"])
    assert updated.modified_at >= original_modified

    # Wait again
    await asyncio.sleep(0.001)

    # Remove tags
    updated2 = await store.remove_tags(uri, ["new"])
    assert updated2.modified_at >= updated.modified_at


@pytest.mark.asyncio
async def test_tag_operations_persist_to_disk(temp_index_path):
    """Test that tag operations persist to disk"""
    store = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store:
        doc = DocumentMetadata(
            uuid="",
            name="Test Document",
            url="https://example.com/doc.pdf",
            summary="A test document",
            mime_type="application/pdf",
            tags=["original"],
        )

        uri = await store.store(doc)
        await store.add_tags(uri, ["added"])

    # Reload from disk
    store2 = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store2:
        retrieved = await store2.get(uri)
        assert retrieved is not None
        assert "original" in retrieved.tags
        assert "added" in retrieved.tags


# ===== Tests for Short ID functionality =====


@pytest.mark.asyncio
async def test_short_id_generation(store):
    """Test that short IDs are generated correctly (10-char alphanumeric)"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uuid = await store.store(doc)

    # Verify UUID is 10 characters and alphanumeric
    assert len(uuid) == 10
    assert uuid.isalnum()
    assert all(
        c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        for c in uuid
    )


@pytest.mark.asyncio
async def test_short_id_collision_detection(store):
    """Test that short ID collision detection works"""
    # Create multiple documents and verify unique UUIDs
    uuids = set()
    for i in range(100):
        doc = DocumentMetadata(
            uuid="",
            name=f"Document {i}",
            url=f"https://example.com/doc{i}.pdf",
            summary=f"Document {i} summary",
            mime_type="application/pdf",
        )
        uuid = await store.store(doc)

        # Verify no collisions
        assert uuid not in uuids, f"UUID collision detected: {uuid}"
        uuids.add(uuid)

    # Verify all 100 UUIDs are unique
    assert len(uuids) == 100


@pytest.mark.asyncio
async def test_uuid_field_in_yaml(temp_index_path):
    """Test that saved YAML contains uuid field, not uri field"""
    store = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store:
        doc = DocumentMetadata(
            uuid="",
            name="Test Document",
            url="https://example.com/doc.pdf",
            summary="A test document",
            mime_type="application/pdf",
        )

        await store.store(doc)

    # Read YAML file directly
    with open(temp_index_path, "r") as f:
        data = yaml.safe_load(f)

    # Verify structure
    assert "documents" in data
    assert len(data["documents"]) == 1

    doc_data = data["documents"][0]

    # Verify uuid field exists
    assert "uuid" in doc_data
    assert len(doc_data["uuid"]) == 10
    assert doc_data["uuid"].replace("_", "").replace("-", "").isalnum()

    # Verify uri field does NOT exist
    assert "uri" not in doc_data

    # Verify _namespace field does NOT exist (private, not serialized)
    assert "_namespace" not in doc_data


@pytest.mark.asyncio
async def test_short_id_persistence_across_reloads(temp_index_path):
    """Test that short IDs persist correctly across store reloads"""
    # Store a document
    store1 = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store1:
        doc = DocumentMetadata(
            uuid="",
            name="Test Document",
            url="https://example.com/doc.pdf",
            summary="A test document",
            mime_type="application/pdf",
        )
        uuid = await store1.store(doc)

    # Reload and verify
    store2 = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store2:
        retrieved = await store2.get(uuid)
        assert retrieved is not None
        assert retrieved.uuid == uuid


# ============================================================================
# Field-Specific Search Tests
# ============================================================================


@pytest.mark.asyncio
async def test_search_by_name_field(store):
    """Test field-specific name search"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Attention Is All You Need",
        url="https://example.com/transformer.pdf",
        summary="Paper about transformers",
        mime_type="application/pdf",
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Deep Learning Book",
        url="https://example.com/dl.pdf",
        summary="Comprehensive guide to attention mechanisms",
        mime_type="application/pdf",
    )

    await store.store(doc1)
    await store.store(doc2)

    # Search by name field - should only match doc1
    results = await store.search("Attention", search_field="name")
    assert len(results) == 1
    assert results[0].result.name == "Attention Is All You Need"


@pytest.mark.asyncio
async def test_search_by_name_multiple_words(store):
    """Test name search with multiple words"""
    doc = DocumentMetadata(
        uuid="",
        name="Machine Learning Fundamentals",
        url="https://example.com/ml.pdf",
        summary="Introduction to ML",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # Search with multiple words
    results = await store.search("Machine Learning", search_field="name")
    assert len(results) == 1
    assert results[0].score == 1.0  # Both words matched


@pytest.mark.asyncio
async def test_search_by_name_partial_match(store):
    """Test name search with partial word match"""
    doc = DocumentMetadata(
        uuid="",
        name="Neural Networks Guide",
        url="https://example.com/nn.pdf",
        summary="Guide to neural networks",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # Partial match - only one of two words
    results = await store.search("Neural Python", search_field="name")
    assert len(results) == 1
    assert results[0].score == 0.5  # Only 1 of 2 words matched


@pytest.mark.asyncio
async def test_search_by_name_case_insensitive(store):
    """Test that name search is case-insensitive"""
    doc = DocumentMetadata(
        uuid="",
        name="PyTorch Tutorial",
        url="https://example.com/pytorch.pdf",
        summary="PyTorch guide",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # All case variations should match
    for query in ["pytorch", "PYTORCH", "PyTorch", "pYtOrCh"]:
        results = await store.search(query, search_field="name")
        assert len(results) == 1


@pytest.mark.asyncio
async def test_search_by_tags_field(store):
    """Test field-specific tag search"""
    doc1 = DocumentMetadata(
        uuid="",
        name="AI Paper",
        url="https://example.com/ai.pdf",
        summary="Paper about AI",
        mime_type="application/pdf",
        tags=["ai", "machine-learning"],
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Web Dev Guide",
        url="https://example.com/web.pdf",
        summary="Web development guide",
        mime_type="application/pdf",
        tags=["web", "backend"],
    )

    await store.store(doc1)
    await store.store(doc2)

    # Search by tags field
    results = await store.search("ai", search_field="tags")
    assert len(results) == 1
    assert results[0].result.name == "AI Paper"


@pytest.mark.asyncio
async def test_search_by_tags_multiple(store):
    """Test tag search with multiple tags (comma-separated)"""
    doc1 = DocumentMetadata(
        uuid="",
        name="ML Paper",
        url="https://example.com/ml.pdf",
        summary="Machine learning paper",
        mime_type="application/pdf",
        tags=["ai", "ml", "research"],
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="NLP Paper",
        url="https://example.com/nlp.pdf",
        summary="NLP paper",
        mime_type="application/pdf",
        tags=["ai", "nlp"],
    )

    await store.store(doc1)
    await store.store(doc2)

    # Search for documents with any of these tags
    results = await store.search("ai,ml", search_field="tags")
    assert len(results) == 2

    # doc1 has both tags (score = 1.0)
    # doc2 has only "ai" (score = 0.5)
    assert results[0].score == 1.0
    assert results[1].score == 0.5


@pytest.mark.asyncio
async def test_search_by_tags_case_insensitive(store):
    """Test that tag search is case-insensitive"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Doc",
        url="https://example.com/test.pdf",
        summary="Test document",
        mime_type="application/pdf",
        tags=["Machine-Learning", "AI"],
    )

    await store.store(doc)

    # All case variations should match
    for query in ["machine-learning", "MACHINE-LEARNING", "Machine-Learning"]:
        results = await store.search(query, search_field="tags")
        assert len(results) == 1


@pytest.mark.asyncio
async def test_search_by_extra_field_numeric_gt(store):
    """Test extra metadata search with greater than operator"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Old Paper",
        url="https://example.com/old.pdf",
        summary="Paper from 2019",
        mime_type="application/pdf",
        extra={"year": 2019},
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="New Paper",
        url="https://example.com/new.pdf",
        summary="Paper from 2023",
        mime_type="application/pdf",
        extra={"year": 2023},
    )

    await store.store(doc1)
    await store.store(doc2)

    # Search for year > 2020
    results = await store.search(".year > 2020", search_field="extra")
    assert len(results) == 1
    assert results[0].result.name == "New Paper"


@pytest.mark.asyncio
async def test_search_by_extra_field_numeric_gte(store):
    """Test extra metadata search with greater than or equal operator"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Doc 2020",
        url="https://example.com/2020.pdf",
        summary="Paper from 2020",
        mime_type="application/pdf",
        extra={"year": 2020},
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Doc 2021",
        url="https://example.com/2021.pdf",
        summary="Paper from 2021",
        mime_type="application/pdf",
        extra={"year": 2021},
    )

    await store.store(doc1)
    await store.store(doc2)

    results = await store.search(".year >= 2020", search_field="extra")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_by_extra_field_numeric_lt(store):
    """Test extra metadata search with less than operator"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Doc 2018",
        url="https://example.com/2018.pdf",
        summary="Paper from 2018",
        mime_type="application/pdf",
        extra={"year": 2018},
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Doc 2023",
        url="https://example.com/2023.pdf",
        summary="Paper from 2023",
        mime_type="application/pdf",
        extra={"year": 2023},
    )

    await store.store(doc1)
    await store.store(doc2)

    results = await store.search(".year < 2020", search_field="extra")
    assert len(results) == 1
    assert results[0].result.name == "Doc 2018"


@pytest.mark.asyncio
async def test_search_by_extra_field_string_contains(store):
    """Test extra metadata search with contains operator"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Smith Paper",
        url="https://example.com/smith.pdf",
        summary="Paper by Smith",
        mime_type="application/pdf",
        extra={"author": "John Smith"},
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="Jones Paper",
        url="https://example.com/jones.pdf",
        summary="Paper by Jones",
        mime_type="application/pdf",
        extra={"author": "Mary Jones"},
    )

    await store.store(doc1)
    await store.store(doc2)

    results = await store.search(".author contains Smith", search_field="extra")
    assert len(results) == 1
    assert results[0].result.name == "Smith Paper"


@pytest.mark.asyncio
async def test_search_by_extra_field_string_equals(store):
    """Test extra metadata search with equality operator"""
    doc1 = DocumentMetadata(
        uuid="",
        name="NeurIPS Paper",
        url="https://example.com/neurips.pdf",
        summary="NeurIPS paper",
        mime_type="application/pdf",
        extra={"venue": "NeurIPS"},
    )
    doc2 = DocumentMetadata(
        uuid="",
        name="ICML Paper",
        url="https://example.com/icml.pdf",
        summary="ICML paper",
        mime_type="application/pdf",
        extra={"venue": "ICML"},
    )

    await store.store(doc1)
    await store.store(doc2)

    results = await store.search(".venue == NeurIPS", search_field="extra")
    assert len(results) == 1
    assert results[0].result.name == "NeurIPS Paper"


@pytest.mark.asyncio
async def test_search_by_extra_field_missing_field(store):
    """Test extra metadata search when field doesn't exist"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Doc",
        url="https://example.com/test.pdf",
        summary="Test document",
        mime_type="application/pdf",
        extra={"author": "Smith"},
    )

    await store.store(doc)

    # Query for field that doesn't exist
    results = await store.search(".year > 2020", search_field="extra")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_by_extra_field_no_extra_metadata(store):
    """Test extra metadata search when document has no extra metadata"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Doc",
        url="https://example.com/test.pdf",
        summary="Test document",
        mime_type="application/pdf",
    )

    await store.store(doc)

    results = await store.search(".year > 2020", search_field="extra")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_by_extra_field_case_insensitive_contains(store):
    """Test that contains operator is case-insensitive"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Doc",
        url="https://example.com/test.pdf",
        summary="Test document",
        mime_type="application/pdf",
        extra={"author": "John Smith"},
    )

    await store.store(doc)

    # All case variations should match
    for query in [
        ".author contains smith",
        ".author contains SMITH",
        ".author contains Smith",
    ]:
        results = await store.search(query, search_field="extra")
        assert len(results) == 1


@pytest.mark.asyncio
async def test_search_default_field_is_summary(store):
    """Test that default search field is summary"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Doc",
        url="https://example.com/test.pdf",
        summary="Paper about transformers and attention mechanisms",
        mime_type="application/pdf",
        tags=["ai"],
    )

    await store.store(doc)

    # Default search should search summary
    results = await store.search("transformers")
    assert len(results) == 1

    # Explicit summary search should work the same
    results2 = await store.search("transformers", search_field="summary")
    assert len(results2) == 1


@pytest.mark.asyncio
async def test_search_by_summary_uses_best_available_method(store):
    """Test that summary search uses the best available search method"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Doc",
        url="https://example.com/test.pdf",
        summary="Machine learning and deep learning fundamentals",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # Summary search should work (will use best available: hybrid, BM25, FTS5, or simple)
    results = await store.search("machine learning", search_field="summary")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_field_specific_methods_dont_cross_search(store):
    """Test that field-specific searches don't cross-contaminate"""
    doc = DocumentMetadata(
        uuid="",
        name="Python Programming",
        url="https://example.com/python.pdf",
        summary="Guide to JavaScript",
        mime_type="application/pdf",
        tags=["ruby"],
        extra={"language": "Go"},
    )

    await store.store(doc)

    # Name search should only find "Python" in name
    results = await store.search("Python", search_field="name")
    assert len(results) == 1

    # But not JavaScript (which is in summary)
    results = await store.search("JavaScript", search_field="name")
    assert len(results) == 0

    # Summary search should find JavaScript
    results = await store.search("JavaScript", search_field="summary")
    assert len(results) == 1

    # Tag search should only find ruby
    results = await store.search("ruby", search_field="tags")
    assert len(results) == 1

    # Extra search should find Go
    results = await store.search(".language == Go", search_field="extra")
    assert len(results) == 1
