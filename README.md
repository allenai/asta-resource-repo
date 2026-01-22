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
- `search_documents` - Search by keywords
- `get_document` - Get details by URI

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
uv run asta-index search "transformer architecture"
```

### Get Document Details

```bash
uv run asta-index get asta://local-index/document/UUID
```

### Remove Document

```bash
uv run asta-index remove asta://local-index/document/UUID
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
namespace: "local-index"

documents:
  - uri: "asta://local-index/document/550e8400-..."
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

### Document Structure

Each document has:

**Required:**
- `url` - Where the document lives (any HTTP/HTTPS URL)
- `name` - Document title
- `summary` - Description (used for search)
- `mime_type` - Document type (e.g., `application/pdf`, `text/html`)
- `tags` - List of tags (can be empty)

**Auto-generated:**
- `uri` - Unique identifier (`asta://local-index/document/UUID`)
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

### Environment Variables

- `INDEX_PATH` - Override index file location (default: `.asta/index.yaml`)
- `NAMESPACE` - Change URI namespace (default: `local-index`)
- `RESOURCE_TYPE` - Change resource type (default: `document`)

### Config File

Edit `src/asta/resources/config/local.conf` for persistent settings.

### Multiple Indexes

Run multiple instances with different index files by setting `INDEX_PATH`:

```bash
# Work index
INDEX_PATH=~/work-docs/.asta/index.yaml uv run asta-index list

# Personal index
INDEX_PATH=~/personal/.asta/index.yaml uv run asta-index list
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
