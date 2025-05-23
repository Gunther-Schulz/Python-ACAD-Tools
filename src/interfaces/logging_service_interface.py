"""Interface for logging services."""
from typing import Protocol, Any, Optional

# Standard logging levels
# import logging # Not importing here, interface defines methods, not implementation details

from ..domain.exceptions import ConfigError

class ILoggingService(Protocol):
    """Interface for a standardized logging service within the application."""

    def setup_logging(
        self,
        log_level_console: str = "INFO",
        log_level_file: Optional[str] = "DEBUG",
        log_file_path: Optional[str] = None,
        # config: Optional[AppConfig] = None # Or pass specific logging settings
    ) -> None:
        """
        Configures the logging system for the application.
        Should be called once at application startup.

        Args:
            log_level_console: Logging level for console output (e.g., "DEBUG", "INFO").
            log_level_file: Logging level for file output. If None, file logging disabled.
            log_file_path: Path to the log file. Required if log_level_file is set.
        """
        ...

    def set_log_level(self, logger_name: Optional[str], level: str) -> None:
        """
        Sets the logging level for a specific logger or the root logger.

        Args:
            logger_name: Name of the logger. If None, sets for the root logger.
            level: The logging level string (e.g., "DEBUG", "INFO", "WARNING").
        """
        ...

    def get_logger(self, name: str) -> Any: # Should return a logger-like object
        """
        Retrieves a logger instance with the given name.
        The returned object should have standard logging methods like debug, info, warning, error, exception.

        Args:
            name: The name for the logger (typically __name__ of the calling module).

        Returns:
            A logger object/interface that supports methods like .info(), .error(), etc.
        """
        ...

    # Convenience methods (optional, as get_logger().info() is standard)
    # Implementers can choose to provide these or expect users to use get_logger()

    # def info(self, message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    #     ...

    # def warning(self, message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    #     ...

    # def error(self, message: str, logger_name: Optional[str] = None, exc_info: bool = False, **kwargs) -> None:
    #     ...

    # def debug(self, message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    #     ...
