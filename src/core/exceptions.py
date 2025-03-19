"""
Custom exceptions for the OLADPP core module.
"""

class OLADPPError(Exception):
    """Base exception for all OLADPP errors."""
    pass

class ProjectError(OLADPPError):
    """Raised when there are issues with project configuration or loading."""
    pass

class ProcessingError(OLADPPError):
    """Raised when there are issues during data processing."""
    pass

class ValidationError(OLADPPError):
    """Raised when there are validation issues with configuration or data."""
    pass

class ExportError(OLADPPError):
    """Raised when there are issues during data export."""
    pass

class ConfigurationError(OLADPPError):
    """Raised when there are issues with application configuration."""
    pass
