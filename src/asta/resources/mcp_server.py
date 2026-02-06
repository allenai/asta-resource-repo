#!/usr/bin/env python3
"""
MCP-only server for stdio transport.
This is the dedicated MCP server without REST API components.
Provides document metadata indexing with local YAML storage.
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

logger = logging.getLogger(__name__)


def main():
    logger.info("Starting MCP server for document metadata index in stdio mode")

    # Load configuration
    config = load_config()
    document_store = config.document_store()
    allowed_mime_types = set(config.allowed_mime_types)

    logger.info(f"Using document store: {type(document_store).__name__}")
    logger.info(f"Index path: {getattr(document_store, 'index_path', 'N/A')}")

    # Create MCP server (single-user, no authentication required)
    # Note: FastMCP will handle document store initialization via lifespan
    mcp_server = create_mcp_server(
        document_store=document_store,
        allowed_mime_types=allowed_mime_types,
    )

    logger.info("MCP server created, starting stdio transport...")

    # Run in stdio mode (FastMCP's run() creates its own event loop)
    # This blocks until the client disconnects
    mcp_server.run()


if __name__ == "__main__":
    main()
