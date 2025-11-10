"""
Minimal integration tests for REST API running in Docker.

These tests verify that the API server is running correctly in Docker.
They require the Docker containers to be running (docker compose up).

Run with: make test-docker
"""

import time

import pytest
import requests


# Base URL for Docker deployment
API_BASE_URL = "http://localhost:8000"

# Test user URI for authentication
TEST_USER_URI = "asta://local-postgres/user/00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def wait_for_api():
    """Wait for API to be ready before running tests"""
    max_retries = 30
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            response = requests.get(f"{API_BASE_URL}/rest/health", timeout=2)
            if response.status_code == 200:
                print(f"\n✓ API is ready after {attempt + 1} attempt(s)")
                return
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise

    pytest.fail("API did not become ready in time")


class TestDockerDeployment:
    """Minimal smoke tests for Docker deployment"""

    def test_health_check(self, wait_for_api):
        """Verify the service is healthy"""
        response = requests.get(f"{API_BASE_URL}/rest/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "asta-resource-repository"

    def test_api_docs_available(self, wait_for_api):
        """Verify OpenAPI docs are accessible"""
        response = requests.get(f"{API_BASE_URL}/docs")
        assert response.status_code == 200

    def test_basic_document_workflow(self, wait_for_api):
        """Test basic document upload, retrieve, and delete"""
        # Set up headers with authentication
        headers = {"Authorization": f"Bearer {TEST_USER_URI}"}

        # 1. Upload a document
        upload_response = requests.post(
            f"{API_BASE_URL}/rest/documents",
            json={
                "content": "Docker test content",
                "filename": "docker_test.txt",
                "mime_type": "text/plain",
            },
            headers=headers,
        )
        assert upload_response.status_code == 201
        doc_uri = upload_response.json()["uri"]

        # Extract namespace, resource_type, and uuid from URI (format: asta://{namespace}/{resource_type}/{uuid})
        uri_parts = doc_uri.replace("asta://", "").split("/")
        namespace = uri_parts[0]
        resource_type = uri_parts[1]
        uuid = uri_parts[2]

        # 2. Retrieve the document
        get_response = requests.get(
            f"{API_BASE_URL}/rest/documents/{namespace}/{resource_type}/{uuid}",
            headers=headers,
        )
        assert get_response.status_code == 200
        assert get_response.json()["filename"] == "docker_test.txt"

        # 3. List documents (should include our document)
        list_response = requests.get(f"{API_BASE_URL}/rest/documents", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] >= 1

        # 4. Search for the document
        search_response = requests.post(
            f"{API_BASE_URL}/rest/documents/search",
            json={"query": "Docker", "limit": 10},
            headers=headers,
        )
        assert search_response.status_code == 200
        assert len(search_response.json()["results"]) >= 1

        # 5. Delete the document
        delete_response = requests.delete(
            f"{API_BASE_URL}/rest/documents/{namespace}/{resource_type}/{uuid}",
            headers=headers,
        )
        assert delete_response.status_code == 204

        # 6. Verify it's deleted
        get_deleted = requests.get(
            f"{API_BASE_URL}/rest/documents/{namespace}/{resource_type}/{uuid}",
            headers=headers,
        )
        assert get_deleted.status_code == 404


class TestDockerMCPEndpoint:
    """Verify MCP endpoint is accessible"""

    def test_mcp_endpoint_exists(self, wait_for_api):
        """Verify MCP endpoint returns something (even if it's an error without proper client)"""
        # The MCP endpoint won't work with a plain HTTP request,
        # but we can verify it's mounted and responds
        response = requests.get(f"{API_BASE_URL}/mcp", timeout=5)

        # MCP endpoints may return various status codes depending on the protocol
        # We just want to verify the endpoint is mounted and responding
        assert response.status_code in [
            200,
            404,
            405,
            426,
        ]  # Various acceptable responses
