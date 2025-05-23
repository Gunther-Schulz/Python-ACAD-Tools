"""Utilities related to file and directory operations."""
import os

def ensure_parent_dir_exists(filepath: str) -> None:
    """Ensures that the parent directory of the given filepath exists, creating it if necessary."""
    parent_dir = os.path.dirname(filepath)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
        # Potentially log this creation through a logging service if available/passed
        # print(f"Created directory: {parent_dir}") # Simple print for now if no logger
