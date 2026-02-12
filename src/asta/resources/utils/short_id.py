"""Short ID generation utilities for document URIs"""

import secrets
import string

# Base62 alphabet (a-zA-Z0-9) for URL-safe, readable IDs
BASE62_ALPHABET = string.ascii_letters + string.digits


def generate_short_id(length: int = 10) -> str:
    """Generate a random base62-encoded short ID

    Uses cryptographically secure random number generation to create
    a short alphanumeric ID suitable for use in URIs.

    Args:
        length: Length of the ID in characters (default: 10)
                10 characters = 62^10 = ~839 quadrillion possibilities

    Returns:
        Random base62 string of specified length

    Examples:
        >>> id1 = generate_short_id()
        >>> len(id1)
        10
        >>> id1.isalnum()
        True
    """
    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))


def generate_unique_short_id(
    existing: set[str], length: int = 10, max_retries: int = 10
) -> str:
    """Generate a unique short ID that doesn't collide with existing IDs

    Attempts to generate a unique ID with collision checking and retry logic.
    The probability of collision is extremely low (< 0.00000006% for 10k documents),
    but we check anyway for safety.

    Args:
        existing: Set of existing short IDs to check against
        length: Length of the ID in characters (default: 10)
        max_retries: Maximum number of generation attempts (default: 10)

    Returns:
        Unique short ID that doesn't exist in the provided set

    Raises:
        RuntimeError: If unable to generate unique ID after max_retries
                     (indicates critical issue, should never happen in practice)

    Examples:
        >>> existing = {"abc123xyz0", "def456uvw1"}
        >>> new_id = generate_unique_short_id(existing)
        >>> new_id not in existing
        True
        >>> len(new_id)
        10
    """
    for attempt in range(max_retries):
        short_id = generate_short_id(length)
        if short_id not in existing:
            return short_id

    # This should never happen in practice (collision probability is ~0.00000006% for 10k docs)
    raise RuntimeError(
        f"Failed to generate unique short ID after {max_retries} attempts. "
        f"This indicates a critical issue with the random number generator or an "
        f"extremely unlikely collision scenario. Existing IDs count: {len(existing)}"
    )
