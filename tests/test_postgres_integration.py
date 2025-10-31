"""Integration tests for PostgreSQL backend"""

import base64
from datetime import datetime

import pytest
import pytest_asyncio

from asta.resources.config import load_config
from asta.resources.exceptions import ValidationError
from asta.resources.model import DocumentMetadata, Document


@pytest_asyncio.fixture
async def postgres_store():
    """Create a PostgreSQL document store for testing using config"""
    config = load_config()
    async with config.storage.document_store() as store:
        yield store

        # Cleanup: Delete all test documents
        if store.pool:
            async with store.pool.acquire() as conn:
                await conn.execute("DELETE FROM documents")


@pytest.mark.asyncio
async def test_postgres_upload_and_retrieve(postgres_store):
    """Test uploading and retrieving a document from PostgreSQL"""

    test_content = "This is a test document stored in PostgreSQL."

    doc_metadata = DocumentMetadata(
        uri="",
        name="postgres_test.txt",
        mime_type="text/plain",
        extra={"title": "PostgreSQL Test", "tags": ["test", "postgres"]},
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content=test_content,
    ).to_binary()

    doc_id = await postgres_store.store(document)
    assert doc_id is not None
    assert len(doc_id) > 0

    # Retrieve the document
    retrieved_doc = await postgres_store.get(doc_id)

    assert retrieved_doc is not None
    assert retrieved_doc.metadata.uri == doc_id
    assert retrieved_doc.metadata.name == "postgres_test.txt"
    assert retrieved_doc.metadata.mime_type == "text/plain"
    assert retrieved_doc.metadata.extra["title"] == "PostgreSQL Test"
    assert "test" in retrieved_doc.metadata.extra["tags"]
    assert retrieved_doc.content.decode("utf-8") == test_content


@pytest.mark.asyncio
async def test_postgres_list_documents(postgres_store):
    """Test listing documents from PostgreSQL"""

    # Upload multiple documents
    doc1_metadata = DocumentMetadata(
        uri="",
        name="doc1.txt",
        mime_type="text/plain",
        extra={"priority": "high"},
        created_at=datetime.now(),
    )

    document1 = Document(
        metadata=doc1_metadata,
        content="First document in PostgreSQL",
    ).to_binary()

    doc1_id = await postgres_store.store(document1)

    doc2_metadata = DocumentMetadata(
        uri="",
        name="doc2.json",
        mime_type="application/json",
        extra={"priority": "low"},
        created_at=datetime.now(),
    )

    document2 = Document(
        metadata=doc2_metadata,
        content='{"key": "value"}',
    ).to_binary()

    doc2_id = await postgres_store.store(document2)

    # List all documents
    documents = await postgres_store.list_docs()

    assert len(documents) >= 2
    doc_ids = [doc.uri for doc in documents]
    assert doc1_id in doc_ids
    assert doc2_id in doc_ids

    # Verify sorting (newest first)
    assert documents[0].created_at >= documents[-1].created_at


@pytest.mark.asyncio
async def test_postgres_search_documents(postgres_store):
    """Test full-text search in PostgreSQL"""

    # Upload documents with searchable content
    doc_metadata = DocumentMetadata(
        uri="",
        name="search_test.txt",
        mime_type="text/plain",
        extra={"tags": ["python", "programming"]},
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="This document contains information about Python programming and FastMCP framework.",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Search by content
    results = await postgres_store.search("Python", limit=10)
    assert len(results) > 0
    assert any(hit.result.uri == doc_id for hit in results)

    # Search by tag
    results = await postgres_store.search("programming", limit=10)
    assert len(results) > 0
    assert any(hit.result.uri == doc_id for hit in results)

    # Search by filename
    results = await postgres_store.search("search_test", limit=10)
    assert len(results) > 0
    assert any(hit.result.uri == doc_id for hit in results)


@pytest.mark.asyncio
async def test_postgres_search_no_results(postgres_store):
    """Test search with no matching results"""

    # Upload a document
    doc_metadata = DocumentMetadata(
        uri="",
        name="unique_doc.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="This document is about cats and dogs",
    ).to_binary()

    await postgres_store.store(document)

    # Search for something that doesn't exist
    results = await postgres_store.search("elephants", limit=10)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_postgres_binary_document(postgres_store):
    """Test storing and retrieving binary documents (PDFs)"""

    # Create fake PDF content
    fake_pdf_content = b"%PDF-1.4\n%fake pdf content with binary data\x00\x01\x02"
    encoded_content = base64.b64encode(fake_pdf_content).decode("utf-8")

    doc_metadata = DocumentMetadata(
        uri="",
        name="test.pdf",
        mime_type="application/pdf",
        extra={"title": "Test PDF Document", "author": "Test User"},
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content=encoded_content,
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Retrieve and verify
    retrieved_doc = await postgres_store.get(doc_id)
    assert retrieved_doc is not None
    assert retrieved_doc.metadata.mime_type == "application/pdf"
    assert retrieved_doc.metadata.extra["title"] == "Test PDF Document"
    assert retrieved_doc.content == fake_pdf_content


@pytest.mark.asyncio
async def test_postgres_get_nonexistent_document(postgres_store):
    """Test retrieving a document that doesn't exist"""

    # Generate a properly formatted but non-existent document ID
    import uuid

    fake_uuid = str(uuid.uuid4())
    fake_doc_id = f"asta://{postgres_store.namespace}/{postgres_store.resource_type}/{fake_uuid}"

    result = await postgres_store.get(fake_doc_id)
    assert result is None


@pytest.mark.asyncio
async def test_postgres_exists_check(postgres_store):
    """Test the exists() method"""

    # Upload a document
    doc_metadata = DocumentMetadata(
        uri="",
        name="exists_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="Test content for exists check",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Check existence
    assert await postgres_store.exists(doc_id) is True

    # Generate a properly formatted but non-existent document ID
    import uuid

    fake_uuid = str(uuid.uuid4())
    fake_doc_id = f"asta://{postgres_store.namespace}/{postgres_store.resource_type}/{fake_uuid}"
    assert await postgres_store.exists(fake_doc_id) is False


@pytest.mark.asyncio
async def test_postgres_delete_document(postgres_store):
    """Test deleting a document"""

    # Upload a document
    doc_metadata = DocumentMetadata(
        uri="",
        name="delete_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="This document will be deleted",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Verify it exists
    assert await postgres_store.exists(doc_id) is True

    # Delete it
    success = await postgres_store.delete(doc_id)
    assert success is True

    # Verify it's gone
    assert await postgres_store.exists(doc_id) is False
    assert await postgres_store.get(doc_id) is None

    # Try deleting again (should return False)
    success = await postgres_store.delete(doc_id)
    assert success is False


@pytest.mark.asyncio
async def test_postgres_large_document(postgres_store):
    """Test storing a large document"""

    # Create a large document (1MB)
    large_content = "A" * (1024 * 1024)  # 1MB of 'A' characters

    doc_metadata = DocumentMetadata(
        uri="",
        name="large_doc.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content=large_content,
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Retrieve and verify
    retrieved_doc = await postgres_store.get(doc_id)
    assert retrieved_doc is not None
    assert len(retrieved_doc.content) == 1024 * 1024
    assert retrieved_doc.metadata.size == 1024 * 1024


@pytest.mark.asyncio
async def test_postgres_search_limit(postgres_store):
    """Test search result limit"""

    # Upload multiple documents
    for i in range(5):
        doc_metadata = DocumentMetadata(
            uri="",
            name=f"doc{i}.txt",
            mime_type="text/plain",
            extra={"index": i},
            created_at=datetime.now(),
        )

        document = Document(
            metadata=doc_metadata,
            content=f"Document {i} about testing search functionality",
        ).to_binary()

        await postgres_store.store(document)

    # Search with limit
    results = await postgres_store.search("testing", limit=3)
    assert len(results) <= 3

    results = await postgres_store.search("testing", limit=10)
    assert len(results) >= 5  # Should find all 5 documents


@pytest.mark.asyncio
async def test_postgres_search_snippet(postgres_store):
    """Test that search results are returned correctly"""

    doc_metadata = DocumentMetadata(
        uri="",
        name="snippet_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="This is a very long document with lots of text. "
        "The keyword appears here in the middle. "
        "And there's more text after the keyword for context.",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Search for keyword
    results = await postgres_store.search("keyword", limit=10)

    assert len(results) > 0
    hit = next((h for h in results if h.result.uri == doc_id), None)
    assert hit is not None
    assert hit.result.name == "snippet_test.txt"


@pytest.mark.asyncio
async def test_postgres_connection_pool(postgres_store):
    """Test that connection pooling works correctly"""

    # Perform multiple operations in parallel
    import asyncio

    async def upload_doc(index: int) -> str:
        doc_metadata = DocumentMetadata(
            uri="",
            name=f"parallel_doc{index}.txt",
            mime_type="text/plain",
            created_at=datetime.now(),
        )

        document = Document(
            metadata=doc_metadata,
            content=f"Document {index} for parallel testing",
        ).to_binary()

        return await postgres_store.store(document)

    # Upload 10 documents in parallel
    doc_ids = await asyncio.gather(*[upload_doc(i) for i in range(10)])

    assert len(doc_ids) == 10
    assert all(doc_id is not None for doc_id in doc_ids)

    # Verify all documents were stored
    documents = await postgres_store.list_docs()
    assert len(documents) >= 10


@pytest.mark.asyncio
async def test_document_id_validation(postgres_store):
    """Test document ID validation enforces asta://{namespace}/{resource_type}/{uuid} format"""

    # Upload a document to get a valid ID
    doc_metadata = DocumentMetadata(
        uri="",
        name="validation_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="Test document for ID validation",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Valid URI should work
    retrieved = await postgres_store.get(doc_id)
    assert retrieved is not None
    assert retrieved.metadata.uri == doc_id

    # Test invalid formats
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.get("just-a-uuid")

    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.get("too/many/parts/here/now")

    # Test mismatched namespace
    # doc_id is now "asta://{namespace}/{resource_type}/{uuid}"
    parts = doc_id.replace("asta://", "").split("/")
    uuid_part = parts[2]
    resource_type_part = parts[1]
    wrong_namespace_id = f"asta://wrong_namespace/{resource_type_part}/{uuid_part}"

    with pytest.raises(ValidationError):
        await postgres_store.get(wrong_namespace_id)

    # Test mismatched resource_type
    wrong_resource_type_id = f"asta://{postgres_store.namespace}/wrong_type/{uuid_part}"

    with pytest.raises(ValidationError):
        await postgres_store.get(wrong_resource_type_id)

    # Test invalid UUID format (regex won't match invalid characters)
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.get(f"asta://{postgres_store.namespace}/{postgres_store.resource_type}/not-a-valid-uuid")

    # Test empty UUID part - regex won't match
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.get(f"asta://{postgres_store.namespace}/{postgres_store.resource_type}/")

    # Test empty namespace part
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.get(f"asta:///{postgres_store.resource_type}/{uuid_part}")

    # Test empty resource_type part
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.get(f"asta://{postgres_store.namespace}//{uuid_part}")


@pytest.mark.asyncio
async def test_document_id_validation_on_delete(postgres_store):
    """Test document ID validation on delete operations"""

    # Upload a document
    doc_metadata = DocumentMetadata(
        uri="",
        name="delete_validation_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="Test document for delete validation",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Test invalid ID format on delete
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.delete("just-a-uuid")

    # Test mismatched namespace on delete
    # doc_id is now "asta://{namespace}/{resource_type}/{uuid}"
    parts = doc_id.replace("asta://", "").split("/")
    uuid_part = parts[2]
    resource_type_part = parts[1]
    wrong_namespace_id = f"asta://wrong_namespace/{resource_type_part}/{uuid_part}"

    with pytest.raises(ValidationError):
        await postgres_store.delete(wrong_namespace_id)

    # Valid delete should work
    success = await postgres_store.delete(doc_id)
    assert success is True


@pytest.mark.asyncio
async def test_document_id_validation_on_exists(postgres_store):
    """Test document ID validation on exists checks"""

    # Upload a document
    doc_metadata = DocumentMetadata(
        uri="",
        name="exists_validation_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="Test document for exists validation",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Test invalid ID format on exists
    with pytest.raises(ValidationError, match="must be in format"):
        await postgres_store.exists("just-a-uuid")

    # Test mismatched namespace on exists
    # doc_id is now "asta://{namespace}/{resource_type}/{uuid}"
    parts = doc_id.replace("asta://", "").split("/")
    uuid_part = parts[2]
    resource_type_part = parts[1]
    wrong_namespace_id = f"asta://wrong_namespace/{resource_type_part}/{uuid_part}"

    with pytest.raises(ValidationError):
        await postgres_store.exists(wrong_namespace_id)

    # Valid exists check should work
    exists = await postgres_store.exists(doc_id)
    assert exists is True


@pytest.mark.asyncio
async def test_document_id_format_after_store(postgres_store):
    """Test that stored document IDs follow asta://{namespace}/{resource_type}/{uuid} format"""

    doc_metadata = DocumentMetadata(
        uri="",
        name="format_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="Test document for ID format check",
    ).to_binary()

    doc_id = await postgres_store.store(document)

    # Verify format starts with asta://
    assert doc_id.startswith("asta://")

    # Parse the ID
    rest = doc_id.replace("asta://", "")
    parts = rest.split("/")
    assert len(parts) == 3
    assert parts[0] == postgres_store.namespace
    assert parts[1] == postgres_store.resource_type

    # Verify UUID part is valid
    import uuid

    try:
        uuid.UUID(parts[2])
    except ValueError:
        pytest.fail(f"UUID part '{parts[2]}' is not a valid UUID")

    # Verify retrieved document has same URI
    retrieved = await postgres_store.get(doc_id)
    assert retrieved.metadata.uri == doc_id
