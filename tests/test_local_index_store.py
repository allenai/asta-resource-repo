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

    uri = await store.store(doc)

    assert uri.startswith("asta://")
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
            uri="",
            name=f"Test Document {i}",
            url=url,
            summary=f"Test document with {url.split('://')[0]} protocol",
            mime_type="application/pdf",
        )

        # Should not raise ValidationError
        uri = await store.store(doc)
        assert uri.startswith("asta://")

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
    assert retrieved.uri == uri
    assert retrieved.name == "Test Document"
    assert retrieved.url == "https://example.com/doc.pdf"
    assert retrieved.summary == "A test document"
    assert retrieved.tags == ["test"]


@pytest.mark.asyncio
async def test_get_nonexistent_document(store):
    """Test getting a document that doesn't exist"""
    from asta.resources.model import construct_document_uri

    uri = construct_document_uri(store.namespace, TEST_SHORT_ID)
    result = await store.get(uri)
    assert result is None


@pytest.mark.asyncio
async def test_get_validates_namespace(store):
    """Test that get validates namespace matches"""
    from asta.resources.model import construct_document_uri

    # Use a different namespace than the store's
    wrong_namespace = "wrong-namespace-different-from-store"
    uri = construct_document_uri(wrong_namespace, TEST_SHORT_ID)
    with pytest.raises(ValidationError, match="Namespace mismatch"):
        await store.get(uri)


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
    """Test searching documents by name"""
    doc1 = DocumentMetadata(
        uuid="",
        name="Python Programming",
        url="https://example.com/python.pdf",
        summary="A guide to Python",
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

    # Use keyword search to test exact matching (not semantic)
    results = await store.search("Python", search_mode="keyword")
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

    # Use keyword search to test exact matching (semantic might find related programming languages)
    results = await store.search("Rust programming", search_mode="keyword")
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
    from asta.resources.model import construct_document_uri

    uri = construct_document_uri(store.namespace, TEST_SHORT_ID)
    deleted = await store.delete(uri)
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

    from asta.resources.model import construct_document_uri

    fake_uri = construct_document_uri(store.namespace, TEST_SHORT_ID)
    assert not await store.exists(fake_uri)


@pytest.mark.asyncio
async def test_exists_wrong_namespace(store):
    """Test exists with wrong namespace returns False"""
    from asta.resources.model import construct_document_uri

    wrong_namespace = "wrong-namespace-different-from-store"
    uri = construct_document_uri(wrong_namespace, TEST_SHORT_ID)
    assert not await store.exists(uri)


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
    results = await store.search("transformer", search_mode="fts5")
    assert len(results) >= 1
    assert "Transformer" in results[0].result.summary

    # Search for "NLP" should find two documents
    results = await store.search("nlp", search_mode="fts5")
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
    results = await store.search("transformers", search_mode="fts5")
    assert len(results) >= 2

    # The document with "transformers" in summary should score highest
    assert (
        "transformers" in results[0].result.summary.lower()
        or "transformers" in results[0].result.name.lower()
    )


@pytest.mark.asyncio
async def test_search_mode_auto_selects_fts5(store):
    """Test that auto mode selects FTS5 when available"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    await store.store(doc)

    # Auto mode should select hybrid if embeddings are available, otherwise FTS5
    selected_mode = store._determine_search_mode()
    if store._embedding_manager:
        assert selected_mode == "hybrid"
    elif store._search_cache and store._search_cache._initialized:
        assert selected_mode == "bm25"
    else:
        assert selected_mode == "simple"


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
    results = await store.search("neural networks", search_mode="fts5")
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
        results = await store.search("First", search_mode="fts5")
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
        results = await store.search("document", search_mode="fts5")
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
    from asta.resources.model import construct_document_uri

    uri = construct_document_uri(store.namespace, TEST_SHORT_ID)

    with pytest.raises(ValidationError, match="Document not found"):
        await store.update(uri, name="New Name")


@pytest.mark.asyncio
async def test_update_validates_namespace(store):
    """Test that update validates namespace matches"""
    from asta.resources.model import construct_document_uri

    wrong_namespace = "wrong-namespace"
    uri = construct_document_uri(wrong_namespace, TEST_SHORT_ID)

    with pytest.raises(ValidationError, match="Namespace mismatch"):
        await store.update(uri, name="New Name")


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
    # Use a properly formatted URI with UUID
    fake_uri = f"asta://{store.namespace}/{TEST_SHORT_ID}"
    with pytest.raises(ValidationError, match="Document not found"):
        await store.add_tags(fake_uri, ["tag"])


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
    """Test removing tags from a non-existent document raises error"""
    # Use a properly formatted URI with UUID
    fake_uri = f"asta://{store.namespace}/{TEST_SHORT_ID}"
    with pytest.raises(ValidationError, match="Document not found"):
        await store.remove_tags(fake_uri, ["tag"])


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

    uri = await store.store(doc)

    # Parse URI to extract UUID
    from asta.resources.model import parse_document_uri

    namespace, uuid = parse_document_uri(uri)

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
        uri = await store.store(doc)

        from asta.resources.model import parse_document_uri

        _, uuid = parse_document_uri(uri)

        # Verify no collisions
        assert uuid not in uuids, f"UUID collision detected: {uuid}"
        uuids.add(uuid)

    # Verify all 100 UUIDs are unique
    assert len(uuids) == 100


@pytest.mark.asyncio
async def test_namespace_injection(store):
    """Test that namespace is injected into loaded documents"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)
    retrieved = await store.get(uri)

    # Verify namespace is injected
    assert retrieved._namespace == store.namespace
    assert retrieved._namespace != ""


@pytest.mark.asyncio
async def test_uri_property_reconstruction(store):
    """Test that URI property correctly reconstructs full URI"""
    doc = DocumentMetadata(
        uuid="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)
    retrieved = await store.get(uri)

    # Verify URI is reconstructed correctly
    assert retrieved.uri == uri
    assert retrieved.uri.startswith("asta://")
    assert retrieved._namespace in retrieved.uri
    assert retrieved.uuid in retrieved.uri

    # Verify format
    from asta.resources.model import parse_document_uri

    namespace, uuid = parse_document_uri(retrieved.uri)
    assert namespace == store.namespace
    assert uuid == retrieved.uuid


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
        uri = await store1.store(doc)

        # Extract UUID
        from asta.resources.model import parse_document_uri

        _, uuid1 = parse_document_uri(uri)

    # Reload and verify
    store2 = LocalIndexDocumentStore(index_path=str(temp_index_path))
    async with store2:
        retrieved = await store2.get(uri)
        assert retrieved is not None
        assert retrieved.uuid == uuid1
        assert retrieved.uri == uri


@pytest.mark.asyncio
async def test_uri_parsing_with_short_ids(store):
    """Test that URI parsing works with short IDs"""
    from asta.resources.model import parse_document_uri, construct_document_uri

    # Test valid short ID
    short_id = "abc123XYZ0"
    uri = construct_document_uri(store.namespace, short_id)

    assert uri == f"asta://{store.namespace}/{short_id}"

    # Parse it back
    namespace, uuid = parse_document_uri(uri)
    assert namespace == store.namespace
    assert uuid == short_id


@pytest.mark.asyncio
async def test_invalid_short_id_format(store):
    """Test that invalid short ID formats are rejected"""
    from asta.resources.model import construct_document_uri
    from asta.resources.exceptions import ValidationError

    # Test too short
    with pytest.raises(ValidationError, match="10-character"):
        construct_document_uri(store.namespace, "abc123")

    # Test too long
    with pytest.raises(ValidationError, match="10-character"):
        construct_document_uri(store.namespace, "abc123xyz012")

    # Test invalid characters
    with pytest.raises(ValidationError, match="10-character"):
        construct_document_uri(store.namespace, "abc!@#$%^&")

    # Test spaces
    with pytest.raises(ValidationError, match="10-character"):
        construct_document_uri(store.namespace, "abc 123xyz")
