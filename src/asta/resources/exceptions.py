"""Custom exceptions for Asta Resource Repository"""


class DocumentServiceError(Exception):
    """Base exception for all document service errors"""

    pass


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a document cannot be found"""

    pass


class InvalidMimeTypeError(DocumentServiceError):
    """Raised when an unsupported MIME type is provided"""

    pass


class DocumentTooLargeError(DocumentServiceError):
    """Raised when a document exceeds the maximum allowed size"""

    pass


class StorageError(DocumentServiceError):
    """Raised when there's an error with the storage backend"""

    pass


class DatabaseError(DocumentServiceError):
    """Raised when there's a database operation error"""

    pass


class ValidationError(DocumentServiceError):
    """Raised when input validation fails"""

    pass
