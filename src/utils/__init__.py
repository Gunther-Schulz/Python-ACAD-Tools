"""Utility functions and classes."""

from .logging import (
    log_info, log_warning, log_error, log_debug,
    LoggerSetup, set_log_level
)
from .base import (
    EnvironmentSetup, PathManager, ProjectManager,
)

# Re-export commonly used functions
setup_logging = LoggerSetup.setup
resolve_path = PathManager.resolve_path
ensure_path_exists = PathManager.ensure_path_exists
create_sample_project = ProjectManager.create_sample_project

__all__ = [
    'log_info',
    'log_warning',
    'log_error',
    'log_debug',
    'setup_logging',
    'set_log_level',
    'ensure_path_exists',
    'resolve_path',
    'create_sample_project',
]
