import logging
import sys
from pathlib import Path
from typing import Optional

# Global logger instance
_logger: Optional[logging.Logger] = None

def setup_logging(level: str = 'INFO', log_file: Optional[Path] = None) -> None:
    """Setup logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
    """
    global _logger
    
    if _logger is not None:
        return  # Already configured
    
    # Create logger
    _logger = logging.getLogger('pycad')
    _logger.setLevel(getattr(logging, level.upper()))
    
    # Create formatters
    console_formatter = logging.Formatter(
        '%(message)s'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    _logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        _logger.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.
    
    Args:
        name: Name of the logger (usually __name__)
        
    Returns:
        Logger instance
    """
    if _logger is None:
        setup_logging()
    return logging.getLogger(f'pycad.{name}')

def set_log_level(level: str) -> None:
    """Set the logging level.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    if _logger is None:
        setup_logging(level)
    else:
        _logger.setLevel(getattr(logging, level.upper()))

# Convenience functions
def log_debug(msg: str) -> None:
    """Log a debug message."""
    get_logger(__name__).debug(msg)

def log_info(msg: str) -> None:
    """Log an info message."""
    get_logger(__name__).info(msg)

def log_warning(msg: str) -> None:
    """Log a warning message."""
    get_logger(__name__).warning(msg)

def log_error(msg: str) -> None:
    """Log an error message."""
    get_logger(__name__).error(msg) 