"""Authorization and user context management"""

import os
import re
from uuid import UUID
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

from .exceptions import ValidationError


class UnauthorizedError(Exception):
    """Raised when user authentication fails"""

    pass


@dataclass
class UserContext:
    """User context containing authenticated user information"""

    user_uri: str  # Format: asta://{namespace}/user/{uuid}
    user_id: str  # Just the UUID part

    def __post_init__(self):
        """Validate user context after initialization"""
        validate_user_uri(self.user_uri)


def validate_user_uri(uri: str) -> tuple[str, str]:
    """Validate user URI format and extract user ID

    Args:
        uri: User URI in format asta://{namespace}/user/{uuid}

    Returns:
        Tuple of (full_uri, user_id)

    Raises:
        ValidationError: If the URI format is invalid
    """
    if not uri or not isinstance(uri, str):
        raise ValidationError(f"User URI must be a non-empty string, got: {uri}")

    # Pattern: asta://{namespace}/user/{uuid}
    pattern = r"^asta://([^/]+)/user/([a-f0-9-]+)$"
    match = re.match(pattern, uri, re.IGNORECASE)

    if not match:
        raise ValidationError(
            f"User URI must be in format 'asta://{{namespace}}/user/{{uuid}}', got: {uri}"
        )

    user_id = match.group(2)

    # Validate UUID format
    try:
        UUID(user_id)
    except ValueError:
        raise ValidationError(
            f"Invalid UUID format in user URI: {uri}. "
            f"UUID part '{user_id}' is not a valid UUID."
        )

    return uri, user_id


def get_user_context_from_env() -> UserContext:
    """Get user context from ASTA_USER environment variable (stdio mode)

    Returns:
        UserContext with authenticated user information

    Raises:
        UnauthorizedError: If ASTA_USER is not set or invalid
    """
    user_uri = os.environ.get("ASTA_USER")

    if not user_uri:
        raise UnauthorizedError(
            "Authentication required: ASTA_USER environment variable not set. "
            "Set ASTA_USER to your user URI in format 'asta://{namespace}/user/{uuid}'"
        )

    try:
        validated_uri, user_id = validate_user_uri(user_uri)
        return UserContext(user_uri=validated_uri, user_id=user_id)
    except ValidationError as e:
        raise UnauthorizedError(f"Invalid ASTA_USER environment variable: {e}")


def get_user_context_from_header(
    authorization: Optional[str] = Header(None),
) -> UserContext:
    """Get user context from Authorization header (HTTP mode)

    Supports both formats:
    - "Bearer asta://{namespace}/user/{uuid}"
    - "asta://{namespace}/user/{uuid}"

    Args:
        authorization: Authorization header value

    Returns:
        UserContext with authenticated user information

    Raises:
        HTTPException: If Authorization header is missing or invalid
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Authorization header missing. "
            "Provide Authorization header with format 'Bearer asta://{namespace}/user/{uuid}' or 'asta://{namespace}/user/{uuid}'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user URI from Authorization header
    user_uri = authorization.strip()

    # Handle "Bearer " prefix
    if user_uri.lower().startswith("bearer "):
        user_uri = user_uri[7:].strip()

    try:
        validated_uri, user_id = validate_user_uri(user_uri)
        return UserContext(user_uri=validated_uri, user_id=user_id)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Authorization header: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
