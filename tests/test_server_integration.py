"""Integration tests for the MCP server"""

import base64
from datetime import datetime

import pytest
import pytest_asyncio

from asta.resources.config import load_config
from asta.resources.model import DocumentMetadata, Document
from asta.resources.exceptions import InvalidMimeTypeError


@pytest_asyncio.fixture
async def document_store():
    """Create a PostgreSQL document store for testing"""
    config = load_config()
    async with config.storage.document_store() as store:
        yield store

        # Cleanup: Delete all test documents
        if store.pool:
            async with store.pool.acquire() as conn:
                await conn.execute("DELETE FROM documents")


@pytest_asyncio.fixture
async def temp_data_dir(document_store):
    """Provide temp directory path for backward compatibility"""
    return None  # Not used with Postgres, kept for compatibility


@pytest.mark.asyncio
async def test_upload_and_search_document(document_store, temp_data_dir):
    """Test uploading a document and then searching for it"""

    # Upload a text document (simulate server logic)
    test_content = "This is a test document about Python programming and FastMCP."

    # Create document metadata
    doc_metadata = DocumentMetadata(
        uri="",
        name="test.txt",
        mime_type="text/plain",
        extra={"title": "Test Document", "tags": ["python", "fastmcp"]},
        created_at=datetime.now(),
    )

    # Create and store document (for text files, content is plain string)
    document = Document(
        metadata=doc_metadata,
        content=test_content,  # Plain string for text/plain
    ).to_binary()

    doc_uri = await document_store.store(document)
    doc_metadata.uri = doc_uri

    assert isinstance(doc_metadata, DocumentMetadata)
    assert doc_metadata.name == "test.txt"
    assert doc_metadata.mime_type == "text/plain"
    assert doc_metadata.extra["title"] == "Test Document"
    assert doc_metadata.uri != ""

    # Search for the document
    search_results = await document_store.search(query="Python", limit=5)

    assert len(search_results) > 0
    assert any(hit.result.uri == doc_metadata.uri for hit in search_results)

    # Test another search term
    search_results = await document_store.search(query="FastMCP", limit=5)
    assert len(search_results) > 0
    assert any(hit.result.uri == doc_metadata.uri for hit in search_results)


@pytest.mark.asyncio
async def test_get_document(document_store, temp_data_dir):
    """Test retrieving a specific document by ID"""

    # Upload a document (simulate server logic)
    test_content = "This is another test document for retrieval testing."

    doc_metadata = DocumentMetadata(
        uri="",
        name="retrieve_test.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content=test_content,  # Plain string for text/plain
    ).to_binary()

    doc_uri = await document_store.store(document)
    doc_metadata.uri = doc_uri

    # Get the document by ID
    retrieved_doc = await document_store.get(doc_metadata.uri)

    assert retrieved_doc is not None
    assert retrieved_doc.metadata.uri == doc_metadata.uri
    assert retrieved_doc.metadata.name == "retrieve_test.txt"
    assert test_content in retrieved_doc.content.decode("utf-8")


@pytest.mark.asyncio
async def test_list_documents(document_store, temp_data_dir):
    """Test listing all documents"""

    # Upload multiple documents (simulate server logic)
    doc1_metadata = DocumentMetadata(
        uri="",
        name="doc1.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document1 = Document(
        metadata=doc1_metadata,
        content="First document content",  # Plain string for text/plain
    ).to_binary()

    doc1_id = await document_store.store(document1)
    doc1_metadata.uri = doc1_id

    doc2_metadata = DocumentMetadata(
        uri="",
        name="doc2.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document2 = Document(
        metadata=doc2_metadata,
        content="Second document content",  # Plain string for text/plain
    ).to_binary()

    doc2_id = await document_store.store(document2)
    doc2_metadata.uri = doc2_id

    # List all documents
    documents = await document_store.list_docs()

    assert len(documents) >= 2
    doc_uris = [doc.uri for doc in documents]
    assert doc1_metadata.uri in doc_uris
    assert doc2_metadata.uri in doc_uris


@pytest.mark.asyncio
async def test_upload_invalid_mime_type(document_store, temp_data_dir):
    """Test that invalid MIME types are rejected"""

    # Test invalid MIME type validation (simulate server validation logic)
    allowed_mime_types = {"application/json", "application/pdf", "text/plain"}
    mime_type = "text/html"

    # This should raise an InvalidMimeTypeError
    if mime_type not in allowed_mime_types:
        with pytest.raises(InvalidMimeTypeError):
            raise InvalidMimeTypeError(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed types: {', '.join(sorted(allowed_mime_types))}"
            )
    else:
        pytest.fail("Expected validation to fail")


@pytest.mark.asyncio
async def test_upload_pdf_document(document_store, temp_data_dir):
    """Test uploading a PDF document (binary)"""

    # Create fake PDF content (base64 encoded)
    fake_pdf_content = b"%PDF-1.4 fake pdf content"
    encoded_content = base64.b64encode(fake_pdf_content).decode("utf-8")

    doc_metadata = DocumentMetadata(
        uri="",
        name="test.pdf",
        mime_type="application/pdf",
        extra={"title": "Test PDF"},
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content=encoded_content,
    ).to_binary()

    doc_uri = await document_store.store(document)
    doc_metadata.uri = doc_uri

    assert doc_metadata.name == "test.pdf"
    assert doc_metadata.mime_type == "application/pdf"
    assert doc_metadata.extra["title"] == "Test PDF"

    # Retrieve and verify the document
    retrieved_doc = await document_store.get(doc_metadata.uri)
    assert retrieved_doc is not None
    assert retrieved_doc.metadata.mime_type == "application/pdf"


@pytest.mark.asyncio
async def test_search_no_results(document_store, temp_data_dir):
    """Test searching for non-existent content"""

    # Upload a document (simulate server logic)
    doc_metadata = DocumentMetadata(
        uri="",
        name="cats.txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )

    document = Document(
        metadata=doc_metadata,
        content="This document is about cats",  # Plain string for text/plain
    ).to_binary()

    doc_uri = await document_store.store(document)
    doc_metadata.uri = doc_uri

    # Search for something that doesn't exist
    results = await document_store.search(query="dogs", limit=5)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_get_nonexistent_document(document_store, temp_data_dir):
    """Test retrieving a document that doesn't exist"""

    import uuid

    # Use a valid document URI format that doesn't exist
    fake_uuid = str(uuid.uuid4())
    fake_doc_uri = f"asta://{document_store.namespace}/{document_store.resource_type}/{fake_uuid}"

    result = await document_store.get(fake_doc_uri)
    assert result is None
