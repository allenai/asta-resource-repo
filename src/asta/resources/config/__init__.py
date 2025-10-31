"""Configuration management for Asta Resource Repository"""

import os

from pyhocon import ConfigFactory, ConfigTree
from pydantic import BaseModel, Field

from ..document_store.postgres import PostgresDocumentStore


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


class StorageConfig(BaseModel):
    """Storage backend configuration"""

    postgres: PostgresStorageConfig = Field(default_factory=PostgresStorageConfig)

    def document_store(self) -> PostgresDocumentStore:
        return PostgresDocumentStore(
            namespace=self.postgres.namespace,
            connection_string=self.postgres.url,
        )

    @staticmethod
    def from_config(config: ConfigTree) -> "StorageConfig":
        return StorageConfig(
            postgres=PostgresStorageConfig.from_config(config["postgres"]),
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
    """Main configuration for User Document Service"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)

    @staticmethod
    def from_config(config: ConfigTree) -> "Config":
        return Config(
            server=ServerConfig.from_config(config["server"]),
            storage=StorageConfig.from_config(config["storage"]),
            limits=LimitsConfig.from_config(config["limits"]),
        )


def load_config() -> Config:
    config_file = os.getenv(
        "CONFIG_FILE",
        os.path.join(os.path.dirname(__file__), f'{os.getenv("ENV", "local")}.conf'),
    )
    return Config.from_config(ConfigFactory.parse_file(config_file))
