"""
YAML file handling utilities.
"""
import os
import yaml
from typing import Dict, Any, Optional
from ..core.exceptions import ProjectError
from .logging import log_debug, log_info, log_warning


def load_yaml_file(
    filepath: str,
    required: bool = True,
    default: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Load and parse a YAML file.

    Args:
        filepath: Path to the YAML file
        required: Whether the file is required
        default: Default value if file is not found or empty

    Returns:
        Dictionary containing the YAML data

    Raises:
        ProjectError: If required file is not found or has invalid YAML
    """
    if default is None:
        default = {}

    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as file:
                data = yaml.safe_load(file)
                if data is None:  # File is empty or contains only comments
                    log_debug(f"File {filepath} is empty or contains only comments")
                    return default
                log_info(f"Loaded {filepath}")
                return data
        except yaml.YAMLError as e:
            raise ProjectError(f"Error parsing {filepath}: {str(e)}")
    elif required:
        raise ProjectError(f"Required config file not found: {filepath}")

    log_debug(f"Optional file not found: {filepath}")
    return default


def load_yaml_with_key(
    filepath: str,
    key: str,
    required: bool = True,
    default: Optional[Any] = None
) -> Any:
    """
    Load a YAML file and extract a specific key.

    Args:
        filepath: Path to the YAML file
        key: Key to extract from the YAML data
        required: Whether the file is required
        default: Default value if file is not found or key doesn't exist

    Returns:
        Value associated with the key

    Raises:
        ProjectError: If required file is not found or has invalid YAML
    """
    data = load_yaml_file(filepath, required, {})
    return data.get(key, default)
