"""Concrete implementation of the ILoggingService interface."""
import logging
import sys
from typing import Optional, Any

from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import ConfigError # For potential future use if config validation is stricter

# Default formatter for logs
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class LoggingService(ILoggingService):
    """Provides logging functionalities using Python's standard logging module."""

    _instance = None
    _initialized = False

    # Making it a Borg singleton to ensure configuration is applied once
    # and all parts of the app get the same configured logger instances.
    # A simpler approach for some apps might be a module-level setup_logging call,
    # but a service allows for dependency injection and easier testing/mocking.
    _shared_state = {}

    def __new__(cls, *args, **kwargs):
        obj = super(LoggingService, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls._shared_state
        if not hasattr(cls, '_initialized_borg') or not cls._initialized_borg:
            # Initialize instance attributes only once per class
            cls._initialized_borg = True
            # Perform actual one-time initialization if needed here for the Borg state
        return obj

    def setup_logging(
        self,
        log_level_console: str = "INFO",
        log_level_file: Optional[str] = "DEBUG",
        log_file_path: Optional[str] = None,
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

        formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

        # Console Handler
        console_level_val = logging.getLevelName(log_level_console.upper())
        if not isinstance(console_level_val, int):
            logging.warning(
                f"Invalid console log level '{log_level_console}'. Defaulting to INFO."
            )
            console_level_val = logging.INFO

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level_val)
        root_logger.addHandler(console_handler)

        # File Handler (Optional)
        if log_level_file and log_file_path:
            file_level_val = logging.getLevelName(log_level_file.upper())
            if not isinstance(file_level_val, int):
                logging.warning(
                    f"Invalid file log level '{log_level_file}'. Defaulting to DEBUG."
                )
                file_level_val = logging.DEBUG

            try:
                file_handler = logging.FileHandler(log_file_path, mode='a')
                file_handler.setFormatter(formatter)
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
