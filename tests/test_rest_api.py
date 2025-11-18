"""Integration tests for REST API endpoints"""

import base64

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from asta.resources.config import load_config
from asta.resources.model import parse_document_uri
from asta.resources.rest_api import create_rest_router

# Test user URI for authentication
TEST_USER_UUID = "00000000-0000-0000-0000-000000000001"
TEST_USER_URI = f"asta://local-postgres/user/{TEST_USER_UUID}"


@pytest.fixture
def auth_headers():
    """Fixture to provide authorization headers for REST API requests"""
    return {"Authorization": TEST_USER_URI}


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
async def client(document_store):
    """Create an async test client with REST API router"""
    from fastapi import FastAPI

    app = FastAPI()
    max_file_size_bytes = 100 * 1024 * 1024  # 100 MB
    allowed_mime_types = {"application/json", "application/pdf", "text/plain"}

    router = create_rest_router(
        document_store=document_store,
        max_file_size_bytes=max_file_size_bytes,
        allowed_mime_types=allowed_mime_types,
    )
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestRestAPIUpload:
    """Tests for the upload document endpoint"""

    @pytest.mark.asyncio
    async def test_upload_text_document(self, client, auth_headers):
        """Test uploading a plain text document"""
        # For text files, send plain UTF-8 string (not base64)
        content = "Hello, World!"

        response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "hello.txt",
                "mime_type": "text/plain",
                "extra_metadata": {"description": "Test document"},
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "uri" in data
        assert data["filename"] == "hello.txt"
        assert data["mime_type"] == "text/plain"
        assert data["size_bytes"] == 13
        assert data["message"] == "Document uploaded successfully"

    @pytest.mark.asyncio
    async def test_upload_json_document(self, client, auth_headers):
        """Test uploading a JSON document"""
        # For JSON files, send plain UTF-8 string (not base64)
        content = '{"key": "value", "number": 42}'

        response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "data.json",
                "mime_type": "application/json",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "data.json"
        assert data["mime_type"] == "application/json"

    @pytest.mark.asyncio
    async def test_upload_pdf_document(self, client, auth_headers):
        """Test uploading a PDF document"""
        # Minimal PDF content
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF"
        content = base64.b64encode(pdf_content).decode()

        response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "document.pdf",
                "mime_type": "application/pdf",
                "extra_metadata": {"tags": ["test", "pdf"]},
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "document.pdf"
        assert data["mime_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_upload_invalid_mime_type(self, client, auth_headers):
        """Test uploading with unsupported MIME type"""
        content = "test"

        response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "test.exe",
                "mime_type": "application/x-msdownload",
            },
            headers=auth_headers,
        )

        assert response.status_code == 415  # Unsupported Media Type
        assert "Unsupported MIME type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_empty_filename(self, client, auth_headers):
        """Test uploading with empty filename"""
        content = "test"

        response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Filename cannot be empty" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_empty_content(self, client, auth_headers):
        """Test uploading with empty content"""
        response = await client.post(
            "/rest/documents",
            json={
                "content": "",
                "filename": "test.txt",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Content cannot be empty" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_invalid_base64(self, client, auth_headers):
        """Test uploading with invalid base64 content for PDF"""
        response = await client.post(
            "/rest/documents",
            json={
                "content": "not-valid-base64!!!",
                "filename": "test.pdf",
                "mime_type": "application/pdf",  # Binary type requires base64
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid base64 content" in response.json()["detail"]


class TestRestAPIGetDocument:
    """Tests for the get document endpoint"""

    @pytest.mark.asyncio
    async def test_get_existing_document(self, client, auth_headers):
        """Test retrieving an existing document"""
        # First upload a document (text file - plain string)
        content = "Test content"
        upload_response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "test.txt",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )
        doc_uri = upload_response.json()["uri"]
        namespace, resource_type, uuid = parse_document_uri(doc_uri)

        # Then retrieve it
        response = await client.get(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["uri"] == doc_uri
        assert data["filename"] == "test.txt"
        assert data["mime_type"] == "text/plain"
        assert data["content"] == content  # Should get back plain text
        assert data["size_bytes"] == 12

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self, client, document_store, auth_headers):
        """Test retrieving a document that doesn't exist"""
        import uuid

        fake_uuid = str(uuid.uuid4())
        namespace = document_store.namespace
        resource_type = document_store.resource_type
        response = await client.get(
            f"/rest/documents/{namespace}/{resource_type}/{fake_uuid}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestRestAPIListDocuments:
    """Tests for the list documents endpoint"""

    @pytest.mark.asyncio
    async def test_list_empty_documents(self, client, auth_headers):
        """Test listing when no documents exist"""
        response = await client.get("/rest/documents", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["documents"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_multiple_documents(self, client, auth_headers):
        """Test listing multiple documents"""
        # Upload multiple documents
        for i in range(3):
            content = f"Document {i}"  # Plain text for text/plain
            await client.post(
                "/rest/documents",
                json={
                    "content": content,
                    "filename": f"doc{i}.txt",
                    "mime_type": "text/plain",
                },
                headers=auth_headers,
            )

        # List all documents
        response = await client.get("/rest/documents", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["documents"]) == 3

        # Check that documents are in the list
        filenames = [doc["name"] for doc in data["documents"]]
        assert "doc0.txt" in filenames
        assert "doc1.txt" in filenames
        assert "doc2.txt" in filenames


class TestRestAPISearchDocuments:
    """Tests for the search documents endpoint"""

    @pytest.mark.asyncio
    async def test_search_with_results(self, client, auth_headers):
        """Test searching with results found"""
        # Upload documents with searchable content
        content1 = "Python programming language"
        content2 = "JavaScript programming language"

        await client.post(
            "/rest/documents",
            json={
                "content": content1,
                "filename": "python.txt",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )
        await client.post(
            "/rest/documents",
            json={
                "content": content2,
                "filename": "javascript.txt",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )

        # Search for "Python"
        response = await client.post(
            "/rest/documents/search",
            json={"query": "Python", "limit": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["results"]) >= 1

    @pytest.mark.asyncio
    async def test_search_no_results(self, client, auth_headers):
        """Test searching with no results"""
        # Upload a document
        content = "Some content"
        await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "test.txt",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )

        # Search for something that doesn't exist
        response = await client.post(
            "/rest/documents/search",
            json={"query": "nonexistent-term-xyz", "limit": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_search_with_limit(self, client, auth_headers):
        """Test search with result limit"""
        # Upload multiple documents
        for i in range(5):
            content = f"test document {i}"
            await client.post(
                "/rest/documents",
                json={
                    "content": content,
                    "filename": f"test{i}.txt",
                    "mime_type": "text/plain",
                },
                headers=auth_headers,
            )

        # Search with limit of 2
        response = await client.post(
            "/rest/documents/search",
            json={"query": "test", "limit": 2},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 2


class TestRestAPIDeleteDocument:
    """Tests for the delete document endpoint"""

    @pytest.mark.asyncio
    async def test_delete_existing_document(self, client, auth_headers):
        """Test deleting an existing document"""
        # First upload a document
        content = "To be deleted"
        upload_response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "delete_me.txt",
                "mime_type": "text/plain",
            },
            headers=auth_headers,
        )
        doc_uri = upload_response.json()["uri"]
        namespace, resource_type, uuid = parse_document_uri(doc_uri)

        # Delete the document
        response = await client.delete(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document(
        self, client, document_store, auth_headers
    ):
        """Test deleting a document that doesn't exist"""
        import uuid

        fake_uuid = str(uuid.uuid4())
        namespace = document_store.namespace
        resource_type = document_store.resource_type
        response = await client.delete(
            f"/rest/documents/{namespace}/{resource_type}/{fake_uuid}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestRestAPIHealthCheck:
    """Tests for the health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self, client, auth_headers):
        """Test health check endpoint"""
        response = await client.get("/rest/health", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "asta-resource-repository"


class TestRestAPIEndToEnd:
    """End-to-end workflow tests"""

    @pytest.mark.asyncio
    async def test_complete_document_lifecycle(self, client, auth_headers):
        """Test complete document lifecycle: upload, retrieve, search, delete"""
        # 1. Upload a document
        content = "Full lifecycle test content"
        upload_response = await client.post(
            "/rest/documents",
            json={
                "content": content,
                "filename": "lifecycle.txt",
                "mime_type": "text/plain",
                "extra_metadata": {"purpose": "testing"},
            },
            headers=auth_headers,
        )
        assert upload_response.status_code == 201
        doc_uri = upload_response.json()["uri"]
        namespace, resource_type, uuid = parse_document_uri(doc_uri)

        # 2. Retrieve the document
        get_response = await client.get(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )
        assert get_response.status_code == 200
        assert get_response.json()["filename"] == "lifecycle.txt"

        # 3. List documents and verify it's there
        list_response = await client.get("/rest/documents", headers=auth_headers)
        assert list_response.status_code == 200
        filenames = [doc["name"] for doc in list_response.json()["documents"]]
        assert "lifecycle.txt" in filenames

        # 4. Search for the document
        search_response = await client.post(
            "/rest/documents/search",
            json={"query": "lifecycle", "limit": 10},
            headers=auth_headers,
        )
        assert search_response.status_code == 200
        assert len(search_response.json()["results"]) >= 1

        # 5. Delete the document
        delete_response = await client.delete(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )
        assert delete_response.status_code == 204

        # 6. Verify it's gone
        get_deleted_response = await client.get(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )
        assert get_deleted_response.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_documents_workflow(self, client, auth_headers):
        """Test working with multiple documents"""
        doc_uris = []

        # Upload multiple documents
        for i in range(3):
            content = f"Document {i} content"
            response = await client.post(
                "/rest/documents",
                json={
                    "content": content,
                    "filename": f"multi{i}.txt",
                    "mime_type": "text/plain",
                },
                headers=auth_headers,
            )
            assert response.status_code == 201
            doc_uris.append(response.json()["uri"])

        # List all documents
        list_response = await client.get("/rest/documents", headers=auth_headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 3

        # Search across all documents
        search_response = await client.post(
            "/rest/documents/search",
            json={"query": "Document", "limit": 10},
            headers=auth_headers,
        )
        assert search_response.status_code == 200
        assert len(search_response.json()["results"]) >= 3

        # Delete one document
        namespace, resource_type, uuid = parse_document_uri(doc_uris[1])
        await client.delete(
            f"/rest/documents/{namespace}/{resource_type}/{uuid}", headers=auth_headers
        )

        # Verify count is now 2
        list_response = await client.get("/rest/documents", headers=auth_headers)
        assert list_response.json()["total"] == 2
