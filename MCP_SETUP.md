# MCP Server Setup Guide

Complete setup instructions for configuring the Asta Resource Repository MCP server with Claude Code or Claude Desktop.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager (installed automatically by install script)
- Claude Code or Claude Desktop installed

## Installation

### Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/allenai/asta-resource-repo/main/install.sh | bash
```

The installer will:
- Install uv if not present
- Clone to `~/.asta-resources`
- Install dependencies
- Show configuration instructions

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/allenai/asta-resource-repo.git
cd asta-resource-repo

# Install dependencies
uv sync
```

## Configuration for Claude Code

### Step 1: Open MCP Configuration

In Claude Code:
1. Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
2. Type "MCP" and select **"MCP: Edit Configuration"**

### Step 2: Add Server Configuration

Add this configuration to the `mcpServers` section:

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/rodneyk/workspace/asta-resource-repo",
        "asta-resources-mcp"
      ]
    }
  }
}
```

**Important**: Replace `/Users/rodneyk/workspace/asta-resource-repo` with your actual repository path.

### Step 3: Reload MCP Servers

- Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
- Type "MCP" and select **"MCP: Reload Servers"**

Or simply restart Claude Code.

## Configuration for Claude Desktop

### Step 1: Locate Configuration File

The configuration file is at:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Step 2: Edit Configuration

Open the file and add the server configuration:

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/rodneyk/workspace/asta-resource-repo",
        "asta-resources-mcp"
      ]
    }
  }
}
```

**Important**: Replace `/Users/rodneyk/workspace/asta-resource-repo` with your actual repository path.

### Step 3: Restart Claude Desktop

Quit and restart Claude Desktop for the changes to take effect.

## Verification

Once configured, you should see these MCP tools available:

- **add_document** - Add document metadata to the index
- **get_document** - Retrieve metadata by URI
- **list_documents** - List all documents
- **search_documents** - Search documents by query

### Test the Installation

Try these commands:

**Add a document:**
```
Add a document at https://arxiv.org/pdf/1706.03762.pdf
with name "Attention Is All You Need"
and summary "Transformer architecture paper"
and tags "ai,research,transformers"
```

**List documents:**
```
List all documents in my index
```

**Search:**
```
Search for documents about transformers
```

## Where Data is Stored

The document metadata index is stored at:
```
<repository-path>/.asta/index.yaml
```

This file is:
- Human-readable YAML
- Git-friendly (commit it to track your document collection)
- Portable (copy `.asta/` folder anywhere)

You can view it directly:
```bash
cat .asta/index.yaml
```

Or use the CLI:
```bash
cd /Users/rodneyk/workspace/asta-resource-repo
uv run asta-index list
uv run asta-index show
```

## Troubleshooting

### Server Not Appearing in Claude

1. Check the configuration file path is correct
2. Verify `uv` is installed: `uv --version`
3. Check repository path in configuration is absolute, not relative
4. Restart Claude Code/Desktop after configuration changes
5. Check Claude logs for error messages

### "Command not found: uv"

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then restart your terminal and Claude.

### MCP Server Fails to Start

Test the server manually:
```bash
cd /Users/rodneyk/workspace/asta-resource-repo
uv run asta-resources-mcp
```

If this fails, check:
- Dependencies are installed: `uv sync`
- Python version is 3.10+: `python --version`
- No syntax errors in code

### Permission Denied Errors

Ensure the `.asta/` directory is writable:
```bash
mkdir -p .asta
chmod 755 .asta
```

## Advanced Configuration

### Custom Index Location

Override the default index path:

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/rodneyk/workspace/asta-resource-repo",
        "asta-resources-mcp"
      ],
      "env": {
        "INDEX_PATH": "/path/to/custom/index.yaml"
      }
    }
  }
}
```

### Custom Namespace

Change the URI namespace:

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/rodneyk/workspace/asta-resource-repo",
        "asta-resources-mcp"
      ],
      "env": {
        "NAMESPACE": "my-docs"
      }
    }
  }
}
```

Documents will use URIs like: `asta://my-docs/document/UUID`

## Multiple Index Instances

You can run multiple instances with different index files:

```json
{
  "mcpServers": {
    "asta-research": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/rodneyk/workspace/asta-resource-repo",
        "asta-resources-mcp"
      ],
      "env": {
        "INDEX_PATH": "/Users/rodneyk/Documents/research-index.yaml",
        "NAMESPACE": "research"
      }
    },
    "asta-work": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/rodneyk/workspace/asta-resource-repo",
        "asta-resources-mcp"
      ],
      "env": {
        "INDEX_PATH": "/Users/rodneyk/Documents/work-index.yaml",
        "NAMESPACE": "work"
      }
    }
  }
}
```

## Next Steps

- See [README.md](README.md) for usage examples
- See [CLAUDE.md](CLAUDE.md) for development documentation
- See [BEADS.md](BEADS.md) for contributing with Beads
