"""Layer management implementation."""

from typing import Dict, Any, Optional, List
from ..types.layer import Layer, LayerCollection
from ..types.base import GeometryData, GeometryError, InvalidGeometryError
from .validator import LayerValidator

class LayerManager:
    """Manages layer lifecycle and state."""
    
    def __init__(self, layer_collection: LayerCollection, validator: Optional[LayerValidator] = None):
        """Initialize layer manager.
        
        Args:
            layer_collection: Collection of layers to manage
            validator: Optional layer validator
        """
        self.layers = layer_collection
        self.validator = validator
        self._processing_states: Dict[str, Dict[str, Any]] = {}
    
    def create_layer(
        self,
        name: str,
        geometry: GeometryData,
        update_dxf: bool = False,
        style_id: Optional[str] = None,
        operations: Optional[List[Dict[str, Any]]] = None
    ) -> Layer:
        """Create and add a new layer.
        
        Args:
            name: Layer name
            geometry: Layer geometry data
            update_dxf: Whether to update DXF
            style_id: Optional style ID
            operations: Optional list of operations
            
        Returns:
            Created layer
            
        Raises:
            GeometryError: If layer creation fails
        """
        # Validate name uniqueness
        if name in self.layers.layers:
            raise GeometryError(f"Layer already exists: {name}")
        
        # Create layer
        layer = Layer(
            name=name,
            geometry=geometry,
            update_dxf=update_dxf,
            style_id=style_id,
            operations=operations or []
        )
        
        # Validate if validator exists
        if self.validator and not self.validator.validate_layer(layer):
            raise InvalidGeometryError(
                f"Invalid layer: {', '.join(self.validator.get_validation_errors())}"
            )
        
        # Add to collection
        self.layers.add_layer(layer)
        
        # Initialize processing state
        self._processing_states[name] = {
            'processed_operations': [],
            'current_operation': None,
            'errors': []
        }
        
        return layer
    
    def update_layer(
        self,
        name: str,
        geometry: Optional[GeometryData] = None,
        update_dxf: Optional[bool] = None,
        style_id: Optional[str] = None,
        operations: Optional[List[Dict[str, Any]]] = None
    ) -> Layer:
        """Update an existing layer.
        
        Args:
            name: Layer name
            geometry: Optional new geometry
            update_dxf: Optional new update_dxf flag
            style_id: Optional new style ID
            operations: Optional new operations list
            
        Returns:
            Updated layer
            
        Raises:
            KeyError: If layer doesn't exist
            GeometryError: If update fails
        """
        # Get existing layer
        layer = self.get_layer(name)
        
        # Update fields if provided
        if geometry is not None:
            layer.geometry = geometry
        if update_dxf is not None:
            layer.update_dxf = update_dxf
        if style_id is not None:
            layer.style_id = style_id
        if operations is not None:
            layer.operations = operations
        
        # Validate if validator exists
        if self.validator and not self.validator.validate_layer(layer):
            raise InvalidGeometryError(
                f"Invalid layer after update: {', '.join(self.validator.get_validation_errors())}"
            )
        
        return layer
    
    def delete_layer(self, name: str) -> None:
        """Delete a layer.
        
        Args:
            name: Layer name to delete
            
        Raises:
            KeyError: If layer doesn't exist
        """
        # Remove from collection (will raise KeyError if not found)
        self.layers.remove_layer(name)
        
        # Clean up processing state
        if name in self._processing_states:
            del self._processing_states[name]
    
    def get_layer(self, name: str) -> Layer:
        """Get a layer by name.
        
        Args:
            name: Layer name
            
        Returns:
            Layer instance
            
        Raises:
            KeyError: If layer doesn't exist
        """
        if name not in self.layers.layers:
            raise KeyError(f"Layer not found: {name}")
        return self.layers.layers[name]
    
    def add_dependency(self, dependent: str, dependency: str) -> None:
        """Add a dependency between layers.
        
        Args:
            dependent: Dependent layer name
            dependency: Dependency layer name
            
        Raises:
            KeyError: If either layer doesn't exist
            ValueError: If dependency would create a cycle
        """
        self.layers.add_dependency(dependent, dependency)
        
        # Validate no cycles were created
        try:
            self.layers.get_processing_order()
        except ValueError as e:
            # Remove the dependency we just added
            self.layers._layer_dependencies[dependent].remove(dependency)
            raise ValueError("Adding dependency would create a cycle") from e
    
    def get_processing_state(self, name: str) -> Dict[str, Any]:
        """Get processing state for a layer.
        
        Args:
            name: Layer name
            
        Returns:
            Processing state dictionary
            
        Raises:
            KeyError: If layer doesn't exist
        """
        if name not in self._processing_states:
            raise KeyError(f"No processing state for layer: {name}")
        return self._processing_states[name]
    
    def update_processing_state(
        self,
        name: str,
        operation: Optional[str] = None,
        completed: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """Update processing state for a layer.
        
        Args:
            name: Layer name
            operation: Optional current operation name
            completed: Optional completed operation name
            error: Optional error message
            
        Raises:
            KeyError: If layer doesn't exist
        """
        state = self.get_processing_state(name)
        
        if operation is not None:
            state['current_operation'] = operation
        
        if completed is not None:
            state['processed_operations'].append(completed)
            if state['current_operation'] == completed:
                state['current_operation'] = None
        
        if error is not None:
            state['errors'].append(error)
            state['current_operation'] = None 