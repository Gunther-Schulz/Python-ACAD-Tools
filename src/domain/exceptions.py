"""Custom exception classes for the application."""


class ApplicationBaseException(Exception):
    """Base exception class for all application-specific exceptions."""
    pass


class ConfigError(ApplicationBaseException):
    """Raised when there's an error in configuration loading or validation."""
    pass


class ProcessingError(ApplicationBaseException):
    """Raised when there's a general error during data processing."""
    pass


class DXFProcessingError(ProcessingError):
    """Raised when there's an error specific to DXF file processing."""
    pass


class GeometryError(ProcessingError):
    """Raised when there's an error during geometry operations."""
    pass


class DataSourceError(ProcessingError):
    """Raised when there's an error accessing or loading data sources."""
    pass

