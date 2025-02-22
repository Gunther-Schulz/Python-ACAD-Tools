# Logging Guidelines

## Overview

This document outlines the logging standards and practices for the Python ACAD Tools project. It provides guidelines for consistent, effective logging across all components.

## Related Documents
- [Code Quality Guidelines](CODE_QUALITY.md) - General code quality standards
- [Boundaries](BOUNDARIES.md) - Component boundary rules
- [Testing Guidelines](TESTING.md) - Testing requirements

## Version Applicability
- Python Version: 3.12+
- Last Updated: 2024-02-22
- Status: Draft

## Dependencies
- Python's `logging` module
- `loguru` for enhanced logging
- Component logging configurations

## Logging Standards

### 1. Log Levels

Use appropriate log levels for different types of information:

```python
# ERROR - For errors that prevent normal operation
logger.error("Failed to process layer: %s", layer_name, exc_info=exception)

# WARNING - For concerning but non-fatal issues
logger.warning("Layer %s has invalid style reference", layer_name)

# INFO - For tracking normal operation
logger.info("Processing layer: %s", layer_name)

# DEBUG - For detailed troubleshooting
logger.debug("Layer %s processing state: %s", layer_name, state)
```

### 2. Log Message Format

Standard log message format:
```python
"%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
```

Example output:
```
2024-02-22 10:15:30,123 - geometry_manager - INFO - layer.py:45 - Processing layer: base_layer
```

### 3. Component Logging

Each component should:
1. Use a component-specific logger
2. Follow consistent naming
3. Configure appropriate levels
4. Handle errors properly

Example:
```python
# In geometry/manager.py
import logging

logger = logging.getLogger("geometry_manager")

class GeometryManager:
    def process_layer(self, name: str) -> None:
        try:
            logger.info("Processing layer: %s", name)
            # Processing logic
            logger.debug("Layer %s state: %s", name, self._get_state(name))
        except Exception as e:
            logger.error("Failed to process layer %s", name, exc_info=e)
            raise
```

### 4. Error Logging

Error logging must include:
1. Clear error message
2. Exception information
3. Relevant context
4. Stack trace when appropriate

Example:
```python
try:
    process_geometry(layer)
except GeometryError as e:
    logger.error(
        "Geometry processing failed for layer %s: %s",
        layer.name,
        str(e),
        exc_info=e,
        extra={
            "layer_id": layer.id,
            "operation": current_operation,
            "state": processing_state
        }
    )
    raise
```

### 5. Performance Logging

For performance-sensitive operations:
1. Log timing information
2. Track resource usage
3. Monitor thresholds
4. Log optimization attempts

Example:
```python
import time
from contextlib import contextmanager

@contextmanager
def log_timing(operation: str) -> None:
    """Log operation timing."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        logger.info("%s completed in %.3f seconds", operation, duration)

def process_large_geometry(geometry: GeometryData) -> None:
    with log_timing("large_geometry_processing"):
        # Processing logic
```

### 6. Configuration

Standard logging configuration:
```python
def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Path | None = None,
    format_string: str | None = None
) -> logging.Logger:
    """Set up component logger.

    Args:
        name: Logger name
        level: Log level
        log_file: Optional log file path
        format_string: Optional format string

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(format_string))
    logger.addHandler(console)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(str(log_file))
        file_handler.setFormatter(logging.Formatter(format_string))
        logger.addHandler(file_handler)

    return logger
```

### 7. Testing and Validation

Logging tests should verify:
1. Correct log levels
2. Message format
3. Error handling
4. Performance logging

Example:
```python
def test_error_logging(caplog):
    """Test error logging configuration."""
    with caplog.at_level(logging.ERROR):
        with pytest.raises(GeometryError):
            process_invalid_geometry()

        assert "Failed to process geometry" in caplog.text
        assert "GeometryError" in caplog.text
        assert "layer_id" in caplog.text
```

## Best Practices

### 1. Message Content
- Be specific and clear
- Include relevant context
- Use string formatting
- Avoid sensitive data

### 2. Performance Impact
- Log appropriate amount
- Use debug for details
- Batch logging when needed
- Monitor log size

### 3. Error Context
- Log full error context
- Include state information
- Track error chains
- Enable debugging

### 4. Security
- No sensitive data
- No credentials
- No personal information
- Sanitize user input

## Implementation Examples

### 1. Component Logger
```python
# src/geometry/manager.py
import logging
from typing import Any

logger = logging.getLogger("geometry_manager")

class GeometryManager:
    def __init__(self) -> None:
        self.logger = logger.getChild("instance")
        self.logger.info("Initializing geometry manager")

    def process_layer(self, name: str) -> None:
        self.logger.info("Processing layer: %s", name)
        try:
            # Processing logic
            self.logger.debug("Layer processed successfully")
        except Exception as e:
            self.logger.error("Processing failed", exc_info=e)
            raise
```

### 2. Error Tracking
```python
# src/core/error_handler.py
from typing import Any

def log_exception(
    logger: logging.Logger,
    message: str,
    exc: Exception,
    **context: Any
) -> None:
    """Log exception with context."""
    logger.error(
        message,
        exc_info=exc,
        extra={"context": context} if context else None
    )
```

### 3. Performance Monitoring
```python
# src/core/monitoring.py
import time
from typing import Any, Generator

class PerformanceLogger:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.timings: dict[str, float] = {}

    @contextmanager
    def measure(self, operation: str) -> Generator[None, None, None]:
        """Measure and log operation timing."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.timings[operation] = duration
            self.logger.info(
                "%s completed in %.3f seconds",
                operation,
                duration
            )
```

## Logging Configuration

### 1. Project Configuration
```yaml
# logging.yaml
version: 1
formatters:
  standard:
    format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  detailed:
    format: "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
handlers:
  console:
    class: logging.StreamHandler
    formatter: standard
    level: INFO
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: detailed
    filename: ${LOG_FILE}
    maxBytes: 10485760
    backupCount: 5
loggers:
  geometry_manager:
    level: INFO
    handlers: [console, file]
  export_manager:
    level: INFO
    handlers: [console, file]
```

### 2. Runtime Configuration
```python
# src/core/logging.py
import yaml
from pathlib import Path

def configure_logging(config_path: Path) -> None:
    """Configure logging from YAML."""
    with open(config_path) as f:
        config = yaml.safe_load(f)
    logging.config.dictConfig(config)
```

## Troubleshooting

### 1. Common Issues
- Missing handlers
- Incorrect levels
- Format errors
- Permission issues

### 2. Solutions
- Verify configuration
- Check permissions
- Monitor log size
- Rotate logs

## Version History

| Version | Date | Changes | Status |
|---------|------|---------|--------|
| 0.1.0   | 2024-02-22 | Initial logging guidelines | Draft |
