"""Configuration management for Asta Resource Repository"""

import os

from pyhocon import ConfigFactory, ConfigTree
from pydantic import BaseModel, Field

from ..document_store import DocumentStore
from ..document_store.local_index import LocalIndexDocumentStore

# Keep postgres import for backward compatibility during transition
try:
    from ..document_store.postgres import PostgresDocumentStore
except ImportError:
    PostgresDocumentStore = None


class ServerConfig(BaseModel):
    """Server configuration"""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    name: str = Field(default="asta-resource-repository", description="Service name")

    @staticmethod
    def from_config(config: ConfigTree) -> "ServerConfig":
        return ServerConfig(**config)


class PostgresStorageConfig(BaseModel):
    """PostgreSQL storage configuration"""

    namespace: str = Field(description="Namespace identifier for PostgreSQL storage")
    url: str = Field(
        default="postgresql://asta_resources:asta_resources@localhost:5432/asta_resources",
        description="PostgreSQL connection URL",
    )
    min_pool_size: int = Field(default=10, description="Minimum connection pool size")
    max_pool_size: int = Field(default=20, description="Maximum connection pool size")

    @staticmethod
    def from_config(config: ConfigTree) -> "PostgresStorageConfig":
        return PostgresStorageConfig(**config)


class LocalIndexStorageConfig(BaseModel):
    """Local index storage configuration"""

    namespace: str = Field(
        default="local-index", description="Namespace identifier for local index"
    )
    index_path: str = Field(
        default=".asta/index.yaml",
        description="Path to YAML index file (relative to cwd)",
    )
    resource_type: str = Field(
        default="document", description="Resource type for documents in URIs"
    )

    @staticmethod
    def from_config(config: ConfigTree) -> "LocalIndexStorageConfig":
        return LocalIndexStorageConfig(**config)


class GitHubStorageConfig(BaseModel):
    """GitHub storage configuration"""

    namespace: str = Field(description="Namespace identifier for GitHub storage")
    repo_owner: str = Field(description="GitHub repository owner")
    repo_name: str = Field(description="GitHub repository name")
    branch: str = Field(default="main", description="Git branch for storage")
    token: str = Field(description="GitHub personal access token")
    cache_db_path: str = Field(
        default=".asta/github_cache.db",
        description="Path to SQLite cache database",
    )
    cache_ttl_seconds: int = Field(
        default=300, description="Cache TTL in seconds (default 5 minutes)"
    )

    @staticmethod
    def from_config(config: ConfigTree) -> "GitHubStorageConfig":
        return GitHubStorageConfig(**config)


class StorageConfig(BaseModel):
    """Storage backend configuration"""

    backend: str = Field(
        default="local-index",
        description="Storage backend type (local-index, postgres, or github)",
    )
    local_index: LocalIndexStorageConfig = Field(
        default_factory=LocalIndexStorageConfig
    )
    postgres: PostgresStorageConfig | None = Field(
        default=None, description="PostgreSQL storage configuration"
    )
    github: GitHubStorageConfig | None = Field(
        default=None, description="GitHub storage configuration"
    )

    def document_store(self) -> DocumentStore:
        """Factory method to create document store based on backend"""
        if self.backend == "local-index":
            return LocalIndexDocumentStore(
                namespace=self.local_index.namespace,
                resource_type=self.local_index.resource_type,
                index_path=self.local_index.index_path,
            )
        elif self.backend == "postgres":
            if self.postgres is None or PostgresDocumentStore is None:
                raise ValueError(
                    "PostgreSQL storage configuration is required when backend is 'postgres'"
                )
            return PostgresDocumentStore(
                namespace=self.postgres.namespace,
                connection_string=self.postgres.url,
            )
        elif self.backend == "github":
            if self.github is None:
                raise ValueError(
                    "GitHub storage configuration is required when backend is 'github'"
                )
            from ..document_store.github.store import GitHubDocumentStore

            return GitHubDocumentStore(config=self.github)
        else:
            raise ValueError(f"Unsupported storage backend: {self.backend}")

    @staticmethod
    def from_config(config: ConfigTree) -> "StorageConfig":
        backend = config.get("backend", "local-index")

        # Parse backend-specific config
        local_index_config = LocalIndexStorageConfig.from_config(
            config.get("local-index", {})
        )
        postgres_config = None
        if "postgres" in config:
            postgres_config = PostgresStorageConfig.from_config(config["postgres"])
        github_config = None
        if "github" in config:
            github_config = GitHubStorageConfig.from_config(config["github"])

        return StorageConfig(
            backend=backend,
            local_index=local_index_config,
            postgres=postgres_config,
            github=github_config,
        )


class LimitsConfig(BaseModel):
    """Resource limits configuration"""

    max_file_size_mb: int = Field(
        default=100, description="Maximum file size in megabytes"
    )
    max_documents_per_user: int = Field(
        default=1000, description="Maximum documents per user"
    )

    @staticmethod
    def from_config(config: ConfigTree) -> "LimitsConfig":
        return LimitsConfig(**config)


class Config(BaseModel):
    """Main configuration for Asta Resource Repository"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    allowed_mime_types: list[str] = Field(
        default=[
            "application/json",
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/html",
        ],
        description="Allowed MIME types for documents",
    )

    @staticmethod
    def from_config(config: ConfigTree) -> "Config":
        # Server and limits are optional for local-index backend
        server_config = ServerConfig.from_config(config.get("server", {}))
        limits_config = LimitsConfig.from_config(config.get("limits", {}))
        allowed_mime_types = config.get(
            "allowed_mime_types",
            [
                "application/json",
                "application/pdf",
                "text/plain",
                "text/markdown",
                "text/html",
            ],
        )

        return Config(
            server=server_config,
            storage=StorageConfig.from_config(config["storage"]),
            limits=limits_config,
            allowed_mime_types=allowed_mime_types,
        )


def load_config() -> Config:
    config_file = os.getenv(
        "CONFIG_FILE",
        os.path.join(os.path.dirname(__file__), f'{os.getenv("ENV", "local")}.conf'),
    )
    return Config.from_config(ConfigFactory.parse_file(config_file))
