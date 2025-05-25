"""Custom exception classes for the application."""
from typing import Optional, List


class ApplicationBaseException(Exception):
    """Base exception class for all application-specific exceptions."""
    pass


class ConfigError(ApplicationBaseException):
    """Raised when there's an error in configuration loading or validation."""
    pass


class ConfigValidationError(ConfigError):
    """Raised when configuration validation fails."""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 config_file: Optional[str] = None, validation_errors: Optional[List[str]] = None):
        super().__init__(message)
        self.field_name = field_name
        self.config_file = config_file
        self.validation_errors = validation_errors or []

    def __str__(self):
        error_details = [str(self.args[0])]
        if self.config_file:
            error_details.append(f"Config file: {self.config_file}")
        if self.field_name:
            error_details.append(f"Field: {self.field_name}")
        if self.validation_errors:
            error_details.append(f"Validation errors: {'; '.join(self.validation_errors)}")
        return "\n".join(error_details)


class ProcessingError(ApplicationBaseException):
    """Raised when there's a general error during data processing."""
    pass


class DXFProcessingError(ProcessingError):
    """Raised when there's an error specific to DXF file processing."""
    pass


class DXFGeometryConversionError(DXFProcessingError):
    """Raised when there's an error converting DXF entities to Shapely geometries."""
    pass


class GeometryError(ProcessingError):
    """Raised when there's an error during geometry operations."""
    pass


class GdfValidationError(ConfigError):
    """Raised when GeoDataFrame validation fails."""
    pass


class DataSourceError(ProcessingError):
    """Raised when there's an error accessing or loading data sources."""
    pass


class PathResolutionError(ApplicationBaseException):
    """Raised when there's an error resolving path aliases or path references."""

    def __init__(self, message: str, alias_reference: Optional[str] = None,
                 project_name: Optional[str] = None):
        super().__init__(message)
        self.alias_reference = alias_reference
        self.project_name = project_name

    def __str__(self):
        error_details = [str(self.args[0])]
        if self.project_name:
            error_details.append(f"Project: {self.project_name}")
        if self.alias_reference:
            error_details.append(f"Alias reference: {self.alias_reference}")
        return "\n".join(error_details)
