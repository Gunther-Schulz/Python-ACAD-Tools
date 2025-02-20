"""DXF layer management."""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from src.core.utils import setup_logger

@dataclass
class LayerManager:
    """Manages DXF layers."""
    
    def __init__(self):
        """Initialize layer manager."""
        self.logger = setup_logger("layer_manager")
        self.layers: Dict[str, Any] = {}
    
    def create_layer(self, doc: Any, layer_name: str, properties: Optional[Dict[str, Any]] = None) -> Any:
        """Create a new layer in the DXF document.
        
        Args:
            doc: DXF document
            layer_name: Name of the layer to create
            properties: Optional layer properties
            
        Returns:
            Created layer object
        """
        if layer_name in doc.layers:
            layer = doc.layers.get(layer_name)
        else:
            layer = doc.layers.new(name=layer_name)
            self.logger.debug(f"Created new layer: {layer_name}")
        
        if properties:
            self.apply_properties(layer, properties)
        
        self.layers[layer_name] = layer
        return layer
    
    def apply_properties(self, layer: Any, properties: Dict[str, Any]) -> None:
        """Apply properties to a layer.
        
        Args:
            layer: Layer object
            properties: Properties to apply
        """
        for key, value in properties.items():
            if hasattr(layer.dxf, key):
                setattr(layer.dxf, key, value)
                self.logger.debug(f"Applied property {key}={value} to layer {layer.dxf.name}")
    
    def ensure_layer_exists(self, doc: Any, layer_name: str, properties: Optional[Dict[str, Any]] = None) -> Any:
        """Ensure a layer exists, creating it if necessary.
        
        Args:
            doc: DXF document
            layer_name: Name of the layer
            properties: Optional layer properties
            
        Returns:
            Layer object
        """
        if layer_name not in self.layers:
            return self.create_layer(doc, layer_name, properties)
        return self.layers[layer_name]
    
    def apply_layer(self, entity: Any, layer_name: str) -> None:
        """Apply layer to DXF entity.
        
        Args:
            entity: DXF entity
            layer_name: Name of the layer to apply
        """
        if hasattr(entity, 'dxf'):
            entity.dxf.layer = layer_name
            self.logger.debug(f"Applied layer {layer_name} to entity") 