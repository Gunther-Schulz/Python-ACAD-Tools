"""
Buffer operation for layer processing.
"""
from typing import Dict, Any, Optional
from ...core.exceptions import ProcessingError
from .base import BaseOperation


class BufferOperation(BaseOperation):
    """Creates a buffer around a geometry."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the buffer operation.

        Args:
            config: Operation configuration
        """
        super().__init__(config)
        self.distance = config.get('distance', 0.0)
        self.mode = config.get('mode', 'round')
        self.join_style = config.get('join_style', 'round')

    def process(self, layer_name: str, geometry: Optional[object] = None) -> object:
        """
        Process the buffer operation.

        Args:
            layer_name: Name of the layer being processed
            geometry: Input geometry to process

        Returns:
            Buffered geometry
        """
        if geometry is None:
            raise ProcessingError("No geometry provided for buffer operation")

        geometry_processor = self.get_geometry_processor()
        if geometry_processor is None:
            raise ProcessingError("Geometry processor not set")

        try:
            return geometry_processor.create_buffer(
                geometry,
                distance=self.distance,
                mode=self.mode,
                join_style=self.join_style
            )
        except Exception as e:
            raise ProcessingError(f"Error creating buffer: {str(e)}")

    def validate_config(self) -> bool:
        """
        Validate operation configuration.

        Returns:
            bool: True if configuration is valid
        """
        if 'distance' not in self.config:
            return False
        return True

    def get_required_config(self) -> list:
        """
        Get list of required configuration parameters.

        Returns:
            list: List of required parameter names
        """
        return ['distance']

    def get_optional_config(self) -> list:
        """
        Get list of optional configuration parameters.

        Returns:
            list: List of optional parameter names
        """
        return ['mode', 'join_style']

    def _get_geometry_processor(self) -> Optional[object]:
        """
        Get the geometry processor instance.

        Returns:
            Geometry processor instance or None if not available
        """
        # This should be implemented to get the geometry processor from the layer processor
        # For now, return None
        return None
