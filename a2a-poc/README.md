# A2A Protocol Proof of Concept

A Python implementation for prototyping interaction between Asta agents using the official Agent-to-Agent (A2A) protocol SDK.

## Overview

This POC implements two HTTP-based A2A agents:

- **Handler Agent** (port 9000): Stateful agent that manages conversation history and artifacts
- **Subagent** (port 9001): Stateless agent that processes tasks and returns results with artifacts

### Core Workflow

1. User sends request to Handler agent
2. Handler builds context from conversation history
   - May optionally attach hydrated artifacts referenced by past messages
3. Handler forwards request to Subagent via HTTP/JSON-RPC
4. Subagent processes request and returns response
   - Response may include attached artifacts as hydrated data (not URL references)
5. Handler generates response message
   - Persists any attached artifacts in the artifact store
   - Stores response message in conversation history
   - Attaches artifact references (not hydrated data) in the response message

## Installation

This project uses `uv` for dependency management.

```bash
# Install dependencies
uv sync

# Or install with dev dependencies
uv sync --dev
```

## Manual Testing

### Starting the Servers

You need to run both agents in separate terminals:

**Terminal 1 - Start Subagent:**
```bash
uv run python examples/run_subagent.py
```

You should see:
```
Starting Subagent A2A server on 0.0.0.0:9001
Agent card available at: http://localhost:9001/.well-known/agent-card.json
```

**Terminal 2 - Start Handler:**
```bash
uv run python examples/run_handler.py
```

You should see:
```
Starting Handler A2A server on 0.0.0.0:9000
Agent card available at: http://localhost:9000/.well-known/agent-card.json
Subagent URL: http://localhost:9001
```

### Running the Test Client

**Terminal 3 - Run Test Client:**
```bash
uv run python examples/test_client.py
```

This will:
1. Fetch the Handler's agent card
2. Send three test messages to the Handler
3. Display the responses

Expected output:
```
=== A2A Handler Test Client ===

Fetching Handler agent card...
Agent: Asta Handler
Description: Handler agent that manages conversations, artifacts, and delegates to subagent
Version: 1.0.0
Skills: ['Handle User Request']

Message 1: Hello! Can you help me process some data?
Response: Subagent processed: Context: 0 previous messages

Current request: Hello! Can you help me process some data?
RPC ID: <uuid>
...
```

### Testing with curl

You can also test the agents directly with curl:

**Check Agent Card:**
```bash
curl http://localhost:9000/.well-known/agent-card.json | python3 -m json.tool
```

**Send a Message (JSON-RPC):**
```bash
curl -X POST http://localhost:9000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "test-123",
        "role": "user",
        "parts": [{"kind": "text", "text": "Hello from curl!"}]
      }
    },
    "id": "request-1"
  }' | python3 -m json.tool
```

### Verifying the Workflow

To verify the complete workflow:

1. **Check logs** - Both servers log all requests and responses
2. **Multiple messages** - Send several messages to see conversation history building
3. **Artifacts** - The Subagent creates sample artifacts that the Handler persists
4. **Error handling** - Try invalid requests to test error responses

## Architecture

### A2A Protocol

The agents communicate using the official A2A protocol via JSON-RPC over HTTP:

- **Method**: `message/send`
- **Transport**: HTTP POST to `/`
- **Format**: JSON-RPC 2.0
- **Agent Cards**: Available at `/.well-known/agent-card.json`

### Storage Layer

The project defines interfaces for pluggable storage:

- **`IArtifactStore`**: Interface for artifact persistence
  - `store(artifact)`: Save artifact and return ID
  - `get(artifact_id)`: Retrieve artifact by ID
  - `delete(artifact_id)`: Remove artifact
  - `list_all()`: List all artifacts

- **`IConversationHistory`**: Interface for message history
  - `add_message(message)`: Append message to history
  - `get_messages(limit)`: Retrieve recent messages
  - `get_message_by_id(id)`: Get specific message
  - `clear()`: Clear all history

In-memory implementations are provided for testing:
- `InMemoryArtifactStore`
- `InMemoryConversationHistory`

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_storage.py -v
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .
```

## Resources

- **A2A Protocol**: https://a2a-protocol.org
- **Python SDK**: https://github.com/a2aproject/a2a-python
- **Samples**: https://github.com/a2aproject/a2a-samples
- **PyPI**: https://pypi.org/project/a2a-sdk/
