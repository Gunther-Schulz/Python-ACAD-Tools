"""Filesystem utility functions for file and directory operations."""
import os


def ensure_parent_dir_exists(filepath: str) -> None:
    """Ensures that the parent directory of the given filepath exists, creating it if necessary."""
    parent_dir = os.path.dirname(filepath)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
