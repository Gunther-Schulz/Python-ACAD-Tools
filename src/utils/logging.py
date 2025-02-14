"""Logging utilities for the application."""

import logging
import os
import sys
import warnings
import traceback
from typing import Optional, Any, Callable
from functools import wraps

class Colors:
    """ANSI color codes for terminal output."""
    WARNING = "\033[93m"
    ERROR = "\033[91m"
    RESET = "\033[0m"

    @classmethod
    def wrap(cls, text: str, color: str) -> str:
        """Wrap text with color codes."""
        return f"{color}{text}{cls.RESET}"

class LoggerSetup:
    """Handles logger configuration and setup."""
    
    @staticmethod
    def _create_formatter(for_file: bool = True) -> logging.Formatter:
        """Create a formatter for either file or console output."""
        return logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s' if for_file 
            else '%(levelname)s:%(name)s:%(message)s'
        )
    
    @staticmethod
    def _setup_handler(handler: logging.Handler, level: int, for_file: bool = True) -> None:
        """Configure a logging handler with level and formatter."""
        handler.setLevel(level)
        handler.setFormatter(LoggerSetup._create_formatter(for_file))

    @classmethod
    def setup(cls, level: str = 'INFO') -> None:
        """Setup logging configuration with file and console handlers."""
        # Set logging levels for external libraries
        for logger_name in ['fiona', 'osgeo', 'pyogrio._io']:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
        
        # Create logs directory
        os.makedirs('logs', exist_ok=True)
        
        # Setup root logger
        root_logger = logging.getLogger('')
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers.clear()
        
        # Configure handlers
        handlers = {
            'debug': (logging.FileHandler('logs/debug.log', mode='w'), logging.DEBUG),
            'info': (logging.FileHandler('logs/info.log', mode='w'), logging.INFO),
            'warning': (logging.FileHandler('logs/warning.log', mode='w'), logging.WARNING),
            'error': (logging.FileHandler('logs/error.log', mode='w'), logging.ERROR),
            'console': (logging.StreamHandler(), getattr(logging, level.upper()))
        }
        
        for handler, level in handlers.values():
            cls._setup_handler(handler, level, isinstance(handler, logging.FileHandler))
            root_logger.addHandler(handler)
        
        # Route warnings through logging system
        warnings.showwarning = warning_to_logger

def with_caller_info(func: Callable) -> Callable:
    """Decorator to add caller information to log messages."""
    @wraps(func)
    def wrapper(message: str, *args: Any, **kwargs: Any) -> None:
        stack = traceback.extract_stack()
        caller = stack[-3]  # Skip this function and the logging function
        message = f"{message} (from {caller.filename}:{caller.lineno})"
        return func(message, *args, **kwargs)
    return wrapper

@with_caller_info
def log_debug(message: str) -> None:
    """Log a debug message with caller info."""
    logging.debug(message)

def log_info(*messages: str) -> None:
    """Log an info message."""
    logging.info(' '.join(str(msg) for msg in messages))

def log_warning(message: str) -> None:
    """Log a warning message with color."""
    logging.warning(Colors.wrap(message, Colors.WARNING))

def log_error(message: str, abort: bool = True, exc_info: Optional[Exception] = None) -> None:
    """Log an error message with color and optional exception info."""
    error_msg = Colors.wrap(f"Error: {message}", Colors.ERROR)
    
    if exc_info:
        error_type = type(exc_info).__name__
        error_traceback = ''.join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
        logging.error(f"{error_msg}\nError Type: {error_type}\nTraceback:\n{error_traceback}")
    else:
        error_traceback = traceback.format_exc()
        if error_traceback != "NoneType: None\n":
            logging.error(f"{error_msg}\nTraceback:\n{error_traceback}")
        else:
            logging.error(error_msg)
    
    if abort:
        sys.exit(1)

def set_log_level(level: str) -> None:
    """Set the logging level for console handler only."""
    log_level = getattr(logging, level.upper())
    for handler in logging.getLogger('').handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(log_level)
            break

def warning_to_logger(message: Any, category: Any, filename: str, lineno: int, 
                     file: Optional[Any] = None, line: Optional[str] = None) -> None:
    """Convert warnings to log messages."""
    logging.warning(f'{filename}:{lineno}: {category.__name__}: {message}') 