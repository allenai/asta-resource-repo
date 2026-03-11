"""Utilities for handling file paths and URLs"""

from pathlib import Path
from urllib.parse import unquote, urlparse


def normalize_file_url(url: str, index_path: Path) -> str:
    """Normalize file URLs to use relative paths when possible

    If the URL points to a file within the same directory tree as the index file,
    convert it to a relative path instead of an absolute file:// URL or absolute path.

    Args:
        url: The URL to normalize (can be file://, absolute path, or URL)
        index_path: Path to the index file

    Returns:
        Normalized URL (relative path if within same tree, otherwise unchanged)

    Examples:
        >>> normalize_file_url("file:///path/to/project/docs/paper.pdf", Path("/path/to/project/index.yaml"))
        "docs/paper.pdf"

        >>> normalize_file_url("/path/to/project/docs/paper.pdf", Path("/path/to/project/index.yaml"))
        "docs/paper.pdf"

        >>> normalize_file_url("https://example.com/paper.pdf", Path("/path/to/project/index.yaml"))
        "https://example.com/paper.pdf"
    """
    # Parse the URL
    parsed = urlparse(url)

    # Only process file:// URLs or paths without scheme
    if parsed.scheme and parsed.scheme not in ("file", ""):
        # Not a local file (http://, https://, s3://, gs://, etc.)
        return url

    # Convert file:// URL to path
    if parsed.scheme == "file":
        # Handle file:// URLs
        file_path = unquote(parsed.path)
        # On Windows, file URLs may have an extra leading slash
        if file_path.startswith("/") and len(file_path) > 2 and file_path[2] == ":":
            file_path = file_path[1:]
    elif "://" not in url:
        # Plain file path without scheme - treat as absolute path
        file_path = url
    else:
        # Has a scheme but not file:// - return unchanged
        return url

    # Convert to Path object
    target_path = Path(file_path)

    # Only resolve if it's an absolute path or if the file exists
    # This prevents resolving non-existent relative paths like "invalid-url"
    if target_path.is_absolute():
        try:
            target_path = target_path.resolve()
        except (ValueError, OSError):
            # Invalid path, return original URL
            return url
    elif target_path.exists():
        # Relative path that exists - resolve it
        try:
            target_path = target_path.resolve()
        except (ValueError, OSError):
            # Invalid path, return original URL
            return url
    else:
        # Relative path that doesn't exist - return original URL unchanged
        # Let the validation logic handle it
        return url

    # Get repository root - simply use the parent directory of the index file
    # All paths are relative to the index location
    index_path = Path(index_path).resolve()
    repo_root = index_path.parent

    # Check if target is within repository
    try:
        rel_path = target_path.relative_to(repo_root)
        # Successfully computed relative path - file is within repo
        # Return as POSIX-style relative path (works on all platforms)
        return rel_path.as_posix()
    except ValueError:
        # File is outside repository - return as absolute file:// URL
        # This ensures portability even for external files
        return f"file://{target_path.as_posix()}"
