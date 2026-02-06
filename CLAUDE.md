# CLAUDE.md - Developer Guide

**Audience**: This file is for **agent-developers** working on the asta-resource-repo codebase itself.

**For agent-users** (using this tool for document management): See [README.md](README.md) and [MCP_SETUP.md](MCP_SETUP.md) instead.

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Asta Resource Repository is a lightweight, git-friendly document metadata index that requires zero external dependencies. It provides MCP (Model Context Protocol) tools and a CLI for managing document metadata locally.

**Key Concept**: Instead of storing document content, this tool maintains an index of metadata (URLs, summaries, tags) in a local YAML file. Documents are identified by URIs in the format `asta://{namespace}/{uuid}`.

## Architecture

### Local-Only Design

**No Databases, No Servers, No Docker**
- Single YAML file (`.asta/index.yaml`) stores all metadata
- No PostgreSQL, no REST API, no external services
- Git-friendly: diffs show exactly what changed
- Portable: copy `.asta/` folder to any project

### Core Components

1. **`document_store/local_index.py`**: YAML-based storage backend
   - File locking for thread safety
   - Atomic writes
   - In-memory search across metadata fields

2. **`mcp_tools.py`**: MCP tool definitions
   - `add_document`: Add document metadata to index
   - `get_document`: Retrieve metadata by URI
   - `list_documents`: List all documents
   - `search_documents`: Search across name, summary, tags, extra fields

3. **`mcp_server.py`**: Stdio transport MCP server
   - Entry point for Claude Desktop/Code integration
   - Single-user model (no authentication)

4. **`cli/index_cli.py`**: Command-line interface
   - `asta-index` commands for manual management
   - Human-friendly output with `--json` option

5. **`model.py`**: Data models
   - `DocumentMetadata`: Metadata-only model (no content field)
   - Fields: `uri`, `name`, `url`, `summary`, `tags`, `mime_type`, `created_at`, `modified_at`, `extra`

6. **`config/`**: HOCON-based configuration
   - Default: `.asta/index.yaml`
   - Environment variable overrides

## Document Model

### DocumentMetadata Fields

**Required fields:**
- `url`: Where the actual document content lives (HTTP/HTTPS URL)
- `name`: Document title/name
- `summary`: Text description for search (required for all documents)
- `mime_type`: Document MIME type (e.g., `application/pdf`, `text/plain`)
- `tags`: List of tags for categorization (can be empty list)

**Optional fields:**
- `uri`: Auto-generated if not provided (`asta://{namespace}/{uuid}`)
- `created_at`: Auto-set on creation
- `modified_at`: Auto-updated on changes
- `extra`: Dict for additional metadata (author, year, venue, etc.)

**Removed from previous versions:**
- ~~`content`~~ - Never stored locally
- ~~`size`~~ - Not relevant without content storage
- ~~`owner_uri`~~ - Single-user model
- ~~`resource_type`~~ - Removed from URI format for simplicity

### Index File Structure

The `.asta/index.yaml` file contains:

```yaml
version: "1.0"

documents:
  - uri: "asta://allenai/asta-resource-repo/550e8400-e29b-41d4-a716-446655440000"
    name: "Attention Is All You Need"
    url: "https://arxiv.org/pdf/1706.03762.pdf"
    summary: "Seminal paper introducing the Transformer architecture"
    tags: ["ai", "research", "transformers", "nlp"]
    mime_type: "application/pdf"
    created_at: "2026-02-06T10:00:00+00:00"
    modified_at: "2026-02-06T10:00:00+00:00"
    extra:
      author: "Vaswani et al"
      year: 2017
      venue: "NeurIPS"
```

## Configuration

Configuration uses HOCON format. The index file location is fixed at `.asta/index.yaml` relative to the current directory.

**Default config** (`src/asta/resources/config/local.conf`):
```hocon
# Allowed MIME types for documents
allowed_mime_types = [
  "application/json",
  "application/pdf",
  "text/plain",
  "text/markdown",
  "text/html"
]
```

**Environment variable overrides:**
- `CONFIG_FILE`: Use different config file
- `ENV`: Load environment-specific config (e.g., `production.conf`)

## Namespace Derivation

**Namespaces are automatically derived at runtime** from the git repository context:

**In a git repository with remote:**
- Format: `{owner}/{repo}`
- Example: `allenai/asta-resource-repo`
- URIs: `asta://allenai/asta-resource-repo/550e8400-...`
- Benefit: URIs are persistent and shareable across all team members and branches
- URIs remain valid when merging between branches

**Outside git or no remote:**
- Format: `local:{absolute_path}`
- Example: `local:/Users/you/project/.asta/index.yaml`
- URIs: `asta://local:/Users/you/project/.asta/index.yaml/550e8400-...`
- Benefit: Still works without git

**No branch isolation:**
- All branches in the same repository share the same namespace
- Feature branches and main branch use identical namespaces
- URIs created on feature branches work after merging to main
- This supports normal git merge workflows

## Git Tracking

**Recommended for teams:**
```bash
# Track the index file in git
git add .asta/index.yaml
git commit -m "Add document index"
git push
```

When tracked in git:
- ✅ Team members get same URIs (same namespace = same URIs)
- ✅ Git shows readable diffs when documents change
- ✅ Document metadata is versioned alongside code

**Personal use (untracked):**
- `.gitignore` allows tracking `.asta/index.yaml` but ignores other `.asta/` files
- If not committed, the index is local-only
- URIs still use git-based namespaces but aren't portable across machines

## MCP Tools

### add_document

Add document metadata to the index.

```python
await add_document(
    url="https://arxiv.org/pdf/1706.03762.pdf",
    name="Attention Is All You Need",
    summary="Transformer architecture paper introducing attention mechanisms",
    mime_type="application/pdf",
    tags=["ai", "research", "transformers"],
    extra_metadata={"author": "Vaswani et al", "year": 2017}
)
```

**Returns**: `DocumentMetadata` with generated URI

### get_document

Retrieve document metadata by URI.

```python
doc = await get_document(
    document_uri="asta://allenai/asta-resource-repo/550e8400-..."
)
```

**Returns**: `DocumentMetadata` or `None` if not found

### list_documents

List all documents in the index.

```python
docs = await list_documents()
```

**Returns**: `list[DocumentMetadata]`

### search_documents

Search documents by query string.

```python
hits = await search_documents(
    query="transformer architecture",
    limit=10
)
```

Searches across: `name`, `summary`, `tags`, `extra` fields
**Returns**: `list[SearchHit]` ranked by relevance

## CLI Commands

### Installation

```bash
# Install project
uv sync

# Verify CLI is available
uv run asta-index --help
```

### Usage

```bash
# Add a document
uv run asta-index add https://arxiv.org/pdf/1706.03762.pdf \
  --name="Attention Is All You Need" \
  --summary="Transformer architecture paper" \
  --tags="ai,research,transformers" \
  --mime-type="application/pdf" \
  --extra='{"author": "Vaswani et al", "year": 2017}'

# List all documents
uv run asta-index list

# List with tag filter
uv run asta-index list --tags="ai,research"

# List with verbose output
uv run asta-index list -v

# Search documents
uv run asta-index search "transformer"

# Get specific document
uv run asta-index get asta://owner/repo/UUID

# Remove document
uv run asta-index remove asta://owner/repo/UUID

# Show index information
uv run asta-index show

# JSON output (for scripting)
uv run asta-index list --json
```

## MCP Integration

### Claude Desktop Setup

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/asta-resource-repo",
        "asta-resources-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop, then use MCP tools from chat:
- "Add a document about Transformers at https://arxiv.org/..."
- "List all documents tagged with 'ai'"
- "Search for papers about attention mechanisms"

### MCP Server (Stdio)

Run standalone MCP server:

```bash
uv run asta-resources-mcp
```

This runs in stdio mode for MCP client integration. No authentication required (single-user model).

## Development Commands

### Code Quality

```bash
# Check formatting and linting
make code-check

# Auto-format code
make code-format
```

### Running Tests

```bash
# Run all tests
make test

# Or directly with pytest
uv run --extra dev pytest tests/ -v

# Run specific test file
uv run --extra dev pytest tests/test_local_index_store.py -v

# Run with coverage
uv run --extra dev pytest tests/ --cov=src/asta/resources --cov-report=html
```

### Test Organization

- `test_local_index_store.py`: LocalIndexDocumentStore backend tests
- `test_mcp_tools.py`: MCP tool integration tests (if exists)
- All tests use temporary directories (no database setup required)

## Project Workflow

### Task Tracking with Beads

The project uses [Beads](https://github.com/steveyegge/beads), a distributed issue tracker for AI coding agents.

**Quick reference:**
```bash
# View ready work
bd ready

# Show task details
bd show <issue-id>

# Update task status
bd update <issue-id> --status in_progress
bd close <issue-id> --reason "Completed"

# Create new task
bd create "Task title" -d "Description" -p 1 -t feature
```

See `BEADS.md` for detailed workflows.

## Common Patterns

### Adding New Metadata Fields

To add a field to document metadata:

1. Update `DocumentMetadata` in `model.py`
2. Update `add_document` tool in `mcp_tools.py` if it should be a parameter
3. Update CLI `add` command in `cli/index_cli.py` if needed
4. Add tests in `tests/test_local_index_store.py`
5. YAML format automatically handles new fields (no migration needed)

### Extending Search

Search is implemented in `LocalIndexDocumentStore.search()`:
- Simple in-memory string matching
- Case-insensitive
- Ranks by number of matches
- To add new searchable fields, update the `search()` method

### Adding New CLI Commands

1. Add command function in `cli/index_cli.py` (e.g., `cmd_export`)
2. Add subparser in `main()` function
3. Test manually with `uv run asta-index <command>`

## Error Handling

Custom exceptions in `exceptions.py`:
- `ValidationError`: Input validation failures (invalid URL, missing fields)
- `DocumentNotFoundError`: Document doesn't exist
- `DocumentServiceError`: Base exception for service errors

MCP tools raise exceptions directly; CLI converts them to user-friendly messages.

## Important Notes

- **Always use `uv run`**: This project uses `uv` for dependency management
- **No External Dependencies**: Zero runtime dependencies except Python stdlib + YAML parser
- **URI Format**: All document URIs follow `asta://{namespace}/{uuid}` where namespace is auto-derived from git
- **Namespace Derivation**: Automatic from git repo (no configuration needed)
- **Git-Friendly**: `.asta/index.yaml` should be committed for team sharing
- **Branch Isolation**: Each git branch gets its own namespace (intentional design)
- **Async/Await**: All document store operations are async for future extensibility
- **YAML Serialization**: Pydantic's `model_dump()` handles datetime serialization automatically

## Troubleshooting

### Index File Corruption

If `.asta/index.yaml` becomes corrupted:

```bash
# Backup corrupt file
cp .asta/index.yaml .asta/index.yaml.backup

# Recreate empty index
rm .asta/index.yaml
uv run asta-index list  # Creates new empty index
```

### Import Errors

```bash
# Reinstall dependencies
uv sync

# Verify installation
uv run python -c "from asta.resources.document_store import LocalIndexDocumentStore; print('OK')"
```

### CLI Not Found

```bash
# Reinstall project
uv sync

# Check entry points
uv run which asta-index
```

## Quick Start Example

```bash
# Navigate to project directory
cd /path/to/asta-resource-repo

# Add your first document
uv run asta-index add https://arxiv.org/pdf/1706.03762.pdf \
  --name="Attention Is All You Need" \
  --summary="Seminal transformer architecture paper" \
  --tags="ai,nlp,transformers"

# List documents
uv run asta-index list

# Search
uv run asta-index search "attention"

# View the index file directly
cat .asta/index.yaml

# Commit to git
git add .asta/index.yaml
git commit -m "Add transformer paper to index"
```

## Migration from Previous Versions

If migrating from older versions:

**From PostgreSQL/REST API versions:**
1. **No automatic migration tool** - data must be manually re-added
2. Previous database contents are not compatible with YAML index
3. REST API and unified server have been removed
4. User authentication (`ASTA_USER`) is no longer required
5. File size limits removed (no content storage)

**From "local-index" namespace versions:**
1. Namespace is now auto-derived from git (no longer configurable)
2. Old URIs with `asta://local-index/...` won't match new git-based namespaces
3. Index files must be recreated - URIs will change to reflect git context
4. No migration tool provided (breaking change for simplicity)

Start with a fresh index using `asta-index add` commands.
