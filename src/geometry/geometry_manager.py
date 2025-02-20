"""Geometry processing manager."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
from .layers.manager import LayerManager
from .layers.processor import LayerProcessor
from .layers.validator import LayerValidator
from .types.layer import Layer, LayerCollection
from .types.base import GeometryData, GeometryMetadata
from .operations.buffer import BufferOperation
from src.config.geometry_layer_config import GeometryLayerConfig

@dataclass
class GeometryLayer:
    """A geometry layer with its attributes."""
    name: str
    update_dxf: bool
    style: Optional[str]

class GeometryManager:
    """Manages geometry processing pipeline."""
    
    def __init__(self, config: List[GeometryLayerConfig]):
        """Initialize with configuration.
        
        Args:
            config: List of geometry layer configurations
        """
        self.config = config
        
        # Initialize layer infrastructure
        self.layer_collection = LayerCollection()
        self.layer_validator = LayerValidator()
        self.layer_manager = LayerManager(
            layer_collection=self.layer_collection,
            validator=self.layer_validator
        )
        self.layer_processor = LayerProcessor(
            layer_manager=self.layer_manager,
            validator=self.layer_validator
        )
        
        # Register available operations
        self._register_operations()
        
        # Load layers from configuration
        self._load_layers()
    
    def _register_operations(self) -> None:
        """Register available geometry operations."""
        # Register buffer operation
        self.layer_processor.register_operation("buffer", BufferOperation())
        # TODO: Register other operations as they are implemented
    
    def _load_layers(self) -> None:
        """Load layers from configuration."""
        for layer_config in self.config:
            # Create layer with basic attributes
            layer = self.layer_manager.create_layer(
                name=layer_config.name,
                geometry=GeometryData(
                    id=layer_config.name,
                    geometry=None,  # Will be loaded when processing
                    metadata=GeometryMetadata(source_type='config')
                ),
                update_dxf=layer_config.update_dxf,
                style_id=layer_config.style,
                operations=[op.to_dict() for op in layer_config.operations] if layer_config.operations else []
            )
    
    def get_layer_names(self) -> List[str]:
        """Get list of layer names.
        
        Returns:
            List of layer names in processing order
        """
        return self.layer_collection.get_processing_order()
    
    def get_layer(self, layer_name: str) -> Layer:
        """Get a layer by name.
        
        Args:
            layer_name: Name of the layer
            
        Returns:
            Layer instance
            
        Raises:
            KeyError: If layer doesn't exist
        """
        return self.layer_manager.get_layer(layer_name)
    
    def process_layer(self, layer_name: str) -> GeometryLayer:
        """Process a single layer.
        
        Args:
            layer_name: Name of the layer to process
            
        Returns:
            Processed geometry layer
            
        Raises:
            GeometryError: If processing fails
        """
        # Get layer
        layer = self.get_layer(layer_name)
        
        # Process layer operations
        self.layer_processor.process_layer(layer_name)
        
        # Return processed layer info
        return GeometryLayer(
            name=layer.name,
            update_dxf=layer.update_dxf,
            style=layer.style_id
        )
    
    def get_layer_progress(self, layer_name: str) -> Dict[str, Any]:
        """Get processing progress for a layer.
        
        Args:
            layer_name: Name of the layer
            
        Returns:
            Dictionary with processing progress information
        """
        return self.layer_processor.get_layer_progress(layer_name)
    
    def get_layer_errors(self, layer_name: str) -> List[str]:
        """Get errors for a layer.
        
        Args:
            layer_name: Name of the layer
            
        Returns:
            List of error messages
        """
        return self.layer_processor.get_layer_errors(layer_name) 