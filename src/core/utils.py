"""Common utility functions used across the project."""

import os
import logging
from typing import Optional
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def resolve_path(path: str, folder_prefix: Optional[str] = None) -> str:
    """Resolve a path with optional folder prefix."""
    if not path:
        return path
        
    if folder_prefix:
        path = os.path.join(folder_prefix, path)
    
    return os.path.normpath(path)

def ensure_directory(path: str) -> None:
    """Ensure a directory exists, create if it doesn't."""
    os.makedirs(path, exist_ok=True)

def validate_file_exists(filepath: str) -> bool:
    """Validate that a file exists."""
    return os.path.isfile(filepath)

def get_file_extension(filepath: str) -> str:
    """Get the extension of a file."""
    return os.path.splitext(filepath)[1].lower()

def setup_logger(name: str, log_file: Optional[str] = None, level=logging.INFO) -> logging.Logger:
    """Set up a logger with optional file output."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if log_file:
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
    
    return logger 