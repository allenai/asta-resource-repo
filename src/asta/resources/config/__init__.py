"""Configuration management for Asta Resource Repository"""

import os
from typing import Optional

from pyhocon import ConfigFactory, ConfigTree
from pydantic import BaseModel, Field


class SearchConfig(BaseModel):
    """Search configuration settings"""

    enable_cache: bool = True
    cache_filename: str = "search.db"
    enable_embeddings: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    field_weights: dict[str, float] = Field(
        default={
            "summary": 3.0,
            "name": 2.0,
            "tags": 1.5,
            "extra": 1.0,
        }
    )
    hybrid_bm25_weight: float = 0.5
    hybrid_semantic_weight: float = 0.5

    @staticmethod
    def from_config(config: ConfigTree) -> "SearchConfig":
        # Parse search configuration
        return SearchConfig(
            enable_cache=config.get("enable_cache", True),
            cache_filename=config.get("cache_filename", "search.db"),
            enable_embeddings=config.get("embeddings.enabled", True),
            embedding_model=config.get(
                "embeddings.model", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            bm25_k1=config.get("bm25.k1", 1.2),
            bm25_b=config.get("bm25.b", 0.75),
            field_weights={
                "summary": config.get("field_weights.summary", 3.0),
                "name": config.get("field_weights.name", 2.0),
                "tags": config.get("field_weights.tags", 1.5),
                "extra": config.get("field_weights.extra", 1.0),
            },
            hybrid_bm25_weight=config.get("hybrid.bm25_weight", 0.5),
            hybrid_semantic_weight=config.get("hybrid.semantic_weight", 0.5),
        )


class Config(BaseModel):
    """Main configuration for Asta Resource Repository"""

    index_path: str = ".asta/documents/index.yaml"
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
    search: SearchConfig = Field(default_factory=SearchConfig)

    @staticmethod
    def from_config(config: ConfigTree) -> "Config":
        # Get allowed MIME types
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

        # Get index path
        index_path = config.get("index_path", ".asta/documents/index.yaml")

        # Parse search configuration
        search_config = SearchConfig.from_config(config.get_config("search"))

        return Config(
            index_path=index_path,
            allowed_mime_types=allowed_mime_types,
            search=search_config,
        )


def load_config(overrides: Optional[dict] = None) -> Config:
    """Load configuration from file with optional overrides.

    Args:
        overrides: Optional dictionary of configuration overrides

    Returns:
        Config object
    """
    config_file = os.getenv(
        "CONFIG_FILE",
        os.path.join(os.path.dirname(__file__), f'{os.getenv("ENV", "local")}.conf'),
    )

    # Load base configuration
    config = ConfigFactory.parse_file(config_file)

    # Apply overrides using pyhocon's with_fallback
    if overrides:
        override_config = ConfigFactory.from_dict(overrides)
        config = override_config.with_fallback(config)

    return Config.from_config(config)
