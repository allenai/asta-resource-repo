# Installation Guide

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/allenai/asta-resource-repo/main/install.sh | bash
```

That's it! The installer handles everything automatically.

## What the Installer Does

1. ✅ Checks for and installs [uv](https://docs.astral.sh/uv/) package manager if needed
2. ✅ Verifies Python 3.10+ is installed
3. ✅ Clones repository to `~/.asta-resources`
4. ✅ Installs all dependencies
5. ✅ Tests the installation
6. ✅ Shows next steps and MCP configuration

## Installation Location

**Default**: `~/.asta-resources`

**Custom location**: Set `ASTA_INSTALL_DIR` environment variable:
```bash
ASTA_INSTALL_DIR=~/my-custom-path curl -fsSL https://raw.githubusercontent.com/allenai/asta-resource-repo/main/install.sh | bash
```

## After Installation

### Test the CLI

```bash
cd ~/.asta-resources
uv run asta-index --help
```

### Add Your First Document

```bash
cd ~/.asta-resources
uv run asta-index add https://example.com/doc.pdf \
  --name="My First Document" \
  --summary="A test document" \
  --tags="example,test"
```

### Configure for Claude Code

1. Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
2. Select "MCP: Edit Configuration"
3. Add this configuration (replace with your install path):

```json
{
  "mcpServers": {
    "asta-resources": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/YOUR_USERNAME/.asta-resources",
        "asta-resources-mcp"
      ]
    }
  }
}
```

4. Reload MCP servers: `Cmd+Shift+P` → "MCP: Reload Servers"

**Full MCP setup guide**: [MCP_SETUP.md](MCP_SETUP.md)

### Configure for Claude Desktop

**macOS**: Edit `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: Edit `%APPDATA%\Claude\claude_desktop_config.json`

**Linux**: Edit `~/.config/Claude/claude_desktop_config.json`

Add the same configuration as above, then restart Claude Desktop.

## Manual Installation

If you prefer to install manually:

```bash
# Clone repository
git clone https://github.com/allenai/asta-resource-repo.git
cd asta-resource-repo

# Install dependencies
uv sync

# Test
uv run asta-index --help
```

## Updating

To update to the latest version:

```bash
cd ~/.asta-resources
git pull
uv sync
```

Or run the installer again (it will detect the existing installation and offer to update).

## Uninstalling

```bash
# Remove installation directory
rm -rf ~/.asta-resources

# Remove MCP configuration from Claude Code/Desktop config file
# (Edit the JSON file to remove the "asta-resources" entry)
```

## Troubleshooting

### "curl: command not found"

Install curl:
- **macOS**: `brew install curl` (or use built-in)
- **Ubuntu/Debian**: `sudo apt-get install curl`
- **Fedora**: `sudo dnf install curl`

### "Python 3.10+ required"

Install Python:
- **macOS**: `brew install python@3.11`
- **Ubuntu/Debian**: `sudo apt-get install python3.11`
- **Windows**: Download from [python.org](https://www.python.org/downloads/)

### "uv: command not found" after install

The installer installs uv, but you may need to:
1. Restart your terminal
2. Or manually source: `source $HOME/.cargo/env`

### Permission denied

If you get permission errors during installation:

```bash
# Install to a directory you own
ASTA_INSTALL_DIR=~/asta-resources curl -fsSL https://raw.githubusercontent.com/allenai/asta-resource-repo/main/install.sh | bash
```

### Installation test failed

This is usually harmless. Verify manually:

```bash
cd ~/.asta-resources
uv run asta-index --help
```

If this works, the installation is successful despite the test warning.

## Support

- **Documentation**: [README.md](README.md)
- **MCP Setup**: [MCP_SETUP.md](MCP_SETUP.md)
- **Issues**: [GitHub Issues](https://github.com/allenai/asta-resource-repo/issues)
