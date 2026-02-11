---
name: asta-documents
description: Local document metadata index for scientific documents
---

# Asta Documents Management

This skill provides complete document management functionality for tracking research papers, documentation, and resources using the `asta-documents` CLI.

**What it does:** Track document metadata (URLs, summaries, tags) in a local git-friendly YAML file. Think of it as a smart bookmark manager with powerful search capabilities.

## Installation

### 1. Install the CLI Tool

```bash
# Install globally using uv
uv tool install git+https://github.com/allenai/asta-resource-repo.git
```

This installs the `asta-documents` command globally on your system.

**Prerequisites:** Python 3.10+ and [uv package manager](https://docs.astral.sh/uv/)

### 2. Install This Skill

Copy this file to your Claude Code skills directory:

```bash
# macOS/Linux
mkdir -p ~/.claude/skills
curl -o ~/.claude/skills/asta-documents.md https://raw.githubusercontent.com/allenai/asta-resource-repo/main/skills/asta-documents.md

# Or manually copy this file to ~/.claude/skills/
```

### 3. Verify Installation

```bash
# Test the CLI
asta-documents --help

# Verify skill is available
# In Claude Code, type /asta-documents
```

## Core Concepts

**Asta stores metadata only** - not document content:
- **URL**: Where the actual document lives (must be HTTP/HTTPS)
- **Name**: Document title
- **Summary**: Description for search (required, indexed)
- **Tags**: Categorization labels
- **MIME type**: Document type (application/pdf, text/plain, etc.)
- **Extra metadata**: Custom fields (author, year, venue, etc.)

**Document URIs**: Auto-generated identifiers like `asta://namespace/uuid`

**Index location**: `.asta/documents/index.yaml` (git-tracked, shareable)

**Content cache**: `.asta/documents/cache/` (gitignored, auto-managed)

## Quick Command Reference

```bash
# List documents
asta-documents list
asta-documents list --tags="ai,research"
asta-documents list -v  # Verbose

# Search documents
asta-documents search "query"
asta-documents search "query" --mode=hybrid --show-scores

# Add document
asta-documents add <url> --name="Title" --summary="Description" --tags="tag1,tag2"

# Get document metadata
asta-documents get <asta-uri>

# Update document
asta-documents update <asta-uri> --name="New Title" --tags="new,tags"

# Fetch document content
asta-documents fetch <asta-uri> -o /tmp/document.pdf

# Manage tags
asta-documents add-tags <asta-uri> --tags="new,tags"
asta-documents remove-tags <asta-uri> --tags="old,tags"
asta-documents list-by-tags --tags="ai,ml"

# Cache management
asta-documents cache list
asta-documents cache stats
asta-documents cache clean --days 7

# Index information
asta-documents show
```

## Operations

### 1. List Documents

**List all documents:**
```bash
asta-documents list
```

**Filter by tags:**
```bash
asta-documents list --tags="ai,research"
```

**Verbose output (shows all metadata):**
```bash
asta-documents list -v
```

**JSON output (for processing):**
```bash
asta-documents list --json
```

### 2. Search Documents

**Basic search (auto mode):**
```bash
asta-documents search "query string"
```

**Search with specific mode:**
```bash
# Simple substring matching
asta-documents search "query" --mode=simple

# Keyword search (BM25)
asta-documents search "query" --mode=keyword

# Semantic search
asta-documents search "query" --mode=semantic

# Hybrid (BM25 + semantic, best results)
asta-documents search "query" --mode=hybrid
```

**Show relevance scores:**
```bash
asta-documents search "query" --show-scores
```

**Limit results:**
```bash
asta-documents search "query" --limit 5
```

**JSON output:**
```bash
asta-documents search "query" --json
```

### 3. Add Document

**Add with required fields:**
```bash
asta-documents add <url> \
  --name="Document Title" \
  --summary="Description for search" \
  --mime-type="application/pdf"
```

**Add with tags:**
```bash
asta-documents add <url> \
  --name="Document Title" \
  --summary="Description" \
  --tags="ai,research,transformers"
```

**Add with extra metadata:**
```bash
asta-documents add <url> \
  --name="Document Title" \
  --summary="Description" \
  --tags="ai,research" \
  --extra='{"author": "Smith et al", "year": 2024, "venue": "NeurIPS"}'
```

**Common MIME types:**
- `application/pdf` - PDF documents
- `text/plain` - Plain text
- `text/markdown` - Markdown
- `text/html` - HTML
- `application/json` - JSON

### 4. Get Document Metadata

**Get by URI:**
```bash
asta-documents get asta://namespace/uuid
```

**JSON output:**
```bash
asta-documents get asta://namespace/uuid --json
```

### 5. Update Document

**Update single field:**
```bash
asta-documents update <asta-uri> --name="New Title"
```

**Update multiple fields:**
```bash
asta-documents update <asta-uri> \
  --name="New Title" \
  --summary="Updated description" \
  --tags="updated,revised"
```

**Update extra metadata:**
```bash
asta-documents update <asta-uri> \
  --extra='{"author": "New Author", "year": 2025}'
```

**Note**: Tags and extra metadata are replaced entirely, not merged.

### 6. Manage Tags

**Add tags (preserves existing):**
```bash
asta-documents add-tags <asta-uri> --tags="new,additional"
```

**Remove tags:**
```bash
asta-documents remove-tags <asta-uri> --tags="old,deprecated"
```

**List documents by tags (any match):**
```bash
asta-documents list-by-tags --tags="ai,ml"
```

**List documents by tags (all must match):**
```bash
asta-documents list-by-tags --tags="ai,research" --match-all
```

### 7. Remove Document

**Remove by URI:**
```bash
asta-documents remove <asta-uri>
```

### 8. Fetch Document Content

**Fetch to file (with automatic caching):**
```bash
asta-documents fetch <asta-uri> -o /tmp/document.pdf
```

**Fetch to stdout:**
```bash
asta-documents fetch <asta-uri> > document.pdf
```

**Force fresh download (bypass cache):**
```bash
asta-documents fetch <asta-uri> -o document.pdf --force
```

**Custom cache age (days):**
```bash
asta-documents fetch <asta-uri> -o document.pdf --max-age 30
```

**Quiet mode (suppress progress):**
```bash
asta-documents fetch <asta-uri> -o document.pdf -q
```

**After fetching, use Read tool for PDFs:**
```bash
# 1. Fetch document
asta-documents fetch <asta-uri> -o /tmp/doc.pdf -q

# 2. Extract and display with Read tool
# Read(/tmp/doc.pdf)
# The Read tool has native PDF support for better text extraction
```

### 9. Cache Management

**List cached items:**
```bash
asta-documents cache list
```

**Show cache statistics:**
```bash
asta-documents cache stats
```

**Clean old cache entries:**
```bash
# Remove items older than 7 days (default)
asta-documents cache clean

# Remove items older than N days
asta-documents cache clean --days 14

# Dry run (see what would be removed)
asta-documents cache clean --dry-run
```

**Clear entire cache:**
```bash
asta-documents cache clear
asta-documents cache clear -y  # Skip confirmation
```

**Show specific item details:**
```bash
asta-documents cache info <hash>
```

### 10. Index Information

**Show index stats:**
```bash
asta-documents show
```

## Common Workflows

### Workflow 1: Add and Organize Papers

```bash
# Add research paper
asta-documents add https://arxiv.org/pdf/1706.03762.pdf \
  --name="Attention Is All You Need" \
  --summary="Seminal paper introducing Transformer architecture" \
  --tags="ai,research,nlp,transformers" \
  --mime-type="application/pdf" \
  --extra='{"author": "Vaswani et al", "year": 2017, "venue": "NeurIPS"}'

# List papers by tag
asta-documents list-by-tags --tags="transformers"
```

### Workflow 2: Search and Fetch

```bash
# Search for relevant documents
asta-documents search "transformer architecture" --show-scores

# Get metadata for top result
asta-documents get asta://namespace/uuid

# Fetch content
asta-documents fetch asta://namespace/uuid -o /tmp/paper.pdf -q

# Read with PDF support
# Read(/tmp/paper.pdf)
```

### Workflow 3: Search with JSON Processing

```bash
# Search and extract URIs
RESULTS=$(asta-documents search "query" --json)

# Get first URI (example with Python)
URI=$(echo "$RESULTS" | python3 -c "import sys,json; results=json.load(sys.stdin); print(results[0]['result']['uri'] if results else '')")

# Fetch that document
asta-documents fetch "$URI" -o result.pdf
```

### Workflow 4: Bulk Tag Management

```bash
# List documents with old tag
DOCS=$(asta-documents list-by-tags --tags="old-tag" --json)

# For each, remove old tag and add new
for uri in $(echo "$DOCS" | python3 -c "import sys,json; print('\\n'.join([d['uri'] for d in json.load(sys.stdin)]))"); do
    asta-documents remove-tags "$uri" --tags="old-tag"
    asta-documents add-tags "$uri" --tags="new-tag"
done
```

### Workflow 5: Update Multiple Fields

```bash
# Get current metadata
asta-documents get asta://namespace/uuid

# Update multiple fields
asta-documents update asta://namespace/uuid \
  --name="Updated Title" \
  --summary="Updated summary with more details" \
  --tags="updated,revised,2025"
```

### Workflow 6: Cache Maintenance

```bash
# Check cache usage
asta-documents cache stats

# List what's cached
asta-documents cache list

# Remove old entries if cache is large
asta-documents cache clean --days 7

# Verify cache reduction
asta-documents cache stats
```

## Search Modes Explained

**auto** (default) - Automatically selects best available:
- Uses hybrid if embeddings available
- Falls back to keyword (BM25) if not
- Fast and smart

**simple** - Basic substring matching:
- Fastest, works everywhere
- Case-insensitive
- Good for exact phrases

**keyword** - BM25 ranking:
- Industry-standard keyword search
- Fast indexed search
- Good for specific terms

**semantic** - AI embeddings
- Understands concepts and meaning
- Best for natural language queries
- Works offline (no API calls)

**hybrid** - Combined BM25 + semantic
- Best overall relevance
- Balances precision and recall
- ~80-85% precision@10

## Output Formats

**Human-readable (default):**
- Formatted tables and lists
- Color-coded (if terminal supports)
- Progress messages

**JSON (`--json` flag):**
- Machine-readable
- All fields included
- For scripting and integration

**Verbose (`-v` flag for list):**
- Shows all metadata fields
- Includes extra metadata
- Full URIs and timestamps

## Best Practices

1. **Use descriptive summaries**: They're indexed for search
2. **Tag consistently**: Establish a tagging scheme
3. **Use extra metadata**: Store author, year, venue for papers
4. **Search with hybrid mode**: Best results if you have embeddings
5. **Let fetch handle caching**: Don't manually check cache
6. **Clean cache monthly**: Prevent disk usage buildup
7. **Use JSON for scripting**: More reliable than parsing text
8. **Use quiet mode in scripts**: `-q` suppresses progress messages
9. **Commit index to git**: Share with your team
10. **Use namespaces**: Auto-derived from git repo for portability

## Troubleshooting

**"asta-documents: command not found"**
- Verify installation: `uv tool list | grep asta`
- Add to PATH: `export PATH="$HOME/.local/bin:$PATH"`
- Reinstall: `uv tool install --reinstall git+https://github.com/allenai/asta-resource-repo.git`

**"Document not found"**
- Verify URI: `asta-documents list --json | grep <partial-uri>`
- Check namespace: URIs are namespace-specific
- Ensure you're in correct directory (index is `.asta/documents/index.yaml`)

**"Fetch failed"**
- Check URL is accessible: `curl -I <url>`
- Try force refresh: `--force`
- Check network connection

**"Search returns no results"**
- Try simpler query terms
- Use `--mode=simple` for exact matching
- Check if documents exist: `asta-documents list`

**"Cache is large"**
- Check size: `asta-documents cache stats`
- Clean old entries: `asta-documents cache clean --days 7`
- Clear if needed: `asta-documents cache clear -y`

**"Semantic search not working"**
- Reinstall with embeddings: `uv tool install --reinstall git+https://github.com/allenai/asta-resource-repo.git`
- Check mode availability: Search will fall back automatically

**"Skill not found in Claude Code"**
- Verify skill is in `~/.claude/skills/asta-documents.md`
- Restart Claude Code
- Check skill frontmatter has correct format

## Updating

**Update the CLI tool:**
```bash
uv tool install --reinstall git+https://github.com/allenai/asta-resource-repo.git
```

**Update the skill:**
```bash
curl -o ~/.claude/skills/asta-documents.md https://raw.githubusercontent.com/allenai/asta-resource-repo/main/skills/asta-documents.md
```

## Notes

- Index is at `.asta/documents/index.yaml` (git-friendly, commit to share with team)
- Cache is at `.asta/documents/cache/` (gitignored, managed automatically)
- Document URIs are stable within a git repository
- All operations are safe (file locking prevents corruption)
- Search cache auto-syncs when index changes
- Content cache uses SHA256 of URL as key
- For development, use `uv run asta-documents` from cloned repo

## Links

- **Repository**: https://github.com/allenai/asta-resource-repo
- **Documentation**: https://github.com/allenai/asta-resource-repo/blob/main/README.md
- **Issues**: https://github.com/allenai/asta-resource-repo/issues
