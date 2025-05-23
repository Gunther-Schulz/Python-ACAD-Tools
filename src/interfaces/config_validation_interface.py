"""Interface for configuration validation services."""
from typing import Protocol, Dict, Any, List, Optional

from ..domain.exceptions import ConfigValidationError


class IConfigValidation(Protocol):
    """Interface for services that validate configuration data."""

    def validate_project_config(
        self,
        config_data: Dict[str, Any],
        config_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates a complete project configuration.

        Args:
            config_data: The configuration data to validate.
            config_file: Optional path to the config file for error reporting.

        Returns:
            The validated configuration data.

        Raises:
            ConfigValidationError: If validation fails.
        """
        ...

    @property
    def validation_errors(self) -> List[str]:
        """
        Get the list of validation errors from the last validation run.

        Returns:
            List of validation error messages.
        """
        ...
