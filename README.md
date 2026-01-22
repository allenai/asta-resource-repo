# Asta Resource Repository

A lightweight document metadata index for AI coding agents. Track documents, papers, and resources with tags and summaries—no databases, just a git-friendly YAML file.

## What It Does

This tool helps you and your AI agents keep track of documents by storing **metadata only** (URLs, summaries, tags) in a simple `.asta/index.yaml` file. Think of it as a smart bookmark manager that AI agents can use.

**Key Features:**
- 📋 **Metadata only**: URLs, summaries, tags—no content storage
- 🤖 **MCP integration**: Works natively with Claude Desktop and Claude Code
- ⚡ **Zero setup**: No databases, no Docker, no external services
- 📝 **Git-friendly**: Human-readable YAML diffs
- 🔍 **Searchable**: Full-text search across all metadata fields
- 🏷️ **Taggable**: Organize with custom tags
- 🚀 **Portable**: Copy `.asta/` folder anywhere

## Installation

**One-line install:**

```bash
curl -fsSL https://raw.githubusercontent.com/allenai/asta-resource-repo/main/install.sh | bash
```

The installer automatically:
- ✅ Installs uv package manager (if needed)
- ✅ Clones to `~/.asta-resources`
- ✅ Installs dependencies
- ✅ Shows MCP setup instructions

**Full installation guide**: [INSTALL.md](INSTALL.md)

**Requirements**: Python 3.10+ (installer checks automatically)

## Quick Start with Claude

### For Claude Code Users

**Complete setup guide**: See [MCP_SETUP.md](MCP_SETUP.md)

**Quick config:**
1. Press `Cmd+Shift+P` → "MCP: Edit Configuration"
2. Add this server (replace path with your repo location):

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

3. Reload MCP servers (`Cmd+Shift+P` → "MCP: Reload Servers")

### For Claude Desktop Users

See [MCP_SETUP.md](MCP_SETUP.md) for complete instructions.

### Using with Claude

Once configured, just talk naturally to Claude:

```
💬 "Add a document at https://arxiv.org/pdf/1706.03762.pdf
    about the Transformer architecture,
    tags: ai, research, nlp"

💬 "List all documents tagged with 'research'"

💬 "Search for papers about attention mechanisms"

💬 "Show me all my AI-related documents"
```

Claude will use these MCP tools:
- `add_document` - Add document metadata
- `list_documents` - List all documents
- `search_documents` - Search by keywords (with multiple modes)
- `get_document` - Get details by URI

## Advanced Search

Asta includes a sophisticated search system with multiple modes optimized for different use cases:

### Search Modes

**🤖 Auto Mode** (default)
- Automatically selects the best available search method
- No configuration needed—just works!

**⚡ Simple Mode**
- Basic substring matching
- Fastest, no dependencies
- Good for exact phrase matching

**🎯 Keyword Mode** (BM25)
- Industry-standard BM25 ranking algorithm
- Best for exact keyword matches
- Fast indexed search (~80ms for 5K documents)
- Automatically available (no extra setup)

**🧠 Semantic Mode** (Embeddings)
- Understands meaning and concepts, not just keywords
- Best for natural language queries like "papers about attention mechanisms"
- Uses sentence-transformers for offline AI embeddings
- Requires installation: `uv sync --extra search` (~80MB model download)

**🚀 Hybrid Mode** (BM25 + Semantic)
- Combines keyword precision with semantic understanding
- Best overall relevance (~80-85% precision@10)
- Uses Reciprocal Rank Fusion to merge results
- Requires installation: `uv sync --extra search`

### Installing Semantic Search

To enable semantic and hybrid search:

```bash
# Install with semantic search support
cd /path/to/asta-resource-repo
uv sync --extra search
```

This installs `sentence-transformers` and downloads the `all-MiniLM-L6-v2` model (~80MB, optimized for CPU).

### Performance

Tested with 5K documents:
- Simple: ~150ms (linear scan)
- Keyword (BM25): ~80ms (indexed)
- Semantic: ~120ms (with embeddings)
- Hybrid: ~150ms (best results)

All modes run locally with no external API calls.

## Command Line Usage

Prefer the command line? Use the `asta-index` CLI:

### Add a Document

```bash
uv run asta-index add https://arxiv.org/pdf/1706.03762.pdf \
  --name="Attention Is All You Need" \
  --summary="Seminal paper on Transformer architecture" \
  --tags="ai,nlp,transformers" \
  --mime-type="application/pdf" \
  --extra='{"author": "Vaswani et al", "year": 2017}'
```

### List Documents

```bash
# List all
uv run asta-index list

# Filter by tags
uv run asta-index list --tags="ai,research"

# Verbose output
uv run asta-index list -v

# JSON output (for scripts)
uv run asta-index list --json
```

### Search Documents

```bash
# Auto mode (uses best available method)
uv run asta-index search "transformer architecture"

# Keyword search with scores
uv run asta-index search "neural networks" --mode=keyword --show-scores

# Semantic search (requires: uv sync --extra search)
uv run asta-index search "papers about attention mechanisms" --mode=semantic

# Hybrid search for best results
uv run asta-index search "deep learning" --mode=hybrid --show-scores

# See all options
uv run asta-index search --help
```

**Search mode options:**
- `--mode=auto` - Auto-select best available (default)
- `--mode=simple` - Fast substring matching
- `--mode=keyword` - BM25 keyword ranking
- `--mode=semantic` - AI embeddings (requires `--extra search`)
- `--mode=hybrid` - Combined BM25 + semantic (requires `--extra search`)
- `--show-scores` - Display relevance scores

### Get Document Details

```bash
uv run asta-index get asta://owner/repo/UUID
```

### Remove Document

```bash
uv run asta-index remove asta://owner/repo/UUID
```

### Show Index Stats

```bash
uv run asta-index show
```

## How It Works

### Index File

All metadata is stored in `.asta/index.yaml`:

```yaml
version: "1.0"

documents:
  - uri: "asta://allenai/asta-resource-repo/550e8400-..."
    name: "Attention Is All You Need"
    url: "https://arxiv.org/pdf/1706.03762.pdf"
    summary: "Transformer architecture paper"
    tags: ["ai", "research", "transformers"]
    mime_type: "application/pdf"
    created_at: "2026-02-06T10:00:00+00:00"
    extra:
      author: "Vaswani et al"
      year: 2017
```

### Namespaces and URIs

Document URIs are automatically derived from your git repository:

**In a git repository:**
- Format: `asta://{owner}/{repo}/{uuid}`
- Example: `asta://allenai/asta-resource-repo/550e8400-...`
- URIs are **persistent and shareable** across all team members and branches
- URIs remain valid when merging between branches (no branch in namespace)

**Outside git (or no remote configured):**
- Format: `asta://local:{absolute_path}/{uuid}`
- Example: `asta://local:/Users/you/project/.asta/index.yaml/550e8400-...`
- URIs are local-only and not shareable

### Git Tracking Behavior

**Tracked index files** (recommended for teams):
```bash
# Add to git for team sharing
git add .asta/index.yaml
git commit -m "Add research papers to index"
git push
```

When your team pulls the changes, they'll have:
- ✅ Same namespace (same URIs work for everyone on all branches)
- ✅ Same document metadata
- ✅ Git-readable diffs when documents change
- ✅ URIs work after merging between branches

**Untracked index files** (personal use):
- The `.gitignore` allows `.asta/index.yaml` but ignores other `.asta/` files
- If not committed, the index is local-only to your machine
- URIs still use git-based namespaces but aren't portable across machines
- Useful for personal bookmarks you don't want to share

### Document Structure

Each document has:

**Required:**
- `url` - Where the document lives (any HTTP/HTTPS URL)
- `name` - Document title
- `summary` - Description (used for search)
- `mime_type` - Document type (e.g., `application/pdf`, `text/html`)
- `tags` - List of tags (can be empty)

**Auto-generated:**
- `uri` - Unique identifier (format: `asta://{namespace}/{uuid}`)
- `created_at` - Creation timestamp
- `modified_at` - Last update timestamp

**Optional:**
- `extra` - Custom metadata (author, year, venue, etc.)

### Why Metadata Only?

1. **Small and fast**: No large files in git, instant search
2. **No copyright issues**: Metadata is fair use
3. **Portable**: Works with any URL-accessible content
4. **Flexible**: Content can move, metadata stays stable
5. **Git-friendly**: Track changes in readable YAML diffs

## Use Cases

### Research Management

Track papers, articles, and preprints:
```bash
uv run asta-index add https://arxiv.org/pdf/2304.08485.pdf \
  --name="LLaMA: Open Foundation Models" \
  --summary="Meta's open source LLM" \
  --tags="ai,llm,research" \
  --extra='{"venue": "arXiv", "year": 2023}'
```

### Bookmark Management

Organize web resources:
```bash
uv run asta-index add https://modelcontextprotocol.io/ \
  --name="Model Context Protocol" \
  --summary="MCP documentation and guides" \
  --tags="mcp,documentation,reference"
```

### Project Documentation

Index project-related documents:
```bash
uv run asta-index add https://github.com/user/repo/blob/main/DESIGN.md \
  --name="Project Design Doc" \
  --summary="Architecture and design decisions" \
  --tags="internal,design,architecture"
```

### Team Collaboration

Commit `.asta/index.yaml` to git to share with your team:
```bash
git add .asta/index.yaml
git commit -m "Add ML papers to research index"
git push
```

## Configuration

### Index File Location

The index is always stored at `.asta/index.yaml` relative to your current directory.

To use separate indexes for different projects:
```bash
# Work project
cd ~/work-project
uv run asta-index list

# Personal project
cd ~/personal-project
uv run asta-index list
```

Each directory gets its own `.asta/index.yaml` file.

### Allowed MIME Types

Edit `src/asta/resources/config/local.conf` to customize allowed document types:

```hocon
allowed_mime_types = [
  "application/json",
  "application/pdf",
  "text/plain",
  "text/markdown",
  "text/html"
]
```

## Troubleshooting

### "Command not found: uv"

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### MCP Server Not Working

See detailed troubleshooting in [MCP_SETUP.md](MCP_SETUP.md).

### Index File Not Found

The index file is created automatically on first use. If missing:
```bash
mkdir -p .asta
uv run asta-index show  # Creates empty index
```

## Development

Want to contribute or modify the code? See:
- **[CLAUDE.md](CLAUDE.md)** - Architecture and development guide
- **[BEADS.md](BEADS.md)** - Issue tracking with Beads

### Quick Commands

```bash
# Run tests
make test

# Format code
make code-format

# Check code quality
make code-check
```

## Links

- **MCP Setup**: [MCP_SETUP.md](MCP_SETUP.md)
- **Development Guide**: [CLAUDE.md](CLAUDE.md)
- **Chatbot Usage**: [README_CHATBOT.md](README_CHATBOT.md)
- **Model Context Protocol**: https://modelcontextprotocol.io/
- **Claude Desktop**: https://claude.ai/download
- **Beads Issue Tracker**: https://github.com/steveyegge/beads

## License

MIT License
