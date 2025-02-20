"""Layer validation implementation."""

from typing import List, Optional, Set
from ..types.layer import Layer, LayerCollection
from ..types.base import GeometryValidator

class LayerValidator:
    """Validates layer integrity."""
    
    def __init__(self, geometry_validator: Optional[GeometryValidator] = None):
        """Initialize layer validator.
        
        Args:
            geometry_validator: Optional geometry validator
        """
        self.geometry_validator = geometry_validator
        self._errors: List[str] = []
    
    def validate_layer(self, layer: Layer) -> bool:
        """Validate layer data.
        
        Args:
            layer: Layer to validate
            
        Returns:
            True if valid, False otherwise
        """
        self._errors = []
        
        # Check basic layer properties
        if not layer.name:
            self._errors.append("Layer name is required")
            return False
        
        if not layer.geometry:
            self._errors.append("Layer geometry is required")
            return False
        
        # Validate geometry if validator exists
        if self.geometry_validator:
            if not self.geometry_validator.validate(layer.geometry.geometry):
                self._errors.extend(self.geometry_validator.get_validation_errors())
                return False
        
        # Validate operations format if present
        if layer.operations:
            if not self._validate_operations(layer.operations):
                return False
        
        return True
    
    def validate_dependencies(self, collection: LayerCollection) -> bool:
        """Validate layer dependencies.
        
        Args:
            collection: Layer collection to validate
            
        Returns:
            True if valid, False otherwise
        """
        self._errors = []
        
        # Check for missing layers in dependencies
        for layer_name, deps in collection._layer_dependencies.items():
            if layer_name not in collection.layers:
                self._errors.append(f"Dependency references non-existent layer: {layer_name}")
                return False
            
            for dep in deps:
                if dep not in collection.layers:
                    self._errors.append(f"Layer {layer_name} depends on non-existent layer: {dep}")
                    return False
        
        # Check for cycles
        try:
            collection.get_processing_order()
        except ValueError:
            self._errors.append("Circular dependency detected in layers")
            return False
        
        return True
    
    def validate_operation_sequence(self, layer: Layer, available_operations: Set[str]) -> bool:
        """Validate operation sequence for a layer.
        
        Args:
            layer: Layer to validate
            available_operations: Set of available operation names
            
        Returns:
            True if valid, False otherwise
        """
        self._errors = []
        
        for op in layer.operations:
            # Check operation type
            if 'type' not in op:
                self._errors.append("Operation missing 'type' field")
                return False
            
            op_type = op['type']
            if op_type not in available_operations:
                self._errors.append(f"Unknown operation type: {op_type}")
                return False
            
            # Check parameters format
            if 'parameters' in op and not isinstance(op['parameters'], dict):
                self._errors.append(f"Operation '{op_type}' has invalid parameters format")
                return False
        
        return True
    
    def get_validation_errors(self) -> List[str]:
        """Get validation errors.
        
        Returns:
            List of validation error messages
        """
        return self._errors.copy()
    
    def _validate_operations(self, operations: List[dict]) -> bool:
        """Validate operations list format.
        
        Args:
            operations: List of operation configurations
            
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(operations, list):
            self._errors.append("Operations must be a list")
            return False
        
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                self._errors.append(f"Operation {i} must be a dictionary")
                return False
            
            if 'type' not in op:
                self._errors.append(f"Operation {i} missing 'type' field")
                return False
            
            if not isinstance(op['type'], str):
                self._errors.append(f"Operation {i} 'type' must be a string")
                return False
        
        return True 