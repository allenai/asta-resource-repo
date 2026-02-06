# Document Chatbot - Local Testing Tool

A simple command-line chatbot for testing your MCP document metadata index locally. This chatbot provides an interactive interface to manage document metadata and optionally chat with Claude about them.

## Features

- 🔌 **MCP Integration**: Connects directly to your MCP server via stdio
- 📚 **Document Metadata Management**: Add, search, list, and retrieve document metadata
- 🤖 **Claude Integration** (optional): Natural language chat with tool use
- 💻 **Interactive CLI**: Simple command-based interface

**Note**: This tool manages document **metadata only** (URLs, summaries, tags). It does not store or upload document content.

## Installation

The chatbot is included with the package:

```bash
uv pip install -e .
```

This installs all required dependencies including `anthropic` and `mcp`.

## Usage

### Basic Usage (Without Claude API)

Run the chatbot without an API key to use direct commands:

```bash
# Recommended: use the installed script
uv run asta-chatbot

# Or run directly
python chatbot.py
```

Available commands:
- `/help` - Show help message
- `/list` - List all documents
- `/search <query>` - Search for documents
- `/get <uri>` - Get document metadata by URI
- `/add <url>` - Add document metadata to index
- `/quit` - Exit

### Advanced Usage (With Claude API)

Set your Anthropic API key to enable natural language chat:

```bash
export ANTHROPIC_API_KEY=your_api_key_here
uv run asta-chatbot
```

Now you can chat naturally:
```
💬 You: Find all documents about Python
🤖 Assistant: [Claude will use the search tool and respond]

💬 You: Add a document at https://example.com/report.pdf
🤖 Assistant: [Claude will use the add_document tool]
```

## Example Session

```
==================================================================
📚 Document Chatbot with MCP Tools
==================================================================
🔌 Connecting to MCP server...
✅ Connected! Found 4 tools:
   • search_documents: Search documents by query
   • get_document: Get document metadata by URI
   • list_documents: List all documents in the index
   • add_document: Add document metadata to the index

📚 Document Chatbot Commands:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /help              Show this help message
  /list              List all documents
  /search <query>    Search documents (e.g., /search python)
  /get <uri>         Get document metadata by URI
  /add <url>         Add document metadata (e.g., /add https://example.com/doc.pdf)
  /quit              Exit the chatbot

  Or just type naturally to chat with Claude about documents!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 You: /add https://example.com/sample.pdf
🤖 Assistant: ✅ Added document metadata
   URI: asta://local-index/document/abc123...

💬 You: /search python
🤖 Assistant: 🔍 Found 2 result(s) for 'python':
  • sample.txt (score: 0.85)
    URI: asta://local/abc123...
    ...Python programming guide...

💬 You: /quit
👋 Goodbye!
```

## How It Works

1. **MCP Connection**: The chatbot spawns your MCP server as a subprocess and communicates via stdio
2. **Tool Discovery**: Lists available tools from the MCP server
3. **Command Processing**: Parses user commands and calls appropriate MCP tools
4. **Claude Integration** (optional): When an API key is present, natural language input is sent to Claude with tool definitions, allowing Claude to decide which tools to call
5. **Metadata-Only**: Manages document metadata (URLs, summaries, tags) stored in `.asta/index.yaml` without storing actual document content

## Architecture

```
┌─────────────┐
│   User      │
│  (Terminal) │
└──────┬──────┘
       │
       v
┌──────────────────────────┐
│  chatbot.py              │
│  - Command parsing       │
│  - Claude API client     │
│  - MCP client (stdio)    │
└──────┬───────────────────┘
       │
       v
┌──────────────────────────┐
│  MCP Server (subprocess) │
│  - Document tools        │
│  - YAML index backend    │
└──────────────────────────┘
```

## Troubleshooting

### "Not connected to MCP server"
Make sure your server is properly installed:
```bash
uv pip install -e .
```

### "Claude API not available"
Either:
1. Use direct commands (`/list`, `/search`, etc.) without Claude
2. Set `ANTHROPIC_API_KEY` environment variable for natural language chat

### "Module not found: anthropic"
Install dependencies:
```bash
uv pip install anthropic mcp
```

## Extending the Chatbot

You can extend the chatbot by:

1. **Adding new commands**: Add new command handlers in `handle_command()`
2. **Custom prompts**: Modify the Claude system prompt for better responses
3. **Rich output**: Use libraries like `rich` for colored terminal output
4. **History**: Add conversation history tracking
5. **Config file**: Support for configuration files with default settings

## License

Same as the parent project (MIT).
