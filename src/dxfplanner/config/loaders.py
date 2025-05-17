import yaml
from pathlib import Path
from typing import Union, List, Type, TypeVar

from pydantic import ValidationError
from .schemas import ProjectConfig # Changed from AppConfig
from dxfplanner.core.exceptions import ConfigurationError

T = TypeVar('T', bound=ProjectConfig) # Changed from AppConfig

DEFAULT_CONFIG_FILES = ["config.yml", "config.yaml"]

def find_config_file(
    config_file_or_dir: Union[str, Path, None] = None,
    default_filenames: List[str] = None
) -> Path:
    """
    Finds a configuration file.

    Resolution order:
    1. If `config_file_or_dir` is a file, use it.
    2. If `config_file_or_dir` is a directory, search for `default_filenames` in it.
    3. If `config_file_or_dir` is None, search for `default_filenames` in the current working directory.
    4. If `config_file_or_dir` is None, search for `default_filenames` in common config paths (e.g., ./config).

    Args:
        config_file_or_dir: Specific file path or directory to search in.
        default_filenames: List of default filenames to look for if a directory is given
                           or if no specific path is provided.

    Returns:
        Path to the found configuration file.

    Raises:
        ConfigurationError: If no configuration file can be found.
    """
    if default_filenames is None:
        default_filenames = DEFAULT_CONFIG_FILES

    search_paths: List[Path] = []

    if config_file_or_dir:
        p = Path(config_file_or_dir)
        if p.is_file():
            if not p.exists():
                raise ConfigurationError(f"Specified configuration file not found: {p}")
            return p
        elif p.is_dir():
            search_paths.append(p)
        else:
            # Try interpreting as a file in CWD if it doesn't exist as an absolute/relative path
            # This handles cases where just a filename is passed.
            cwd_p = Path.cwd() / p.name
            if cwd_p.is_file():
                return cwd_p
            # If it's not a dir and not an existing file path (absolute or relative to cwd for filename only case)
            # then it's an invalid path unless it's a dir we haven't checked yet, but is_dir already failed.
            # This implies the provided path itself might be an issue if it's not a dir and not a file.
            # However, the primary logic is: if it's a file, use it. If a dir, search in it.
            # If it's neither an existing file nor dir, it should fall to search paths or error.
            # Let's assume if it's not an existing file or dir, it's likely a misconfiguration for this arg.
            # For robustness, if it's not a file or directory, we will add CWD to search_paths and hope for the best with default names
            pass # Let it fall through to search paths if not a clear file or dir

    # Add standard search paths
    if not search_paths: # If no specific dir was given to search
        search_paths.append(Path.cwd())
        search_paths.append(Path.cwd() / "config")
        search_paths.append(Path(__file__).parent.parent / "config") # project_root/config relative to this file

    for search_dir in search_paths:
        if search_dir.is_dir():
            for fname in default_filenames:
                file_path = search_dir / fname
                if file_path.is_file():
                    return file_path

    raise ConfigurationError(
        f"Configuration file not found. Searched in: {search_paths} for {default_filenames}"
    )

def load_config_from_yaml(
    config_file_path: Union[str, Path, None] = None,
    config_model: Type[T] = ProjectConfig # Changed from AppConfig
) -> T:
    """
    Loads configuration from a YAML file into a Pydantic model.

    Args:
        config_file_path: Path to the YAML configuration file. If None, attempts to find it.
        config_model: The Pydantic model to validate the configuration against (defaults to AppConfig).

    Returns:
        An instance of the Pydantic configuration model.

    Raises:
        ConfigurationError: If the file cannot be found, read, or parsed, or if validation fails.
    """
    actual_config_file = find_config_file(config_file_path)

    try:
        with open(actual_config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        if config_data is None:
            # Handle empty YAML file gracefully by returning a default model instance
            # This ensures that if a config file exists but is empty, the application
            # can still proceed with default configurations defined in Pydantic models.
            return config_model()
    except FileNotFoundError:
        # This case should theoretically be caught by find_config_file, but as a safeguard:
        raise ConfigurationError(f"Configuration file not found: {actual_config_file}")
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Error parsing YAML configuration file {actual_config_file}: {e}")
    except Exception as e:
        raise ConfigurationError(f"Error reading configuration file {actual_config_file}: {e}")

    try:
        return config_model(**config_data)
    except ValidationError as e:
        raise ConfigurationError(f"Configuration validation error in {actual_config_file}:\n{e}")
    except TypeError as e:
        # Handles cases where config_data might not be a dict (e.g. YAML loads a list or scalar)
        raise ConfigurationError(
            f"Configuration structure error in {actual_config_file}. Expected a dictionary, got {type(config_data)}. Error: {e}"
        )

# Example Usage (primarily for testing or direct script use):
# if __name__ == "__main__":
#     try:
#         # Create a dummy config.yml for testing
#         dummy_config_content = {
#             "logging": {"level": "DEBUG"},
#             "io": {"writers": {"dxf": {"default_layer": "TEST_LAYER"}}}
#         }
#         with open("config.yml", "w") as f_config:
#             yaml.dump(dummy_config_content, f_config)

#         app_config = load_config_from_yaml()
#         print("Successfully loaded configuration:")
#         print(f"  Logging Level: {app_config.logging.level}")
#         print(f"  DXF Default Layer: {app_config.io.writers.dxf.default_layer}")

#         # Test with a non-existent file to see error handling
#         # load_config_from_yaml("non_existent_config.yml")
#     except ConfigurationError as e:
#         print(f"Configuration Error: {e}")
#     finally:
#         # Clean up dummy config file
#         if Path("config.yml").exists():
#             Path("config.yml").unlink()
