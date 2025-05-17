import sys
import loguru
import logging
import inspect

from dxfplanner.config.schemas import LoggingConfig # Will be created later

DEFAULT_LOGGING_CONFIG = LoggingConfig()

# ADDED InterceptHandler class (based on Loguru documentation)
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = loguru.logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        loguru.logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(config: LoggingConfig = DEFAULT_LOGGING_CONFIG) -> None:
    """
    Configures the loguru logger based on the provided configuration.
    Removes default handlers and adds a new one with specified format and level.
    Also intercepts standard Python logging and routes it through Loguru.
    """
    loguru.logger.remove()
    loguru.logger.add(
        sys.stderr,
        level=config.level.upper(),
        format=config.format,
        colorize=True,
        enqueue=True,  # Ensure thread-safe logging
        backtrace=True, # Better tracebacks
        diagnose=True   # Extended diagnosis for errors
    )
    loguru.logger.info(f"Loguru logger configured with level: {config.level}, format: '{config.format}'")

    # --- Intercept standard logging ---
    # Configure the root logger of the standard logging module to use InterceptHandler.
    # level=logging.NOTSET (or 0) ensures all messages are passed to the handler.
    # force=True (Python 3.8+) removes any existing handlers from the root logger.
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.NOTSET, force=True)
    loguru.logger.info("Standard logging has been intercepted and routed to Loguru.")

def get_logger(name: str = "dxfplanner") -> 'loguru.Logger':
    """
    Retrieves a logger instance.
    In loguru, all loggers are derived from the root logger, so this primarily
    serves as a conventional way to get a logger, though direct use of
    `from loguru import logger` is also common.

    Args:
        name: The name for the logger (often __name__ of the calling module).
              This is more for conventional use if specific named child loggers were needed,
              but loguru's default logger is usually sufficient.

    Returns:
        The loguru logger instance.
    """
    # For loguru, you typically just import and use the global logger.
    # This function can be used if a specific named logger is desired for some reason,
    # or to abstract away the direct import if that's preferred.
    # return loguru.logger.bind(name=name) # .bind() can be used to add contextual data
    return loguru.logger

# Example of initial setup if this module is imported directly
# and no other setup has occurred. In a DI setup, `setup_logging` would be called
# explicitly by the application's entry point with loaded configuration.
# if not loguru.logger._core.handlers: # Check if any handlers are configured
#     setup_logging()
