"""Unified server with both MCP and REST API endpoints"""

import logging
from contextlib import asynccontextmanager

import click
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config
from .rest_api import create_rest_router
from .mcp_tools import create_mcp_server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration constants
ALLOWED_MIME_TYPES = {"application/json", "application/pdf", "text/plain"}


def create_app() -> tuple[FastAPI, any]:
    """Factory function to create the FastAPI app and MCP server"""
    # Load configuration
    config = load_config()
    document_store = config.storage.document_store()

    # Create MCP server first (it has its own lifespan for document store)
    mcp_server = create_mcp_server(
        document_store=document_store,
        max_file_size_bytes=config.limits.max_file_size_mb * 1024 * 1024,
        allowed_mime_types=ALLOWED_MIME_TYPES,
    )

    # Get the MCP HTTP app (which has the lifespan)
    mcp_http_app = mcp_server.http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager that wraps MCP's lifespan"""
        # The MCP server's lifespan will handle document store initialization
        # We wrap it to add any FastAPI-specific startup/shutdown logic
        logger.info("Starting FastAPI server with MCP and REST endpoints")

        # Run MCP's lifespan which initializes the document store
        async with mcp_http_app.router.lifespan_context(mcp_http_app):
            logger.info("Document store initialized via MCP lifespan")
            yield
            logger.info("Shutting down FastAPI server")

    # Create FastAPI application
    app = FastAPI(
        title="Asta Resource Repository",
        description="MCP server for Asta resource management with REST API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create and mount REST API router
    rest_router = create_rest_router(
        document_store=document_store,
        max_file_size_bytes=config.limits.max_file_size_mb * 1024 * 1024,
        allowed_mime_types=ALLOWED_MIME_TYPES,
    )
    app.include_router(rest_router)

    # Mount MCP server under /mcp prefix
    # Note: We don't mount the app again since we already created it above
    # and we're managing its lifespan in the FastAPI lifespan
    app.mount("/mcp", mcp_http_app)

    # Add root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with service information"""
        return {
            "service": "asta-resource-repository",
            "version": "0.1.0",
            "endpoints": {
                "mcp": "/mcp - MCP protocol endpoints",
                "rest": "/rest - REST API endpoints",
                "docs": "/docs - OpenAPI documentation",
            },
        }

    logger.info("Unified server initialized with MCP (/mcp) and REST (/rest) endpoints")

    return app, mcp_server


@click.command()
@click.option(
    "--port",
    type=int,
    default=None,
    help="Port to bind to (overrides config)",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
def main(port: int | None, reload: bool):
    """Main entry point for running the unified HTTP server (MCP + REST)"""
    import uvicorn

    # Create app only when starting the server
    app, mcp_server = create_app()

    # Run HTTP server with both MCP and REST APIs
    config = load_config()
    server_host = config.server.host
    server_port = port or config.server.port

    logger.info(f"Running HTTP server on {server_host}:{server_port}")
    logger.info(f"  MCP endpoints: http://{server_host}:{server_port}/mcp")
    logger.info(f"  REST endpoints: http://{server_host}:{server_port}/rest")
    logger.info(f"  API docs: http://{server_host}:{server_port}/docs")

    uvicorn.run(
        app,
        host=server_host,
        port=server_port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
