"""Document storage interface and implementations"""

from .base import DocumentStore
from .local_index import LocalIndexDocumentStore

__all__ = ["DocumentStore", "LocalIndexDocumentStore"]
