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
from pathlib import Path
from typing import Optional

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class DocumentChatbot:
    """Interactive chatbot with MCP document tools and Claude API"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the chatbot

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            print("Warning: No ANTHROPIC_API_KEY found. Chat features will be limited.")

        self.client = (
            anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        )
        self.session: Optional[ClientSession] = None
        self.available_tools = []

    async def list_documents(self) -> list:
        """List all documents"""
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        result = await self.session.call_tool("list_documents", {})
        return json.loads(result.content[0].text) if result.content else []

    async def search_documents(self, query: str, limit: int = 10) -> list:
        """Search documents"""
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        result = await self.session.call_tool(
            "search_documents", {"query": query, "limit": limit}
        )
        return json.loads(result.content[0].text) if result.content else []

    async def get_document(self, document_uri: str) -> Optional[dict]:
        """Get a specific document"""
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        result = await self.session.call_tool(
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
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

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
        result = await self.session.call_tool(
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
                model="claude-3-5-sonnet-20241022",
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

                        # Call the MCP tool
                        result = await self.session.call_tool(block.name, block.input)
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
                    model="claude-3-5-sonnet-20241022",
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

    async def run(self):
        """Run the interactive chatbot loop"""
        print("=" * 70)
        print("📚 Document Chatbot with MCP Tools")
        print("=" * 70)
        print("🔌 Connecting to MCP server...")

        # Configure the MCP server to connect to
        # Use the dedicated MCP-only server for stdio mode
        import os

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        server_params = StdioServerParameters(
            command="uv", args=["run", "asta-resources-mcp"], env=env
        )

        # Run the chatbot within the MCP client context
        import sys
        import asyncio

        print("🔄 Creating stdio client...", file=sys.stderr)
        async with stdio_client(server_params, errlog=sys.stderr) as (read, write):
            print("✅ Stdio client created", file=sys.stderr)
            print(f"   Read stream: {type(read)}", file=sys.stderr)
            print(f"   Write stream: {type(write)}", file=sys.stderr)

            # Create session as async context manager
            print("🔄 Creating MCP session...", file=sys.stderr)
            async with ClientSession(read, write) as session:
                self.session = session
                print("✅ MCP session created", file=sys.stderr)

                print(
                    "🔄 Initializing MCP session (this may take a moment)...",
                    file=sys.stderr,
                )
                # Initialize the connection with timeout
                try:
                    # Add a timeout to see if it's truly hanging or just slow
                    await asyncio.wait_for(session.initialize(), timeout=10.0)
                    print("✅ MCP session initialized!", file=sys.stderr)
                except asyncio.TimeoutError:
                    print(
                        "❌ Initialization timed out after 10 seconds", file=sys.stderr
                    )
                    print(
                        "   This suggests the server isn't responding to the initialize request",
                        file=sys.stderr,
                    )
                    raise
                except Exception as e:
                    print(
                        f"❌ Failed to initialize: {type(e).__name__}: {e}",
                        file=sys.stderr,
                    )
                    import traceback

                    traceback.print_exc(file=sys.stderr)
                    raise

                # List available tools
                tools_result = await session.list_tools()
                self.available_tools = tools_result.tools

                print(f"✅ Connected! Found {len(self.available_tools)} tools:")
                for tool in self.available_tools:
                    print(f"   • {tool.name}: {tool.description}")
                print()

                # Show help
                self.print_help()

                # Main loop
                while True:
                    try:
                        # Get user input
                        user_input = input("\n💬 You: ").strip()

                        if not user_input:
                            continue

                        # Handle the command/message
                        response = await self.handle_command(user_input)

                        # Check for quit
                        if response == "__QUIT__":
                            print("\n👋 Goodbye!")
                            break

                        # Display response
                        if response:
                            print(f"\n🤖 Assistant: {response}")

                    except KeyboardInterrupt:
                        print("\n\n👋 Goodbye!")
                        break
                    except Exception as e:
                        print(f"\n❌ Error: {e}")
                        import traceback

                        traceback.print_exc()


async def async_main():
    """Async main entry point"""
    chatbot = DocumentChatbot()
    await chatbot.run()


def main():
    """Sync wrapper for setuptools entry point"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
