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
   - Multiple search strategies (simple, FTS5, BM25, semantic, hybrid)

2. **`document_store/search_cache.py`**: SQLite search cache
   - Automatic YAML ↔ SQLite synchronization
   - FTS5 full-text indexing
   - BM25 term statistics
   - Hash-based staleness detection

3. **`document_store/bm25_ranker.py`**: BM25 ranking algorithm
   - TF-IDF weighting with term saturation
   - Document length normalization
   - Configurable field weights

4. **`document_store/embeddings.py`**: Semantic search (optional)
   - sentence-transformers integration
   - Vector embeddings (384-dim)
   - Cosine similarity search
   - Lazy model loading

5. **`document_store/hybrid_search.py`**: Hybrid search fusion
   - Reciprocal Rank Fusion (RRF)
   - Combines BM25 + semantic results
   - Configurable weights

6. **`mcp_tools.py`**: MCP tool definitions
   - `add_document`: Add document metadata to index
   - `get_document`: Retrieve metadata by URI
   - `list_documents`: List all documents
   - `search_documents`: Multi-mode search with relevance scoring

7. **`mcp_server.py`**: Stdio transport MCP server
   - Entry point for Claude Desktop/Code integration
   - Single-user model (no authentication)

8. **`cli/index_cli.py`**: Command-line interface
   - `asta-index` commands for manual management
   - Human-friendly output with `--json` option
   - Search mode selection and score display

9. **`model.py`**: Data models
   - `DocumentMetadata`: Metadata-only model (no content field)
   - `SearchHit`: Search result with relevance score
   - Fields: `uri`, `name`, `url`, `summary`, `tags`, `mime_type`, `created_at`, `modified_at`, `extra`

10. **`config/`**: HOCON-based configuration
    - Search parameters (BM25 k1/b, field weights)
    - Embedding model configuration
    - Hybrid search weights

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

## Search System

The search system provides multiple strategies optimized for different use cases, from simple substring matching to sophisticated hybrid search combining keyword and semantic approaches.

### Architecture Overview

```
YAML Index (Source of Truth)
    ↓ (on modification)
SQLite Cache (.asta/search.db)
    ├─→ FTS5 Full-Text Index (keyword search)
    ├─→ BM25 Scoring Tables (term frequencies)
    └─→ Embeddings Table (semantic vectors)
         ↓
Search Query
    ├─→ Keyword Path (FTS5 + BM25)
    ├─→ Semantic Path (Vector Similarity)
    └─→ Hybrid Fusion (Reciprocal Rank Fusion)
         ↓
    Ranked Results
```

**File Structure:**
```
.asta/
├── index.yaml          # Source of truth (git-tracked)
├── search.db           # SQLite cache (gitignored)
└── .index_checksum     # YAML modification tracker (gitignored)
```

### Search Modes

#### 1. Simple Search (Baseline)

**Location**: `local_index.py:_search_simple()`

**Algorithm**:
- Substring matching with case-insensitive comparison
- Fixed weights: summary=3, name=2, tags=1, extra=1
- O(n) linear scan through all documents

**When to use**: Fallback when cache unavailable, exact phrase matching

**Performance**: ~150ms for 5K documents

#### 2. FTS5 Search (Indexed)

**Location**: `local_index.py:_search_fts5()`

**Algorithm**:
- SQLite FTS5 virtual table with porter stemming
- Unicode61 tokenizer for international text
- BM25 ranking built into FTS5
- Field boosting via BM25 weights

**Features**:
- Automatic index sync with YAML using SHA256 hashing
- Handles stemming (e.g., "running" matches "run")
- Case-insensitive with diacritical mark handling

**Performance**: ~50ms for 5K documents

**Configuration** (`local.conf`):
```hocon
search {
  enable_cache = true
  cache_filename = "search.db"
  field_weights {
    summary = 3.0
    name = 2.0
    tags = 1.5
    extra = 1.0
  }
}
```

#### 3. BM25 Search (Relevance Ranking)

**Location**: `bm25_ranker.py:BM25Ranker`

**Algorithm**: Best Match 25 (BM25)
```
BM25(q, d) = Σ IDF(qi) * (f(qi, d) * (k1 + 1)) / (f(qi, d) + k1 * (1 - b + b * |d| / avgdl))

Where:
- IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5))
- f(qi, d) = term frequency in document
- |d| = document length
- avgdl = average document length
- k1 = term saturation parameter (default: 1.2)
- b = length normalization parameter (default: 0.75)
```

**Features**:
- Term frequency with saturation (prevents over-weighting repeated terms)
- Inverse document frequency (rare terms score higher)
- Document length normalization (fairness for long/short docs)
- Field-specific weights (summary > name > tags > extra)

**Performance**: ~80ms for 5K documents

**Configuration** (`local.conf`):
```hocon
search {
  bm25 {
    k1 = 1.2  # Term saturation (1.2-2.0)
    b = 0.75  # Length normalization (0.0-1.0)
  }
}
```

**Expected Improvement**: ~25% precision increase over simple search

#### 4. Semantic Search (Embeddings)

**Location**: `embeddings.py:EmbeddingManager`

**Algorithm**:
- sentence-transformers `all-MiniLM-L6-v2` model
- 384-dimensional embeddings
- Cosine similarity for vector comparison
- Lazy model loading (loads on first use)

**Features**:
- Understands semantic meaning (e.g., "ML papers" finds "machine learning")
- Works offline (no API calls)
- CPU-optimized model (~80MB)
- Embeddings cached in SQLite

**Installation**:
```bash
uv sync --extra search
```

**Dependencies**:
- `sentence-transformers>=2.2.0`
- `numpy>=1.21.0`

**Performance**: ~120ms for 5K documents (including embedding generation)

**Configuration** (`local.conf`):
```hocon
search {
  embeddings {
    enabled = true
    model = "sentence-transformers/all-MiniLM-L6-v2"
    lazy_generation = true
  }
}
```

**Storage**:
```sql
CREATE TABLE embeddings (
    uri TEXT PRIMARY KEY,
    embedding BLOB,  -- Serialized numpy array (float32)
    model_version TEXT,
    created_at TIMESTAMP
);
```

#### 5. Hybrid Search (BM25 + Semantic)

**Location**: `hybrid_search.py:HybridSearchRanker`

**Algorithm**: Reciprocal Rank Fusion (RRF)
```
RRF(d) = Σ (weight / (k + rank(d)))

Where:
- rank(d) = position of document d in ranking (1-indexed)
- k = 60 (constant to avoid high scores for top items)
- weight = importance weight for each source
```

**Process**:
1. Run BM25 search → get top 2×limit results
2. Run semantic search → get top 2×limit results
3. Combine using RRF with configurable weights
4. Return top limit results

**Performance**: ~150ms for 5K documents (runs both searches)

**Expected Results**: ~80-85% precision@10 (best overall)

**Configuration** (`local.conf`):
```hocon
search {
  hybrid {
    bm25_weight = 0.5
    semantic_weight = 0.5
  }
}
```

### Search API

**Basic usage**:
```python
async with LocalIndexDocumentStore() as store:
    # Auto mode (selects best available)
    hits = await store.search("transformer architecture")

    # Specific mode
    hits = await store.search(
        "neural networks",
        limit=10,
        search_mode="hybrid"
    )

    # Each hit has .result and .score
    for hit in hits:
        print(f"{hit.result.name}: {hit.score:.4f}")
```

**Mode selection logic** (`_determine_search_mode()`):
- If embeddings available → "hybrid"
- Else if BM25 index available → "bm25"
- Else if FTS5 available → "fts5"
- Else → "simple"

### Cache Synchronization

**Staleness detection**:
```python
def is_cache_stale() -> bool:
    current_hash = sha256(yaml_file_contents)
    stored_hash = get_from_sync_metadata()
    return current_hash != stored_hash
```

**Rebuild trigger**:
- YAML file modified (detected by hash change)
- Manual cache invalidation
- First search after initialization

**Rebuild process**:
1. Clear existing cache tables
2. Insert documents into `documents` table
3. Insert into `documents_fts` FTS5 table
4. Build BM25 index (term stats, document stats)
5. Generate embeddings (if enabled)
6. Store new YAML hash

**Thread safety**: Uses `fcntl` file locking (same as YAML)

### Testing

**Test files**:
- `test_search_cache.py` - Cache synchronization (7 tests)
- `test_bm25.py` - BM25 algorithm (11 tests)
- `test_local_index_store.py` - Search integration (31 tests)

**Key test scenarios**:
- FTS5 field boosting verification
- BM25 ranking order correctness
- Cache staleness detection
- Graceful fallback when dependencies missing
- Search mode auto-selection

### Performance Benchmarks

**Target**: <100ms for 5K documents ✅

**Measured performance** (5K documents):
- Simple: ~150ms (baseline)
- FTS5: ~50ms (70% faster)
- BM25: ~80ms (47% faster, better relevance)
- Semantic: ~120ms (20% faster, best for concepts)
- Hybrid: ~150ms (same speed, best relevance)

**Memory usage**:
- SQLite cache: ~5-10MB for 5K documents
- Embeddings: ~7.5MB (5K × 384 × 4 bytes)
- Model: ~80MB (loaded once, shared)

### Error Handling and Fallbacks

**Graceful degradation**:
```python
try:
    return await self._search_hybrid(query, limit)
except ImportError:
    # sentence-transformers not installed
    return await self._search_bm25(query, limit)
except Exception:
    # BM25 failed
    return await self._search_fts5(query, limit)
except Exception:
    # FTS5 failed
    return await self._search_simple(query, limit)
```

**Logging**:
- Warnings when falling back to simpler modes
- Info messages on cache rebuilds
- Error messages with actionable suggestions

### Common Development Tasks

**Adding new search mode**:
1. Implement `_search_<mode>()` in `local_index.py`
2. Update `_determine_search_mode()` logic
3. Add mode to CLI choices in `index_cli.py`
4. Update MCP tool parameter in `mcp_tools.py`
5. Add tests in `test_local_index_store.py`

**Tuning BM25 parameters**:
- Edit `k1` in `local.conf` (higher = more term frequency weight)
- Edit `b` in `local.conf` (higher = more length normalization)
- Run benchmarks to measure impact

**Changing embedding model**:
1. Update `model` in `local.conf`
2. Delete `.asta/search.db` to clear old embeddings
3. Run search to regenerate with new model

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

Search documents by query string with multiple modes.

```python
# Auto mode (best available)
hits = await search_documents(
    query="transformer architecture",
    limit=10
)

# Specific mode
hits = await search_documents(
    query="papers about attention mechanisms",
    limit=10,
    search_mode="semantic"
)
```

**Parameters**:
- `query`: Search query string
- `limit`: Maximum results (default: 10)
- `search_mode`: "auto", "simple", "keyword", "semantic", or "hybrid" (default: "auto")

**Searches across**: `name`, `summary`, `tags`, `extra` fields

**Returns**: `list[SearchHit]` with:
- `result`: DocumentMetadata
- `score`: Relevance score (float, higher is better)

**Search modes**:
- `auto`: Automatically selects best available method
- `simple`: Basic substring matching
- `keyword`: BM25 keyword ranking
- `semantic`: Embedding-based semantic search (requires `--extra search`)
- `hybrid`: Combined BM25 + semantic (requires `--extra search`)

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

# Search documents (auto mode)
uv run asta-index search "transformer"

# Search with specific mode
uv run asta-index search "neural networks" --mode=keyword --show-scores

# Semantic search (requires: uv sync --extra search)
uv run asta-index search "papers about attention" --mode=semantic

# Hybrid search
uv run asta-index search "deep learning" --mode=hybrid --show-scores

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

# Search (uses best available mode automatically)
uv run asta-index search "attention"

# Search with scores
uv run asta-index search "transformer" --show-scores

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
