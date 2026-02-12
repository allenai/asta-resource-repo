# Asta Resource Repository

A lightweight document metadata index for AI coding agents. Track documents, papers, and resources with tags and summaries—no databases, just a git-friendly YAML file.

## What It Does

This tool helps you and your AI agents keep track of documents by storing **metadata only** (URLs, summaries, tags) in a simple `.asta/documents/index.yaml` file. Think of it as a smart bookmark manager that AI agents can use.

**Key Features:**
- 📋 **Metadata only**: URLs, summaries, tags—no content storage
- 🔧 **CLI + Skill**: Full document management via command line and Claude Code skill
- ⚡ **Zero setup**: No databases, no Docker, no external services
- 📝 **Git-friendly**: Human-readable YAML diffs
- 🔍 **Searchable**: Multiple search modes (simple, keyword, semantic, hybrid)
- 🏷️ **Taggable**: Organize with custom tags
- 🚀 **Portable**: Copy `.asta/` folder anywhere
- 💾 **Smart caching**: Automatic content caching with SHA256 verification

## Installation

**Prerequisites**: Python 3.10+ and [uv](https://docs.astral.sh/uv/) package manager

**Install with uv:**

```bash
uv tool install git+https://github.com/allenai/asta-resource-repo.git
```

This installs the `asta-documents` CLI globally.

## Skill Installation

The [asta-documents](skills/asta-documents/SKILL.md) skill provides agent instructions for using the `asta-documents` CLI.

**Claude Code:**
```bash
curl -o ~/.claude/skills/asta-documents.md https://raw.githubusercontent.com/allenai/asta-resource-repo/main/skills/asta-documents/SKILL.md
```

**skills.sh:**
```bash
npx skills add add allenai/asta-resource-repo/skills
```
## Command Line Usage

After installation, use the `asta-documents` CLI:

### Add a Document

```bash
asta-documents add https://arxiv.org/pdf/1706.03762.pdf \
  --name="Attention Is All You Need" \
  --summary="Seminal paper on Transformer architecture" \
  --tags="ai,nlp,transformers" \
  --mime-type="application/pdf" \
  --extra='{"author": "Vaswani et al", "year": 2017}'
```

### List Documents

```bash
# List all
asta-documents list

# Filter by tags
asta-documents list --tags="ai,research"

# Verbose output
asta-documents list -v

# JSON output (for scripts)
asta-documents list --json
```

### Search Documents

```bash
asta-documents search "transformer architecture"

The `--mode` option allows you to choose the search method. See `--help` for details.
```

### Get Document Details

```bash
asta-documents get asta://{namespace}/{uuid}
```

### Update Document Metadata

```bash
# Update single field
asta-documents update asta://{namespace}/{uuid} \
  --name="Updated Title"

# Update multiple fields
asta-documents update asta://{namespace}/{uuid} \
  --name="New Title" \
  --summary="Updated summary" \
  --tags="revised,updated"

# Update with JSON output
asta-documents --json update asta://{namespace}/{uuid} \
  --tags="new,tags"
```

**Available update fields:**
- `--name` - Document title
- `--url` - Document URL
- `--summary` - Text description
- `--mime-type` - MIME type
- `--tags` - Tags (replaces existing)
- `--extra` - Extra metadata JSON (replaces existing)

### Remove Document

```bash
asta-documents remove asta://{namespace}/{uuid}
```

### Show Index Stats

```bash
asta-documents show
```

## How It Works

### Index File

All metadata is stored in `.asta/documents/index.yaml`, in the current directory.
This file can be copied and shared across projects. The structure is simple YAML:

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

Document URIs are of the form `asta://{namespace}/{uuid}`. The `namespace` 
points to the location of the `index.yaml file`. If the current directory is part of a
local git workspace, the `namespace` will be the repo id, i.e. `{owner}/{repo}`. 
Outside of a git context, the `namespace` is a pointer to the local filesystem.
Thus, `asta://` URLs are shareable only so long as the index file is checked into git.

**In a git repository:**
- Format: `asta://{owner}/{repo}/{uuid}`
- Example: `asta://allenai/asta-resource-repo/550e8400-...`
- URIs are **persistent and shareable** across all team members and branches
- URIs remain valid when merging between branches (no branch in namespace)

**Outside git (or no remote configured):**
- Format: `asta://local:{absolute_path}/{uuid}`
- Example: `asta://local:/Users/you/project/.asta/documents/index.yaml/550e8400-...`
- URIs are local-only and not shareable

### Git Tracking Behavior

**Tracked index files** (recommended for teams):
```bash
# Add to git for team sharing
git add .asta/documents/index.yaml
git commit -m "Add research papers to index"
git push
```

When your team pulls the changes, they'll have:
- ✅ Same namespace (same URIs work for everyone on all branches)
- ✅ Same document metadata
- ✅ Git-readable diffs when documents change
- ✅ URIs work after merging between branches

**Untracked index files** (personal use):
- The `.gitignore` allows `.asta/documents/index.yaml` but ignores other `.asta/` files
- If not committed, the index is local-only to your machine
- URIs still use git-based namespaces but aren't portable across machines
- Useful for personal bookmarks you don't want to share

### Document Structure

Each document has:

**Required:**
- `url` - Where the document lives (supported protocols: `http://`, `https://`, `file://`)
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

1. **Small and fast**: No large files in git, quick search
2. **No copyright issues**: Content stays local. Metadata is fair use.
3. **Portable**: Works with any URL-accessible content
4. **Flexible**: Content can move, metadata stays stable
5. **Git-friendly**: Track changes in readable YAML diffs

## Use Cases

### Research Management

Track papers, articles, and preprints:
```bash
asta-documents add https://arxiv.org/pdf/2304.08485.pdf \
  --name="LLaMA: Open Foundation Models" \
  --summary="Meta's open source LLM" \
  --tags="ai,llm,research" \
  --extra='{"venue": "arXiv", "year": 2023}'
```

### Bookmark Management

Organize web resources:
```bash
asta-documents add https://modelcontextprotocol.io/ \
  --name="Model Context Protocol" \
  --summary="MCP documentation and guides" \
  --tags="mcp,documentation,reference"
```

### Project Documentation

Index project-related documents:
```bash
asta-documents add https://github.com/user/repo/blob/main/DESIGN.md \
  --name="Project Design Doc" \
  --summary="Architecture and design decisions" \
  --tags="internal,design,architecture"
```

### Team Collaboration

Commit `.asta/documents/index.yaml` to git to share with your team:
```bash
git add .asta/documents/index.yaml
git commit -m "Add ML papers to research index"
git push
```

## Troubleshooting

### "Command not found: uv"

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Index File Not Found

The index file is created automatically on first use. If missing:
```bash
mkdir -p .asta
asta-documents show  # Creates empty index
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

- **Asta-Documents Skill**: [skills/asta-documents/SKILL.md](skills/asta-documents/SKILL.md)
- **Development Guide**: [CLAUDE.md](CLAUDE.md)
- **Beads Issue Tracker**: https://github.com/steveyegge/beads

## License

MIT License
