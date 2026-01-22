"""Git-based namespace derivation utilities

Automatically derives document namespace from git repository information
or falls back to local file path for non-git directories.
"""

import re
import subprocess
from pathlib import Path
from typing import Optional


def is_in_git_repo() -> bool:
    """Check if the current directory is inside a git repository

    Returns:
        True if in a git repository, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_remote_url(remote: str = "origin") -> Optional[str]:
    """Get the URL of a git remote

    Args:
        remote: Name of the remote (default: "origin")

    Returns:
        Remote URL string, or None if remote not found
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", f"remote.{remote}.url"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_current_branch() -> Optional[str]:
    """Get the current git branch name

    Returns:
        Branch name, or None if not on a branch (e.g., detached HEAD)
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def parse_git_remote(url: str) -> Optional[dict[str, str]]:
    """Parse a git remote URL to extract owner and repository name

    Supports both SSH and HTTPS formats:
    - SSH: git@github.com:owner/repo.git
    - HTTPS: https://github.com/owner/repo.git

    Args:
        url: Git remote URL

    Returns:
        Dict with 'owner' and 'repo' keys, or None if parsing fails
    """
    # SSH format: git@host:owner/repo.git
    ssh_pattern = r"git@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$"
    ssh_match = re.match(ssh_pattern, url)
    if ssh_match:
        return {"owner": ssh_match.group(1), "repo": ssh_match.group(2)}

    # HTTPS format: https://host/owner/repo.git
    https_pattern = r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$"
    https_match = re.match(https_pattern, url)
    if https_match:
        return {"owner": https_match.group(1), "repo": https_match.group(2)}

    return None


def derive_namespace(index_path: Path) -> str:
    """Derive namespace from git repository or local path

    If the index file is in a git repository with a remote configured,
    the namespace will be: {owner}/{repo}

    Otherwise, the namespace will be: local:{absolute_path}

    Args:
        index_path: Path to the index file

    Returns:
        Derived namespace string
    """
    # Try git-based namespace first
    if is_in_git_repo():
        try:
            remote_url = get_remote_url()

            if remote_url:
                parsed = parse_git_remote(remote_url)
                if parsed:
                    # Construct simple namespace: owner/repo (no branch)
                    return f"{parsed['owner']}/{parsed['repo']}"
        except Exception:
            # Fall through to local path
            pass

    # Fallback: use local file path
    return f"local:{index_path.absolute()}"
