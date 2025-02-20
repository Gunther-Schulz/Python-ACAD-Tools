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

@dataclass
class GeometryLayer:
    """A geometry layer with its attributes."""
    name: str
    update_dxf: bool
    style: Optional[str]

class GeometryManager:
    """Manages geometry processing pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration.
        
        Args:
            config: Dictionary containing geometry layer configurations
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
        geom_layers = self.config.get('geomLayers', [])
        
        for layer_config in geom_layers:
            name = layer_config.get('name')
            if not name:
                continue
                
            # Create layer with basic attributes
            layer = self.layer_manager.create_layer(
                name=name,
                geometry=GeometryData(
                    id=name,
                    geometry=None,  # Will be loaded when processing
                    metadata=GeometryMetadata(source_type='config')
                ),
                update_dxf=layer_config.get('updateDxf', False),
                style_id=layer_config.get('style'),
                operations=layer_config.get('operations', [])
            )
            
            # Add dependencies if specified
            if 'dependencies' in layer_config:
                for dep in layer_config['dependencies']:
                    self.layer_manager.add_dependency(name, dep)
    
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