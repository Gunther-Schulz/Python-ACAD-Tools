"""
Logging utilities using loguru.
"""
import sys
from pathlib import Path
from typing import Optional
from loguru import logger

# Remove default logger
logger.remove()

# Add console logger with color
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    level="INFO",
    colorize=True,
    backtrace=True,  # Enable backtrace for all levels
    diagnose=True   # Enable diagnose for all levels
)

# Add file logger
def setup_file_logger(log_file: Optional[str] = None) -> None:
    """
    Set up file logging.

    Args:
        log_file: Path to log file. If None, uses 'pycad.log' in current directory
    """
    if log_file is None:
        log_file = "pycad.log"

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Add file logger
    logger.add(
        log_file,
        rotation="500 MB",
        retention="10 days",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}\n"
            "{exception}"  # This will include the traceback
        ),
        level="DEBUG",
        backtrace=True,  # Enable backtrace for all levels
        diagnose=True   # Enable diagnose for all levels
    )


def set_log_level(level: str) -> None:
    """
    Set the logging level.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
        backtrace=True,  # Enable backtrace for all levels
        diagnose=True   # Enable diagnose for all levels
    )


# Export logger functions
log_debug = logger.debug
log_info = logger.info
log_warning = logger.warning
log_error = logger.error
log_critical = logger.critical
