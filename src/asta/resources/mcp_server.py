#!/usr/bin/env python3
"""
MCP-only server for stdio transport.
This is the dedicated MCP server without REST API components.
"""

import logging
import os

# Configure logging BEFORE importing FastMCP to suppress its banner and logs
logging.basicConfig(level=logging.WARN, force=True)
logging.getLogger().setLevel(logging.WARN)

# Suppress FastMCP banner by setting environment variable
os.environ["FASTMCP_NO_BANNER"] = "1"

from .config import load_config
from .mcp_tools import create_mcp_server

# Configuration constants
ALLOWED_MIME_TYPES = {"application/json", "application/pdf", "text/plain"}

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting MCP-only server in stdio mode")

    # Load configuration
    config = load_config()
    document_store = config.storage.document_store()
    max_file_size_bytes = config.limits.max_file_size_mb * 1024 * 1024

    logger.info(f"Using document store: {type(document_store).__name__}")

    # Create MCP server
    # Note: We pass the document store directly - FastMCP will handle initialization
    mcp_server = create_mcp_server(
        document_store=document_store,
        max_file_size_bytes=max_file_size_bytes,
        allowed_mime_types=ALLOWED_MIME_TYPES,
    )

    logger.info("MCP server created, starting stdio transport...")

    # Run in stdio mode (FastMCP's run() creates its own event loop)
    # This blocks until the client disconnects
    mcp_server.run()


if __name__ == "__main__":
    main()
