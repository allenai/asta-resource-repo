"""Tests for the fetch command with file:// URLs."""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from asta.resources.document_store.local_index import LocalIndexDocumentStore
from asta.resources.model import DocumentMetadata


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


@pytest.fixture
def temp_file():
    """Create a temporary file for testing file:// URLs."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("This is test content.\nLine 2.\nLine 3.\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_file_protocol_url_validation(store, temp_file):
    """Test that file:// URLs are accepted by validation."""
    doc = DocumentMetadata(
        uri="",
        name="Test File Protocol Document",
        url=f"file://{temp_file}",
        summary="Test document with file:// protocol",
        mime_type="text/plain",
        tags=["test"],
    )

    # Should not raise ValidationError
    uri = await store.store(doc)
    assert uri.startswith("asta://")

    # Verify stored correctly
    retrieved = await store.get(uri)
    assert retrieved is not None
    assert retrieved.url == f"file://{temp_file}"
    assert retrieved.mime_type == "text/plain"


@pytest.mark.asyncio
async def test_supported_url_protocols(store):
    """Test that only supported URL protocols are accepted."""
    supported_protocols = [
        "http://example.com/doc.pdf",
        "https://example.com/doc.pdf",
        "file:///path/to/document.pdf",
    ]

    for i, url in enumerate(supported_protocols):
        protocol = url.split("://")[0]
        doc = DocumentMetadata(
            uri="",
            name=f"Test Document {i}",
            url=url,
            summary=f"Test document with {protocol} protocol",
            mime_type="application/pdf",
        )

        # Should not raise ValidationError
        uri = await store.store(doc)
        assert uri.startswith("asta://")

        # Verify it was stored correctly
        retrieved = await store.get(uri)
        assert retrieved is not None
        assert retrieved.url == url


@pytest.mark.asyncio
async def test_file_protocol_with_spaces_in_path(store):
    """Test that file:// URLs with spaces in path are handled correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create file with spaces in path
        test_dir = Path(temp_dir) / "test folder with spaces"
        test_dir.mkdir()
        test_file = test_dir / "test document.txt"
        test_file.write_text("Content with spaces in path")

        doc = DocumentMetadata(
            uri="",
            name="Test File with Spaces",
            url=f"file://{test_file}",
            summary="Test document with spaces in file path",
            mime_type="text/plain",
        )

        uri = await store.store(doc)
        assert uri.startswith("asta://")

        retrieved = await store.get(uri)
        assert retrieved is not None
        assert retrieved.url == f"file://{test_file}"


@pytest.mark.asyncio
async def test_multiple_file_protocol_documents(store, temp_file):
    """Test storing and retrieving multiple file:// protocol documents."""
    # Create additional temp files
    temp_files = [temp_file]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Second test file content")
        temp_files.append(f.name)

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Third test file content")
        temp_files.append(f.name)

    try:
        uris = []
        for i, file_path in enumerate(temp_files):
            doc = DocumentMetadata(
                uri="",
                name=f"Test File {i+1}",
                url=f"file://{file_path}",
                summary=f"Test file number {i+1}",
                mime_type="text/plain",
            )
            uri = await store.store(doc)
            uris.append(uri)

        # Verify all documents are stored
        assert len(uris) == 3
        all_docs = await store.list_docs()
        file_docs = [d for d in all_docs if d.url.startswith("file://")]
        assert len(file_docs) == 3

        # Verify each can be retrieved
        for uri in uris:
            retrieved = await store.get(uri)
            assert retrieved is not None
            assert retrieved.url.startswith("file://")

    finally:
        # Cleanup temp files
        for file_path in temp_files[1:]:  # Skip first one (handled by fixture)
            Path(file_path).unlink(missing_ok=True)
