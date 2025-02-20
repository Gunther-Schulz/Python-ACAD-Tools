"""Layer type definitions."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from .base import GeometryData, GeometryMetadata
from shapely.geometry import base as shapely_base
from src.config.geometry_layer_config import StyleConfig

@dataclass
class Layer:
    """Pure geometry layer representation."""
    name: str
    geometry: GeometryData
    update_dxf: bool = False
    style_id: Optional[str] = None
    inline_style: Optional[StyleConfig] = None
    operations: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def attributes(self) -> Dict[str, Any]:
        """Get layer attributes."""
        return self.geometry.metadata.attributes
    
    @property
    def source_crs(self) -> Optional[str]:
        """Get layer CRS."""
        return self.geometry.metadata.source_crs
    
    def add_operation_log(self, operation_name: str, **params) -> None:
        """Add operation to the processing log."""
        log_entry = f"{operation_name}: {params}"
        self.geometry.metadata.operations_log.append(log_entry)

@dataclass
class LayerCollection:
    """Collection of geometry layers."""
    layers: Dict[str, Layer] = field(default_factory=dict)
    _layer_dependencies: Dict[str, Set[str]] = field(default_factory=dict)
    
    def add_layer(self, layer: Layer) -> None:
        """Add layer to collection."""
        self.layers[layer.name] = layer
        self._layer_dependencies[layer.name] = set()
    
    def remove_layer(self, layer_name: str) -> None:
        """Remove layer from collection."""
        if layer_name in self.layers:
            del self.layers[layer_name]
            del self._layer_dependencies[layer_name]
            # Remove from other layers' dependencies
            for deps in self._layer_dependencies.values():
                deps.discard(layer_name)
    
    def add_dependency(self, dependent: str, dependency: str) -> None:
        """Add layer dependency."""
        if dependent not in self.layers or dependency not in self.layers:
            raise KeyError("Both layers must exist in collection")
        self._layer_dependencies[dependent].add(dependency)
    
    def get_dependencies(self, layer_name: str) -> Set[str]:
        """Get layer dependencies."""
        return self._layer_dependencies.get(layer_name, set())
    
    def get_processing_order(self) -> List[str]:
        """Get layers in dependency order.
        
        Returns:
            List of layer names in processing order. Returns empty list if no layers.
            
        Raises:
            ValueError: If circular dependency detected
        """
        if not self.layers:
            return []
            
        from collections import deque
        
        # Calculate in-degree for each layer
        in_degree = {name: 0 for name in self.layers.keys()}
        
        # For each layer that has dependencies, increment the in-degree of the layers that depend on it
        for layer_name in self.layers.keys():
            for dependent, deps in self._layer_dependencies.items():
                if layer_name in deps:
                    in_degree[dependent] += 1
        
        # Start with layers having no dependencies
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        order = []
        
        while queue:
            name = queue.popleft()
            order.append(name)
            
            # For each layer that depends on the current layer
            for dependent, deps in self._layer_dependencies.items():
                if name in deps:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        if len(order) != len(self.layers):
            raise ValueError("Circular dependency detected in layers")
            
        return order 