"""
Base operation class for layer operations.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ...core.exceptions import ProcessingError


class BaseOperation(ABC):
    """Base class for all layer operations."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the operation.

        Args:
            config: Operation configuration
        """
        self.config = config
        self._geometry_processor = None

    @abstractmethod
    def process(self, layer_name: str, geometry: Optional[object] = None) -> object:
        """
        Process the operation.

        Args:
            layer_name: Name of the layer being processed
            geometry: Input geometry to process

        Returns:
            Processed geometry
        """
        pass

    def validate_config(self) -> bool:
        """
        Validate operation configuration.

        Returns:
            bool: True if configuration is valid
        """
        return True

    def get_required_config(self) -> list:
        """
        Get list of required configuration parameters.

        Returns:
            list: List of required parameter names
        """
        return []

    def get_optional_config(self) -> list:
        """
        Get list of optional configuration parameters.

        Returns:
            list: List of optional parameter names
        """
        return []

    def set_geometry_processor(self, processor: object) -> None:
        """
        Set the geometry processor.

        Args:
            processor: Geometry processor instance
        """
        self._geometry_processor = processor

    def get_geometry_processor(self) -> Optional[object]:
        """
        Get the geometry processor.

        Returns:
            Geometry processor instance or None if not set
        """
        return self._geometry_processor
