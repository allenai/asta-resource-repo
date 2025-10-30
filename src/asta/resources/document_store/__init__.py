"""Document storage interface and implementations"""

from .postgres import PostgresDocumentStore

__all__ = ["PostgresDocumentStore"]
