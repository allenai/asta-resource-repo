# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Asta Resource Repository is an MCP (Model Context Protocol) server that provides centralized document storage with PostgreSQL backend. It exposes both MCP tools (for Claude Desktop/Code) and REST API endpoints for document management operations.

**Key Concept**: Documents are identified by URIs in the format `asta://{namespace}/{resource_type}/{uuid}`, where `namespace` is the namespace identifier (e.g., "local-postgres"), `resource_type` is the resource type (e.g., "document" for uploaded documents, "user" for users), and `uuid` is the resource's unique identifier.

## Architecture

### Dual Server Model

The application has two distinct server modes:

1. **Unified Server** (`server.py`): Runs both MCP (via HTTP/SSE) and REST API endpoints together
   - MCP endpoints mounted at `/mcp`
   - REST API endpoints at `/rest`
   - API documentation at `/docs`
   - Entry point: `asta-resources-server` command

2. **MCP-only Server** (`mcp_server.py`): Dedicated MCP server using stdio transport
   - For use with Claude Desktop/Code via stdio
   - Entry point: `asta-resources-mcp` command

### Core Components

- **`mcp_tools.py`**: Defines MCP tools (`upload_document`, `get_document`, `list_documents`, `search_documents`)
- **`rest_api.py`**: REST API router with FastAPI endpoints
- **`document_store/postgres.py`**: PostgreSQL backend for document storage
- **`model.py`**: Data models for documents (DocumentMetadata, Document, BinaryDocument, SearchHit)
- **`config/`**: HOCON-based configuration system with environment variable overrides
- **`cli/chatbot.py`**: Interactive chatbot CLI using MCP client

### Configuration System

Configuration uses HOCON format (Human-Optimized Config Object Notation) with environment variable substitution:

- Default config: `src/asta/resources/config/local.conf`
- Environment-specific config loaded via `ENV` environment variable
- Key configurations:
  - `server.host`, `server.port`: Server binding
  - `storage.postgres.namespace`: Namespace identifier for URIs
  - `storage.postgres.resource_type`: Resource type for documents (default: "document")
  - `storage.postgres.url`: PostgreSQL connection string
  - `limits.max_file_size_mb`: Document size limit

Environment variables override config values:
- `NAMESPACE`: Override namespace identifier
- `RESOURCE_TYPE`: Override resource type
- `POSTGRES_URL`: Override database connection
- `POSTGRES_HOST`, `POSTGRES_PORT`: Individual connection parameters
- `SERVER_PORT`: Override server port
- `MAX_FILE_SIZE_MB`: Override file size limit

## Project Workflow

### Task Tracking with Beads

The project uses [Beads](https://github.com/steveyegge/beads), a distributed issue tracker designed for AI coding agents. Tasks are stored in `.beads/` and version-controlled via Git.

**Quick reference:**
```bash
# View ready work (unblocked tasks)
bd ready

# List all open issues
bd list

# Show task details
bd show <issue-id>

# Update task status
bd update <issue-id> --status in_progress
bd close <issue-id> --reason "Completed"

# Create new task
bd create "Task title" -d "Description" -p 1 -t feature
```

**Project Structure:**
- **Phase 1: Core Infrastructure** (`asta-resource-repo-khu`) - P0 - Mostly complete
- **Phase 2: Enhanced Features** (`asta-resource-repo-tz8`) - P1 - Not started
- **Phase 3: Production Ready** (`asta-resource-repo-0ff`) - P2 - Not started

See `BEADS.md` for detailed Beads usage guide and workflows.

**Legacy files:** `instructions/Progress.md` and `instructions/Roadmap.md` have been migrated to Beads. They are kept for reference but no longer actively maintained.

## Development Commands

### Code Quality

```bash
# Check code formatting and linting
make code-check

# Format the code
make code-format
```

### Running Tests

**Important**: Always use `uv run` to execute Python commands. Tests require specific environment variables for database access.

```bash
# Run all tests (skips PostgreSQL tests if DB not configured)
make test

# Run tests with PostgreSQL (requires database)
POSTGRES_URL=postgresql://asta_resources:asta_resources@localhost:15432/asta_resources uv run pytest tests/ -v

# Run single test file
uv run pytest tests/test_rest_api.py -v

# Run specific test
uv run pytest tests/test_rest_api.py::TestRestAPIUpload::test_upload_text_document -v
```

### Docker Development Workflow

```bash
# Start PostgreSQL database
make docker-start-db

# Check if PostgreSQL is ready
make docker-check-db

# Start API server (builds and runs in Docker)
make docker-start-api

# Start both database and API
make docker-start

# View logs
make docker-logs          # All services
make docker-logs-db       # PostgreSQL only
make docker-logs-api      # API only

# Stop all services
make docker-stop

# Restart all services
make docker-restart
```

**Database Connection**: PostgreSQL runs on port `15432` (not default 5432) to avoid conflicts.

### Running Servers Locally

```bash
# Unified server (MCP + REST)
uv run asta-resources-server

# MCP-only server (stdio mode)
uv run asta-resources-mcp

# With custom port
uv run asta-resources-server --port 8001

# Development mode (auto-reload)
uv run asta-resources-server --reload
```

### Database Setup

PostgreSQL database setup is automatic via `migrations/001_initial_schema.sql` which runs on container startup. The schema includes:
- `documents` table: Stores document metadata and content as bytea
- Full-text search using `to_tsvector` on content
- Indexes on URI and search vectors

Modify the `migrations/001_initial_schema.sql` file in place for schema changes, instead of adding new .sql files.

## Testing Strategy

### Test Organization

- `test_rest_api.py`: REST API endpoint tests
- `test_server_integration.py`: MCP server integration tests
- `test_postgres_integration.py`: PostgreSQL backend tests (requires DB)
- `test_docker_integration.py`: Docker deployment tests

### PostgreSQL Test Requirements

PostgreSQL tests are automatically skipped if `POSTGRES_URL` is not set. To run them:

```bash
# Start test database
make docker-start-db

# Run PostgreSQL tests only
POSTGRES_URL=postgresql://asta_resources:asta_resources@localhost:15432/asta_resources uv run pytest tests/test_postgres_integration.py -v
```

Tests automatically:
- Initialize database connection pool
- Clean up test data after each test
- Close connections properly in teardown

## Document Handling

### MIME Types

Currently supported MIME types (defined in `server.py` and `mcp_server.py`):
- `application/json`
- `application/pdf`
- `text/plain`

Add new MIME types to `ALLOWED_MIME_TYPES` set in both server files.

### Binary vs Text Documents

Documents are classified based on MIME type:
- **Text**: `text/*`, `application/json` - stored as UTF-8 strings
- **Binary**: All others (e.g., `application/pdf`) - stored as base64 encoded strings

The `DocumentMetadata.is_binary` property determines encoding/decoding logic.

### Document Content Flow

1. **Upload**: Content arrives as string (UTF-8 or base64) → validated → converted to `BinaryDocument` → stored in PostgreSQL as bytea
2. **Retrieval**: Bytea from PostgreSQL → converted to `BinaryDocument` → serialized to `Document` → content returned as string
3. **Search**: PostgreSQL full-text search on document content using `to_tsvector` and `ts_rank`

## MCP Integration

### Connecting from Claude Desktop

Add to Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/user-doc-service",
        "asta-resources-mcp"
      ]
    }
  }
}
```

### Available MCP Tools

1. **`upload_document`**: Upload new document
   - Validates MIME type and file size
   - Returns document URI for reference

2. **`get_document`**: Retrieve document by URI
   - Returns full document with metadata and content

3. **`list_documents`**: List all documents
   - Returns metadata only (no content)

4. **`search_documents`**: Full-text search
   - Uses PostgreSQL `to_tsvector` for search
   - Returns ranked results with snippets

## Common Development Patterns

### Adding a New MCP Tool

1. Add tool function to `mcp_tools.py` using `@mcp.tool()` decorator
2. Add corresponding database method to `document_store/postgres.py`
3. If exposing via REST, add endpoint to `rest_api.py`
4. Write integration test in `tests/test_postgres_integration.py`

### Adding a New Document Field

1. Update `DocumentMetadata` model in `model.py`
2. Create database migration in `migrations/`
3. Update `store()` and `get()` methods in `postgres.py`
4. Update tests to verify new field

### Error Handling

Custom exceptions defined in `exceptions.py`:
- `ValidationError`: Input validation failures
- `DocumentNotFoundError`: Document doesn't exist
- `InvalidMimeTypeError`: Unsupported MIME type
- `DocumentTooLargeError`: Exceeds size limit
- `DocumentServiceError`: Base exception for service errors

MCP tools raise exceptions directly; REST API converts them to HTTP status codes.

## Database Schema

```sql
CREATE TABLE documents (
    id TEXT PRIMARY KEY,           -- UUID part of URI
    uri TEXT UNIQUE NOT NULL,      -- Full asta:// URI
    name TEXT NOT NULL,            -- Filename
    mime_type TEXT NOT NULL,
    content BYTEA NOT NULL,        -- Binary content
    size_bytes BIGINT NOT NULL,
    extra JSONB,                   -- Extra metadata as JSON
    created_at TIMESTAMP NOT NULL,
    modified_at TIMESTAMP,
    search_vector TSVECTOR         -- For full-text search
);
```

Search uses PostgreSQL full-text search with `ts_rank` for relevance scoring.

## Important Notes

- **Always use `uv run`**: This project uses `uv` for dependency management
- **Port 15432**: PostgreSQL runs on non-standard port to avoid conflicts
- **URI Format**: All document URIs must follow `asta://{namespace}/{resource_type}/{uuid}` format
- **Environment Variable Config**: Most settings can be overridden via environment variables
- **Async/Await**: All database operations are async using `asyncpg`
- **Connection Pooling**: PostgreSQL uses connection pool managed by FastMCP lifespan
- **Binary Encoding**: Binary content is stored as bytea in PostgreSQL but transmitted as base64 in API

## Deployment

### Docker Deployment

The service is containerized with:
- Multi-stage build using Python 3.13
- `uv` for fast dependency installation
- Health checks for PostgreSQL
- Network isolation via `asta-resource-repository-network`

### Environment Variables for Production

```bash
POSTGRES_URL=postgresql://user:pass@host:port/database
POSTGRES_HOST=production-db-host
POSTGRES_PORT=5432
SERVER_PORT=8000
MAX_FILE_SIZE_MB=100
ENV=production  # Loads production.conf
```

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check if PostgreSQL is running
make docker-check-db

# View database logs
make docker-logs-db

# Connect to database directly
docker exec -it asta-resource-repository-db psql -U asta_resources -d asta_resources

# Restart database
docker compose restart postgres
```

### Test Failures

- **"Postgres not configured"**: Set `POSTGRES_URL` environment variable
- **Connection refused**: Ensure database is running (`make docker-start-db`)
- **Port already in use**: Check if another instance is running on port 15432 or 8000

### Import Errors

If you see import errors, ensure you're in a valid uv environment:

```bash
# Verify uv installation
uv --version

# Reinstall dependencies
uv sync
```
