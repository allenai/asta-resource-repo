"""Configuration management for Asta Resource Repository"""

import os

from pyhocon import ConfigFactory, ConfigTree
from pydantic import BaseModel, Field

from ..document_store.local_index import LocalIndexDocumentStore


class Config(BaseModel):
    """Main configuration for Asta Resource Repository"""

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

    def document_store(self) -> LocalIndexDocumentStore:
        """Factory method to create document store"""
        return LocalIndexDocumentStore()

    @staticmethod
    def from_config(config: ConfigTree) -> "Config":
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

        return Config(allowed_mime_types=allowed_mime_types)


def load_config() -> Config:
    config_file = os.getenv(
        "CONFIG_FILE",
        os.path.join(os.path.dirname(__file__), f'{os.getenv("ENV", "local")}.conf'),
    )
    return Config.from_config(ConfigFactory.parse_file(config_file))
