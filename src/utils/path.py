"""
Path utility functions.
"""
import os
from pathlib import Path
from typing import Optional
from .logging import log_debug


def ensure_path_exists(path: str) -> bool:
    """
    Ensure a path exists, creating directories if necessary.

    Args:
        path: Path to ensure exists

    Returns:
        True if path exists or was created, False otherwise
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        log_debug(f"Error creating path {path}: {str(e)}")
        return False


def resolve_path(path: str, prefix: Optional[str] = None) -> str:
    """
    Resolve a path using an optional prefix.

    Args:
        path: Path to resolve
        prefix: Optional prefix to prepend to path

    Returns:
        Resolved path
    """
    if not path:
        return path

    # Expand user path (handles ~)
    path = os.path.expanduser(path)

    # If path is absolute, return it
    if Path(path).is_absolute():
        return path

    # If prefix is provided, join it with the path
    if prefix:
        # Expand user path for prefix as well
        prefix = os.path.expanduser(prefix)
        return str(Path(prefix) / path)

    return path
