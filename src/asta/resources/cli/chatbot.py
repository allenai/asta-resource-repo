#!/usr/bin/env python3
"""
Simple command-line chatbot for testing MCP document tools locally.

This chatbot provides an interactive interface to:
- Upload documents
- Search documents
- List documents
- Get document details
- Chat with Claude about documents

Usage:
    python chatbot.py
"""

import asyncio
import base64
import json
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class ServerConfig:
    """Configuration for an MCP server connection

    Attributes:
        name: Unique identifier for this server
        command: Command to execute (e.g., "sh", "uv")
        args: Arguments to pass to the command
        env: Environment variables to set (optional)
    """
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None


class DevChatbot:
    """Basic CLI chatbot for local testint"""

    def __init__(self, api_key: Optional[str] = None, server_configs: Optional[List[ServerConfig]] = None):
        """Initialize the chatbot

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            server_configs: List of MCP server configurations to connect to
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        self.client = (
            anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        )

        # Multiple server support
        self.server_configs = server_configs or []
        self.sessions: Dict[str, ClientSession] = {}  # server_name -> session
        self.tool_to_server: Dict[str, str] = {}  # tool_name -> server_name
        self.available_tools = []  # All tools from all servers

    def _get_session_for_tool(self, tool_name: str) -> Optional[ClientSession]:
        """Get the session for a specific tool

        Args:
            tool_name: Name of the tool

        Returns:
            The ClientSession that provides this tool, or None if not found
        """
        server_name = self.tool_to_server.get(tool_name)
        if not server_name:
            return None
        return self.sessions.get(server_name)

    async def list_documents(self) -> list:
        """List all documents"""
        session = self._get_session_for_tool("list_documents")
        if not session:
            raise RuntimeError("list_documents tool not available on any server")

        result = await session.call_tool("list_documents", {})
        return json.loads(result.content[0].text) if result.content else []

    async def search_documents(self, query: str, limit: int = 10) -> list:
        """Search documents"""
        session = self._get_session_for_tool("search_documents")
        if not session:
            raise RuntimeError("search_documents tool not available on any server")

        result = await session.call_tool(
            "search_documents", {"query": query, "limit": limit}
        )
        return json.loads(result.content[0].text) if result.content else []

    async def get_document(self, document_uri: str) -> Optional[dict]:
        """Get a specific document"""
        session = self._get_session_for_tool("get_document")
        if not session:
            raise RuntimeError("get_document tool not available on any server")

        result = await session.call_tool(
            "get_document", {"document_uri": document_uri}
        )
        return json.loads(result.content[0].text) if result.content else None

    async def upload_document(
        self,
        filepath: str,
        mime_type: Optional[str] = None,
        extra_metadata: Optional[dict] = None,
    ) -> dict:
        """Upload a document"""
        session = self._get_session_for_tool("upload_document")
        if not session:
            raise RuntimeError("upload_document tool not available on any server")

        # Read the file
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        # Detect MIME type if not provided
        if not mime_type:
            ext = path.suffix.lower()
            mime_types = {
                ".txt": "text/plain",
                ".json": "application/json",
                ".pdf": "application/pdf",
            }
            mime_type = mime_types.get(ext, "application/octet-stream")

        # Read content and encode if binary
        if mime_type.startswith("text/") or mime_type == "application/json":
            content = path.read_text()
        else:
            content_bytes = path.read_bytes()
            content = base64.b64encode(content_bytes).decode("ascii")

        # Upload
        result = await session.call_tool(
            "upload_document",
            {
                "content": content,
                "filename": path.name,
                "mime_type": mime_type,
                "extra_metadata": extra_metadata or {},
            },
        )
        return json.loads(result.content[0].text) if result.content else {}

    def print_help(self):
        """Print help message"""
        print(
            """
📚 Document Chatbot Commands:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /help              Show this help message
  /servers           Show connected MCP servers
  /list              List all documents
  /search <query>    Search documents (e.g., /search python)
  /get <uri>         Get document by URI
  /upload <path>     Upload a document (e.g., /upload data/test.pdf)
  /quit              Exit the chatbot

  Or just type naturally to chat with Claude about documents!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        )

    async def handle_command(self, user_input: str) -> str:
        """Handle user commands

        Returns:
            Response string to display to user
        """
        user_input = user_input.strip()

        # Handle commands
        if user_input == "/help":
            self.print_help()
            return ""

        elif user_input == "/servers":
            if not self.sessions:
                return "📭 No MCP servers connected."

            response = f"🔌 Connected to {len(self.sessions)} MCP server(s):\n"
            for server_name, session in self.sessions.items():
                # Count tools for this server
                tool_count = sum(1 for tool_name, srv in self.tool_to_server.items() if srv == server_name)
                response += f"\n  • {server_name}"
                response += f"\n    Tools: {tool_count}"

            response += f"\n\nTotal tools available: {len(self.available_tools)}"
            return response

        elif user_input == "/list":
            docs = await self.list_documents()
            if not docs:
                return "📭 No documents found."

            response = f"📚 Found {len(docs)} document(s):\n"
            for doc in docs:
                response += f"\n  • {doc['name']}"
                response += f"\n    URI: {doc['uri']}"
                response += f"\n    Type: {doc['mime_type']}"
                if doc.get("extra"):
                    response += f"\n    Metadata: {json.dumps(doc['extra'])}"
            return response

        elif user_input.startswith("/search "):
            query = user_input[8:].strip()
            if not query:
                return "❌ Please provide a search query. Usage: /search <query>"

            results = await self.search_documents(query)
            if not results:
                return f"🔍 No results found for '{query}'"

            response = f"🔍 Found {len(results)} result(s) for '{query}':\n"
            for hit in results:
                doc = hit["document"]
                response += f"\n  • {doc['name']} (score: {hit.get('score', 'N/A')})"
                response += f"\n    URI: {doc['uri']}"
                if hit.get("snippet"):
                    response += f"\n    ...{hit['snippet']}..."
            return response

        elif user_input.startswith("/get "):
            uri = user_input[5:].strip()
            if not uri:
                return "❌ Please provide a document URI. Usage: /get <uri>"

            doc = await self.get_document(uri)
            if not doc:
                return f"❌ Document not found: {uri}"

            response = f"📄 Document: {doc['metadata']['name']}\n"
            response += f"   URI: {doc['metadata']['uri']}\n"
            response += f"   Type: {doc['metadata']['mime_type']}\n"
            response += f"   Size: {doc['metadata'].get('size_bytes', 0)} bytes\n"

            # Show content preview for text files
            if doc["metadata"]["mime_type"].startswith("text/"):
                content = doc["content"][:500]
                response += f"\n   Content preview:\n   {content}\n"
                if len(doc["content"]) > 500:
                    response += "   ...(truncated)"

            return response

        elif user_input.startswith("/upload "):
            filepath = user_input[8:].strip()
            if not filepath:
                return "❌ Please provide a file path. Usage: /upload <path>"

            try:
                result = await self.upload_document(filepath)
                return f"✅ Uploaded: {result['name']}\n   URI: {result['uri']}"
            except FileNotFoundError as e:
                return f"❌ {e}"
            except Exception as e:
                return f"❌ Upload failed: {e}"

        elif user_input in ["/quit", "/exit"]:
            return "__QUIT__"

        # If not a command and we have Claude API, send to Claude
        elif self.client:
            return await self.chat_with_claude(user_input)

        else:
            return "💡 No API key configured. Use /help to see available commands."

    async def chat_with_claude(self, message: str) -> str:
        """Send a message to Claude and get a response

        Args:
            message: User's message

        Returns:
            Claude's response
        """
        if not self.client:
            return "❌ Claude API not available (no API key)"

        try:
            # Get available tools from MCP
            tools = []
            for tool in self.available_tools:
                tool_def = {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                tools.append(tool_def)

            # Call Claude with tools
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                tools=tools,
                messages=[{"role": "user", "content": message}],
            )

            # Handle tool calls
            while response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        print(f"🔧 Using tool: {block.name}")

                        # Get the appropriate session for this tool
                        session = self._get_session_for_tool(block.name)
                        if not session:
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"Error: Tool {block.name} not available on any server",
                                }
                            )
                            continue

                        # Call the MCP tool
                        result = await session.call_tool(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": (
                                    result.content[0].text
                                    if result.content
                                    else "No result"
                                ),
                            }
                        )

                # Continue the conversation with tool results
                messages = [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": tool_results},
                ]

                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    tools=tools,
                    messages=messages,
                )

            # Extract text response
            text_blocks = [
                block.text for block in response.content if hasattr(block, "text")
            ]
            return "\n".join(text_blocks) if text_blocks else "No response"

        except Exception as e:
            return f"❌ Error calling Claude: {e}"

    async def _connect_to_server(self, config: ServerConfig, exit_stack: AsyncExitStack) -> None:
        """Connect to an MCP server and register its tools

        Args:
            config: Server configuration
            exit_stack: AsyncExitStack to manage the connection lifecycle
        """
        # Create server parameters
        server_env = os.environ.copy()
        server_env["PYTHONUNBUFFERED"] = "1"
        server_env["FASTMCP_LOG_LEVEL"] = "WARNING"

        # Add any custom environment variables from config
        if config.env:
            server_env.update(config.env)

        server_params = StdioServerParameters(
            command="sh",
            args=["-c", f"{config.command} {' '.join(config.args)} 2>/dev/null"],
            env=server_env
        )

        print(f"🔌 Connecting to {config.name}...")

        # Connect to the server
        read, write = await exit_stack.enter_async_context(stdio_client(server_params))
        session = await exit_stack.enter_async_context(ClientSession(read, write))

        # Initialize the connection with timeout
        try:
            await asyncio.wait_for(session.initialize(), timeout=10.0)
        except asyncio.TimeoutError:
            print(f"❌ Timeout connecting to {config.name}")
            raise
        except Exception as e:
            print(f"❌ Error connecting to {config.name}: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
            raise

        # Store the session
        self.sessions[config.name] = session

        # List available tools and register them
        tools_result = await session.list_tools()
        for tool in tools_result.tools:
            self.tool_to_server[tool.name] = config.name
            self.available_tools.append(tool)

        print(f"✅ Connected to {config.name} ({len(tools_result.tools)} tools)")

    async def run(self):
        """Run the interactive chatbot loop with multiple MCP servers"""
        # Use default config if none provided
        if not self.server_configs:
            # Default to the asta-resources MCP server
            env = os.environ.copy()
            self.server_configs = [
                ServerConfig(
                    name="asta-resources",
                    command="uv",
                    args=["run", "asta-resources-mcp"],
                    env={"PYTHONUNBUFFERED": "1", "FASTMCP_LOG_LEVEL": "WARNING"}
                ),
                ServerConfig(
                    name="asta-paper-finder",
                    command="uv",
                    args=["run", "--directory", "/Users/rodneyk/workspace/nora/mcp", "paper_finder_server.py"],
                )
            ]

        # Connect to all servers using AsyncExitStack
        async with AsyncExitStack() as exit_stack:
            # Connect to all configured servers
            for config in self.server_configs:
                try:
                    await self._connect_to_server(config, exit_stack)
                except Exception as e:
                    print(f"⚠️  Failed to connect to {config.name}: {e}")
                    # Continue with other servers

            # Check if we have any active sessions
            if not self.sessions:
                print("❌ No MCP servers connected. Exiting.")
                return

            print(f"\n🎉 Ready! Connected to {len(self.sessions)} server(s) with {len(self.available_tools)} tool(s) total.\n")

            # Main loop
            while True:
                try:
                    # Get user input
                    try:
                        user_input = input("\n💬 You: ").strip()
                    except EOFError:
                        break

                    # Handle the command/message
                    response = await self.handle_command(user_input)

                    # Check for quit
                    if response == "__QUIT__":
                        print("\n👋 Goodbye!")
                        break

                    # Display response
                    if response:
                        print(f"\n🤖 Asta: {response}")

                except KeyboardInterrupt:
                    print("\n\n👋 Goodbye!")
                    break
                except Exception as e:
                    print(f"\n❌ Error: {e}")
                    import traceback
                    traceback.print_exc()


async def async_main():
    """Async main entry point"""
    chatbot = DevChatbot()
    await chatbot.run()


def main():
    """Sync wrapper for setuptools entry point"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
