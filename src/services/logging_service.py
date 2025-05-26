"""Concrete implementation of the ILoggingService interface."""
import logging
import sys
from typing import Optional, Any

from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import ConfigError # For potential future use if config validation is stricter
from ..utils.color_formatter import ColorFormatter

# Default formatter for logs
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels in console output."""

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.color_formatter = ColorFormatter(use_colors=use_colors)

    def format(self, record):
        # Format the record normally first
        formatted = super().format(record)

        # Only colorize the level name part
        if self.color_formatter.use_colors:
            # Replace the level name in the formatted string with colored version
            colored_level = self.color_formatter.colorize_log_level(record.levelname)
            formatted = formatted.replace(record.levelname, colored_level, 1)

        return formatted

class LoggingService(ILoggingService):
    """Provides logging functionalities using Python's standard logging module."""

    _instance = None
    _initialized = False

    # Making it a Borg singleton to ensure configuration is applied once
    # and all parts of the app get the same configured logger instances.
    # A simpler approach for some apps might be a module-level setup_logging call,
    # but a service allows for dependency injection and easier testing/mocking.
    _shared_state = {}

    def __init__(self, log_level_console: str = "INFO", log_level_file: Optional[str] = "DEBUG", log_file_path: Optional[str] = None, use_colors: Optional[bool] = None):
        """Initialize LoggingService with configuration."""
        self.__dict__ = self._shared_state
        if not hasattr(self.__class__, '_initialized_borg') or not self.__class__._initialized_borg:
            # Initialize instance attributes only once per class
            self.__class__._initialized_borg = True
            # Store color preference
            self._use_colors = use_colors
            # Perform actual one-time initialization if needed here for the Borg state
            # Auto-setup logging if parameters are provided
            if log_level_console or log_level_file or log_file_path:
                self.setup_logging(log_level_console, log_level_file, log_file_path, use_colors)

    def setup_logging(
        self,
        log_level_console: str = "INFO",
        log_level_file: Optional[str] = "DEBUG",
        log_file_path: Optional[str] = None,
        use_colors: Optional[bool] = None,
    ) -> None:
        """Configures the logging system for the application."""
        # Ensure setup runs only once effectively for the Borg state
        if self._shared_state.get("_logging_configured", False):
            # Could log a warning if called multiple times, or simply return
            logging.getLogger(__name__).debug("Logging already configured. Skipping re-setup.")
            return

        root_logger = logging.getLogger()
        root_logger.handlers.clear() # Clear any existing handlers
        # Set root logger level to the lowest of all handlers to allow them to pick up messages
        # Individual handlers will then filter based on their own levels.
        root_logger.setLevel(logging.DEBUG) # Or determine lowest programmatically

        # Use color preference from initialization or parameter
        colors_enabled = use_colors if use_colors is not None else getattr(self, '_use_colors', None)

        # Console Handler with colored formatter
        console_level_val = logging.getLevelName(log_level_console.upper())
        if not isinstance(console_level_val, int):
            logging.warning(
                f"Invalid console log level '{log_level_console}'. Defaulting to INFO."
            )
            console_level_val = logging.INFO

        console_handler = logging.StreamHandler(sys.stdout)
        # Use colored formatter for console output
        console_formatter = ColoredFormatter(LOG_FORMAT, DATE_FORMAT, use_colors=colors_enabled)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(console_level_val)
        root_logger.addHandler(console_handler)

        # File Handler (Optional) - always use plain formatter for files
        if log_level_file and log_file_path:
            file_level_val = logging.getLevelName(log_level_file.upper())
            if not isinstance(file_level_val, int):
                logging.warning(
                    f"Invalid file log level '{log_level_file}'. Defaulting to DEBUG."
                )
                file_level_val = logging.DEBUG

            try:
                file_handler = logging.FileHandler(log_file_path, mode='a')
                # Use plain formatter for file output (no colors in files)
                file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
                file_handler.setFormatter(file_formatter)
                file_handler.setLevel(file_level_val)
                root_logger.addHandler(file_handler)
            except (IOError, OSError) as e:
                # Log to console if file handler setup fails
                logging.error(f"Failed to set up file logger at '{log_file_path}': {e}", exc_info=True)
        elif log_level_file and not log_file_path:
            logging.warning(
                "File logging level specified but no log_file_path provided. File logging disabled."
            )

        self._shared_state["_logging_configured"] = True
        logging.getLogger(__name__).info(
            f"Logging configured. Console: {log_level_console}, File: {log_level_file or 'Disabled'}"
        )

    def set_log_level(self, logger_name: Optional[str], level: str) -> None:
        """Sets the logging level for a specific logger or the root logger."""
        level_val = logging.getLevelName(level.upper())
        if not isinstance(level_val, int):
            effective_logger_name = logger_name or "root"
            logging.warning(
                f"Invalid log level '{level}' for logger '{effective_logger_name}'. No change applied."
            )
            return

        logger_to_set = logging.getLogger(logger_name)
        logger_to_set.setLevel(level_val)
        logging.getLogger(__name__).info(
            f"Log level for '{logger_name or 'root'}' set to {level.upper()}"
        )

    def get_logger(self, name: str) -> logging.Logger:
        """Retrieves a logger instance with the given name."""
        # Ensure logging is configured before returning a logger
        # This is a simple check; a more robust app might enforce setup_logging call at startup
        if not self._shared_state.get("_logging_configured", False):
            # Fallback to basic config if not explicitly set up.
            # This is not ideal as it won't use custom formatters/handlers defined in setup_logging
            # but prevents total failure if get_logger is called before setup.
            logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT, datefmt=DATE_FORMAT)
            logging.getLogger(__name__).warning(
                "LoggingService.get_logger called before setup_logging. Using basicConfig."
            )
            self._shared_state["_logging_configured"] = True # Mark as configured to avoid repeated basicConfig

        return logging.getLogger(name)
