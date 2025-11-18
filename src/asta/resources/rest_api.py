"""REST API endpoints for Asta Resource Repository"""

import base64
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from .document_store import PostgresDocumentStore
from .model import DocumentMetadata, Document, SearchHit, construct_document_uri
from .exceptions import (
    DocumentNotFoundError,
    InvalidMimeTypeError,
    DocumentTooLargeError,
    ValidationError,
    DocumentServiceError,
)
from .auth import get_user_context_from_header, UserContext


# Request/Response models for REST API
class UploadDocumentRequest(BaseModel):
    content: str = Field(
        ...,
        description="Document content (UTF-8 string for text files, base64 for binary files)",
    )
    filename: str = Field(..., description="Name of the document file")
    mime_type: str = Field(..., description="MIME type of the document")
    extra_metadata: dict[str, Any] | None = Field(
        None, description="Additional metadata"
    )


class UploadDocumentResponse(BaseModel):
    uri: str
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    message: str = "Document uploaded successfully"


class GetDocumentResponse(BaseModel):
    uri: str
    filename: str
    content: str  # base64 encoded
    mime_type: str
    size_bytes: int
    created_at: datetime
    modified_at: datetime | None = None
    extra_metadata: dict[str, Any] | None = None


class ListDocumentsResponse(BaseModel):
    documents: list[DocumentMetadata]
    total: int


class SearchDocumentsRequest(BaseModel):
    query: str = Field(..., description="Search query string")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")


class SearchDocumentsResponse(BaseModel):
    results: list[SearchHit]
    total: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int


def create_rest_router(
    document_store: PostgresDocumentStore,
    max_file_size_bytes: int,
    allowed_mime_types: set[str],
) -> APIRouter:
    """Create REST API router with all endpoints

    Args:
        document_store: Document store instance
        max_file_size_bytes: Maximum file size in bytes
        allowed_mime_types: Set of allowed MIME types

    Returns:
        Configured FastAPI router
    """
    router = APIRouter(prefix="/rest", tags=["documents"])

    def _id_to_uri(namespace: str, resource_type: str, doc_uuid: str) -> str:
        """Convert namespace, resource_type, and uuid to URI

        Args:
            namespace: Namespace identifier
            resource_type: Resource type
            doc_uuid: Document UUID

        Returns:
            Full URI in format asta://{namespace}/{resource_type}/{uuid}
        """
        return construct_document_uri(namespace, resource_type, doc_uuid)

    @router.post(
        "/documents",
        response_model=UploadDocumentResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Upload a document",
        description="Upload a new document with metadata",
    )
    async def upload_document(
        request: UploadDocumentRequest,
        user_context: UserContext = Depends(get_user_context_from_header),
    ) -> UploadDocumentResponse:
        """Upload a new document"""
        try:
            # Validate inputs
            if not request.filename or not request.filename.strip():
                raise ValidationError("Filename cannot be empty")

            if not request.content:
                raise ValidationError("Content cannot be empty")

            # Validate MIME type
            if request.mime_type not in allowed_mime_types:
                raise InvalidMimeTypeError(
                    f"Unsupported MIME type '{request.mime_type}'. "
                    f"Allowed types: {', '.join(sorted(allowed_mime_types))}"
                )

            # Create document metadata first to check if binary
            doc_metadata = DocumentMetadata(
                uri="",
                name=request.filename,
                mime_type=request.mime_type,
                extra=request.extra_metadata or {},
                created_at=datetime.now(),
            )

            # Validate file size based on content type
            try:
                if doc_metadata.is_binary:
                    # Binary files: content is base64, decode to check size
                    content_bytes = base64.b64decode(request.content)
                else:
                    # Text files: content is UTF-8 string, encode to check size
                    content_bytes = request.content.encode("utf-8")

                content_size = len(content_bytes)

                if content_size > max_file_size_bytes:
                    max_mb = max_file_size_bytes / (1024 * 1024)
                    actual_mb = content_size / (1024 * 1024)
                    raise DocumentTooLargeError(
                        f"Document size ({actual_mb:.2f} MB) exceeds "
                        f"maximum allowed size ({max_mb:.0f} MB)"
                    )
            except Exception as e:
                if isinstance(
                    e, (DocumentTooLargeError, InvalidMimeTypeError, ValidationError)
                ):
                    raise
                if doc_metadata.is_binary:
                    raise ValidationError(f"Invalid base64 content: {str(e)}")
                else:
                    raise ValidationError(f"Invalid UTF-8 content: {str(e)}")

            # Create document
            document = Document(
                metadata=doc_metadata,
                content=request.content,
            ).to_binary()

            doc_uri = await document_store.store(document, user_context.user_uri)
            doc_metadata.uri = doc_uri

            return UploadDocumentResponse(
                uri=doc_uri,
                filename=request.filename,
                mime_type=request.mime_type,
                size_bytes=content_size,
                created_at=doc_metadata.created_at,
            )

        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except InvalidMimeTypeError as e:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e)
            )
        except DocumentTooLargeError as e:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e)
            )
        except DocumentServiceError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    @router.get(
        "/documents/{namespace}/{resource_type}/{doc_uuid}",
        response_model=GetDocumentResponse,
        summary="Get a document",
        description="Retrieve a document by its namespace, resource type, and UUID",
    )
    async def get_document(
        namespace: str,
        resource_type: str,
        doc_uuid: str,
        user_context: UserContext = Depends(get_user_context_from_header),
    ) -> GetDocumentResponse:
        """Get a document by namespace, resource_type, and uuid"""
        try:
            # Construct URI from path parameters
            uri = _id_to_uri(namespace, resource_type, doc_uuid)
            document = await document_store.get(uri, user_context.user_uri)

            if document is None:
                raise DocumentNotFoundError(
                    f"Document with ID '{namespace}/{resource_type}/{doc_uuid}' not found"
                )

            serializable = document.to_serializable()

            return GetDocumentResponse(
                uri=serializable.metadata.uri,
                filename=serializable.metadata.name,
                content=serializable.content,
                mime_type=serializable.metadata.mime_type,
                size_bytes=serializable.metadata.size,
                created_at=serializable.metadata.created_at,
                modified_at=serializable.metadata.modified_at,
                extra_metadata=serializable.metadata.extra,
            )

        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except DocumentNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except DocumentServiceError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    @router.get(
        "/documents",
        response_model=ListDocumentsResponse,
        summary="List all documents",
        description="Get a list of all documents with metadata",
    )
    async def list_documents(
        user_context: UserContext = Depends(get_user_context_from_header),
    ) -> ListDocumentsResponse:
        """List all documents"""
        try:
            documents = await document_store.list_docs(user_context.user_uri)
            return ListDocumentsResponse(
                documents=documents,
                total=len(documents),
            )
        except DocumentServiceError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    @router.post(
        "/documents/search",
        response_model=SearchDocumentsResponse,
        summary="Search documents",
        description="Search through documents using full-text search",
    )
    async def search_documents(
        request: SearchDocumentsRequest,
        user_context: UserContext = Depends(get_user_context_from_header),
    ) -> SearchDocumentsResponse:
        """Search documents"""
        try:
            hits = await document_store.search(
                request.query, user_context.user_uri, request.limit
            )
            return SearchDocumentsResponse(
                results=hits,
                total=len(hits),
            )
        except DocumentServiceError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    @router.delete(
        "/documents/{namespace}/{resource_type}/{doc_uuid}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a document",
        description="Delete a document by its namespace, resource type, and UUID",
    )
    async def delete_document(
        namespace: str,
        resource_type: str,
        doc_uuid: str,
        user_context: UserContext = Depends(get_user_context_from_header),
    ) -> None:
        """Delete a document"""
        try:
            # Construct URI from path parameters
            uri = _id_to_uri(namespace, resource_type, doc_uuid)

            # Check if document exists and is owned by user
            document = await document_store.get(uri, user_context.user_uri)
            if document is None:
                raise DocumentNotFoundError(
                    f"Document with ID '{namespace}/{resource_type}/{doc_uuid}' not found"
                )

            await document_store.delete(uri, user_context.user_uri)

        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except DocumentNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except DocumentServiceError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    @router.get(
        "/health",
        summary="Health check",
        description="Check if the service is healthy",
    )
    async def health_check() -> dict[str, str]:
        """Health check endpoint"""
        return {"status": "healthy", "service": "asta-resource-repository"}

    return router
