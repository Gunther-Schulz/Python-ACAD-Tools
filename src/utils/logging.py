import logging
import os
from typing import Optional
from pathlib import Path

class LogManager:
    _instance: Optional['LogManager'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LogManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not LogManager._initialized:
            self.logger = logging.getLogger('pycad')
            self.logger.setLevel(logging.INFO)
            LogManager._initialized = True

    def setup(self, log_file: str, log_level: str = 'INFO') -> None:
        """Setup logging configuration.
        
        Args:
            log_file: Path to the log file
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Remove existing handlers
        self.logger.handlers.clear()

        # Set log level
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)

        # Create formatters
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')

        # Setup file handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Setup console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

    def set_level(self, level: str) -> None:
        """Set the logging level.
        
        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))

# Global logger instance
log_manager = LogManager()

# Convenience functions
def setup_logging(log_file: str, log_level: str = 'INFO') -> None:
    """Setup logging configuration.
    
    Args:
        log_file: Path to the log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_manager.setup(log_file, log_level)

def set_log_level(level: str) -> None:
    """Set the logging level.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_manager.set_level(level)

def log_debug(message: str) -> None:
    """Log a debug message.
    
    Args:
        message: Message to log
    """
    log_manager.logger.debug(message)

def log_info(message: str) -> None:
    """Log an info message.
    
    Args:
        message: Message to log
    """
    log_manager.logger.info(message)

def log_warning(message: str) -> None:
    """Log a warning message.
    
    Args:
        message: Message to log
    """
    log_manager.logger.warning(message)

def log_error(message: str) -> None:
    """Log an error message.
    
    Args:
        message: Message to log
    """
    log_manager.logger.error(message)

def log_critical(message: str) -> None:
    """Log a critical message.
    
    Args:
        message: Message to log
    """
    log_manager.logger.critical(message) 