# MCP Asta Resource Repository - Project Description

## Executive Summary

Build an MCP (Model Context Protocol) server that provides centralized document storage, permission management, and multi-format file parsing. This server will allow multiple MCP clients (Claude Desktop, Claude Code, custom applications) to share access to documents with proper authentication and authorization.

## Core Problem Statement

The current MCP ecosystem lacks a unified solution for:

- Storing and retrieving documents across multiple clients
- Managing permissions for file access
- Parsing various document formats (PDF, DOCX, XLSX, images, etc.)
- Providing a secure, shared workspace for AI agents

## MVP Scope

### Phase 1: Core Infrastructure (Start Here)

- Basic MCP Server with HTTP/SSE transport
- Simple file storage (local filesystem, expandable to PostgreSQL/S3 later)
- Basic authentication (API key or simple OAuth)
- Core CRUD operations for documents

### Phase 2: Enhanced Features

- Multi-format parsing (integrate document processing libraries)
- Advanced permissions (user/group-based access control)
- Resource discovery (list, search, filter documents)

### Phase 3: Production Ready

- OAuth 2.1 integration (Keycloak or Auth0)
- Cloud storage backends (S3, Azure Blob, GCS)
- Audit logging and analytics

## MCP Tools Specification

### Phase 1 Tools

#### 1. `upload_document`
Creates a new document in the system.

**Parameters:**
- `content` (string, required): File content (base64 for binary files)
- `filename` (string, required): Document filename
- `mime_type` (string, required): MIME type (e.g., "application/pdf")
- `extra_metadata` (object, optional): Additional metadata (tags, description, etc.)

**Returns:**
```json
{
  "document_id": "uuid",
  "filename": "document.pdf",
  "created_at": "2025-01-15T10:30:00Z",
  "uri": "document://uuid",
  "size_bytes": 12345
}
```

#### 2. `get_document`
Retrieves a document by ID.

**Parameters:**
- `document_id` (string, required): UUID of document

**Returns:**
```json
{
  "document_id": "uuid",
  "filename": "document.pdf",
  "content": "base64_encoded_content",
  "mime_type": "application/pdf",
  "metadata": {},
  "created_at": "2025-01-15T10:30:00Z",
  "size_bytes": 12345
}
```

#### 3. `list_documents`
Lists available documents with optional filtering.

**Parameters:**
- None (returns all documents)

**Returns:**
```json
{
  "documents": [
    {
      "document_id": "uuid",
      "filename": "document.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 12345,
      "created_at": "2025-01-15T10:30:00Z",
      "metadata": {}
    }
  ]
}
```

#### 4. `search_documents`
Full-text search across documents.

**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Max results (default: 10)

**Returns:**
```json
{
  "results": [
    {
      "document_id": "uuid",
      "filename": "document.pdf",
      "score": 0.95,
      "snippet": "...relevant text snippet..."
    }
  ]
}
```

### Phase 2 Tools

#### 5. `update_document`
Updates an existing document's metadata or content.

**Parameters:**
- `document_id` (string, required)
- `content` (string, optional): New content
- `metadata` (object, optional): Updated metadata

**Returns:**
```json
{
  "document_id": "uuid",
  "modified_at": "2025-01-15T11:00:00Z",
  "message": "Document updated successfully"
}
```

#### 6. `delete_document`
Deletes a document.

**Parameters:**
- `document_id` (string, required)

**Returns:**
```json
{
  "message": "Document deleted successfully",
  "deleted_at": "2025-01-15T12:00:00Z"
}
```

#### 7. `parse_document`
Extracts text/data from various file formats.

**Parameters:**
- `document_id` (string, required)
- `output_format` (string, optional): "text", "markdown", "json" (default: "text")
- `options` (object, optional): Parser-specific options
  - `extract_images`: For PDFs/DOCX
  - `extract_tables`: For PDFs/DOCX/XLSX
  - `ocr`: Enable OCR for images

**Returns:**
```json
{
  "document_id": "uuid",
  "parsed_content": "extracted text or structured data",
  "format": "markdown",
  "metadata": {
    "page_count": 5,
    "word_count": 1234,
    "images_found": 3,
    "tables_found": 2
  }
}
```

### Phase 3 Tools

#### 8. `share_document`
Generate shareable link or grant access to another user.

**Parameters:**
- `document_id` (string, required)
- `share_with` (string, optional): User/group identifier
- `permissions` (array, required): ["read", "write", "delete"]
- `expires_at` (string, optional): Expiration timestamp

#### 9. `get_document_versions`
List version history of a document.

**Parameters:**
- `document_id` (string, required)

## MCP Resources Specification

Resources expose documents as URIs that can be read by MCP clients.

## Authentication & Authorization

### Phase 1: API Key Authentication

**Implementation:**
- Generate API keys for each client/user
- Store hashed keys in database
- Validate via HTTP Authorization header: `Authorization: Bearer <api_key>`

**Database Schema:**
```sql
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    permissions TEXT -- JSON array
);
```

### Phase 2: Permission Model

**Permission Levels:**
- `read`: Can read documents
- `write`: Can create/update documents
- `delete`: Can delete documents
- `admin`: Full access + user management

**Access Control Example:**
```json
{
  "document_id": "uuid",
  "owner": "user_123",
  "shared_with": {
    "user_456": ["read"],
    "group_editors": ["read", "write"]
  },
  "public": false
}
```

### Phase 3: OAuth 2.1 Integration

- Authorization Code flow with PKCE
- JWT access tokens
- Refresh token support
- Integration with Keycloak or Auth0

## Data Models

### Document Model
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List

@dataclass
class Document:
    id: str  # UUID
    filename: str
    mime_type: str
    storage_path: str  # Where file is stored
    size_bytes: int
    owner_id: str
    created_at: datetime
    modified_at: datetime
    metadata: Dict  # User-defined metadata
    permissions: Dict  # Access control
    tags: List[str]
    version: int
    parent_version: Optional[str]  # For versioning
```

### User Model (Phase 2)
```python
@dataclass
class User:
    id: str
    email: str
    name: str
    api_keys: List[str]
    groups: List[str]
    created_at: datetime
```

## Document Parsers

### Parser Interface
```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class DocumentParser(ABC):
    @abstractmethod
    def can_parse(self, mime_type: str) -> bool:
        """Check if parser supports this MIME type"""
        pass

    @abstractmethod
    def parse(self, content: bytes, options: Dict = None) -> Dict[str, Any]:
        """Parse document and return structured data"""
        pass
```

### Implementations

#### PDF Parser
```python
class PDFParser(DocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        return mime_type == "application/pdf"

    def parse(self, content: bytes, options: Dict = None) -> Dict:
        # Use pdfplumber or PyPDF2
        return {
            "text": extracted_text,
            "pages": page_count,
            "images": extracted_images,
            "tables": extracted_tables
        }
```

#### DOCX Parser
```python
class DOCXParser(DocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        return mime_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]

    def parse(self, content: bytes, options: Dict = None) -> Dict:
        # Use python-docx
        pass
```

## Security Considerations

- **Input Validation:** Validate all file uploads, content types, sizes
- **File Type Verification:** Use magic bytes, not just extensions
- **Path Traversal Prevention:** Sanitize all file paths
- **Rate Limiting:** Prevent abuse of API
- **Encryption:** Encrypt sensitive data at rest (Phase 3)
- **Audit Logging:** Log all access and modifications
- **Sandboxing:** Run document parsers in isolated environments

## Next Steps

Once MVP is built:
1. Gather user feedback
2. Add requested file formats
3. Implement advanced search with filters
4. Build web UI for management
5. Create client libraries (JavaScript, Python)
6. Consider commercial features (teams, advanced analytics)

## Technical Notes for Implementation
- Use UUID4 for document IDs
- Store files with hash-based names to prevent collisions
- Implement file chunking for large uploads
- Use SQLAlchemy ORM for database portability
- Implement proper logging with Python's logging module
- Use environment variables for sensitive config (API keys, DB passwords)
- Use sentence-transformers for generating document embeddings
- Store embeddings in PostgreSQL with pgvector extension
