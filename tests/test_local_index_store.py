"""Tests for LocalIndexDocumentStore"""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path

from asta.resources.document_store.local_index import LocalIndexDocumentStore
from asta.resources.model import DocumentMetadata
from asta.resources.exceptions import ValidationError


@pytest.fixture
def temp_index_path():
    """Create a temporary directory for test index files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / ".asta" / "index.yaml"
        yield index_path


@pytest_asyncio.fixture
async def store(temp_index_path):
    """Create a LocalIndexDocumentStore instance for testing"""
    store = LocalIndexDocumentStore(
        namespace="test-namespace",
        resource_type="document",
        index_path=str(temp_index_path),
    )
    async with store:
        yield store


@pytest.mark.asyncio
async def test_initialize_creates_index_file(temp_index_path):
    """Test that initialize creates the index file and directory"""
    assert not temp_index_path.exists()

    store = LocalIndexDocumentStore(
        namespace="test",
        resource_type="document",
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
        uri="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
        tags=["test", "example"],
        extra={"author": "Test Author"},
    )

    uri = await store.store(doc)

    assert uri.startswith("asta://test-namespace/document/")
    assert doc.created_at is not None
    assert doc.modified_at is not None


@pytest.mark.asyncio
async def test_store_validates_url(store):
    """Test that store validates URL format"""
    doc = DocumentMetadata(
        uri="",
        name="Test Document",
        url="invalid-url",
        summary="A test document",
        mime_type="application/pdf",
    )

    with pytest.raises(ValidationError, match="Invalid URL format"):
        await store.store(doc)


@pytest.mark.asyncio
async def test_store_requires_summary(store):
    """Test that store requires summary field"""
    doc = DocumentMetadata(
        uri="",
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
        uri="",
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
    uri = "asta://test-namespace/document/00000000-0000-0000-0000-000000000000"
    result = await store.get(uri)
    assert result is None


@pytest.mark.asyncio
async def test_get_validates_namespace(store):
    """Test that get validates namespace matches"""
    uri = "asta://wrong-namespace/document/00000000-0000-0000-0000-000000000000"
    with pytest.raises(ValidationError, match="Namespace mismatch"):
        await store.get(uri)


@pytest.mark.asyncio
async def test_list_documents(store):
    """Test listing all documents"""
    # Add multiple documents
    docs = [
        DocumentMetadata(
            uri="",
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
        uri="",
        name="Python Programming",
        url="https://example.com/python.pdf",
        summary="A guide to Python",
        mime_type="application/pdf",
    )
    doc2 = DocumentMetadata(
        uri="",
        name="JavaScript Guide",
        url="https://example.com/js.pdf",
        summary="Learning JavaScript",
        mime_type="application/pdf",
    )

    await store.store(doc1)
    await store.store(doc2)

    results = await store.search("Python")
    assert len(results) == 1
    assert results[0].result.name == "Python Programming"


@pytest.mark.asyncio
async def test_search_by_summary(store):
    """Test searching documents by summary"""
    doc = DocumentMetadata(
        uri="",
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
        uri="",
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
        uri="",
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
            uri="",
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
        uri="",
        name="JavaScript Guide",
        url="https://example.com/js.pdf",
        summary="Learn JavaScript",
        mime_type="application/pdf",
    )

    await store.store(doc)

    results = await store.search("Rust programming")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_delete_document(store):
    """Test deleting a document"""
    doc = DocumentMetadata(
        uri="",
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
    uri = "asta://test-namespace/document/00000000-0000-0000-0000-000000000000"
    deleted = await store.delete(uri)
    assert deleted is False


@pytest.mark.asyncio
async def test_exists(store):
    """Test checking if a document exists"""
    doc = DocumentMetadata(
        uri="",
        name="Test Document",
        url="https://example.com/doc.pdf",
        summary="A test document",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)
    assert await store.exists(uri)

    fake_uri = "asta://test-namespace/document/00000000-0000-0000-0000-000000000000"
    assert not await store.exists(fake_uri)


@pytest.mark.asyncio
async def test_exists_wrong_namespace(store):
    """Test exists with wrong namespace returns False"""
    uri = "asta://wrong-namespace/document/00000000-0000-0000-0000-000000000000"
    assert not await store.exists(uri)


@pytest.mark.asyncio
async def test_persistence(temp_index_path):
    """Test that documents persist across store instances"""
    # Create and populate first store
    store1 = LocalIndexDocumentStore(
        namespace="test",
        resource_type="document",
        index_path=str(temp_index_path),
    )
    async with store1:
        doc = DocumentMetadata(
            uri="",
            name="Persistent Document",
            url="https://example.com/doc.pdf",
            summary="A persistent document",
            mime_type="application/pdf",
        )
        uri = await store1.store(doc)

    # Create new store instance and verify document persists
    store2 = LocalIndexDocumentStore(
        namespace="test",
        resource_type="document",
        index_path=str(temp_index_path),
    )
    async with store2:
        retrieved = await store2.get(uri)
        assert retrieved is not None
        assert retrieved.name == "Persistent Document"


@pytest.mark.asyncio
async def test_update_document(store):
    """Test updating a document by storing with same URI"""
    doc = DocumentMetadata(
        uri="",
        name="Original Name",
        url="https://example.com/doc.pdf",
        summary="Original summary",
        mime_type="application/pdf",
    )

    uri = await store.store(doc)

    # Update the document
    doc.uri = uri
    doc.name = "Updated Name"
    doc.summary = "Updated summary"
    doc.tags = ["updated"]

    await store.store(doc)

    # Retrieve and verify update
    retrieved = await store.get(uri)
    assert retrieved.name == "Updated Name"
    assert retrieved.summary == "Updated summary"
    assert retrieved.tags == ["updated"]


@pytest.mark.asyncio
async def test_extra_metadata(store):
    """Test storing and retrieving extra metadata"""
    doc = DocumentMetadata(
        uri="",
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
        uri="",
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
