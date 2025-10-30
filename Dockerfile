# Dockerfile for Asta Resource Repository - Unified HTTP Server (MCP + REST)
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Create minimal package structure for dependency installation
RUN mkdir -p src/asta/resources && touch src/asta/resources/__init__.py

# Install dependencies (this layer will be cached unless pyproject.toml changes)
RUN uv pip install --system .

# Copy source code (changing source won't invalidate dependency cache)
COPY src/ ./src/

RUN uv pip install --system .

# Expose port
EXPOSE 8000

# Run the unified HTTP server (serves both MCP and REST)
CMD ["asta-resources-server", "--port", "8000"]
