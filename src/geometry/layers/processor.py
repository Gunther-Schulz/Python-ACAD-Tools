"""Layer processing implementation."""

from typing import Dict, Any, Optional, Set, Type, Union
from ..types.layer import Layer, LayerCollection
from ..types.base import GeometryError, GeometryOperationError
from ..operations.base import Operation, OperationContext, OperationResult
from .manager import LayerManager
from .validator import LayerValidator

class LayerProcessor:
    """Processes operations on layers."""
    
    def __init__(
        self,
        layer_manager: LayerManager,
        validator: Optional[LayerValidator] = None
    ):
        """Initialize layer processor.
        
        Args:
            layer_manager: Layer manager instance
            validator: Optional layer validator
        """
        self.layer_manager = layer_manager
        self.validator = validator
        self._operations: Dict[str, Operation] = {}
    
    def register_operation(self, name: str, operation: Operation) -> None:
        """Register an operation.
        
        Args:
            name: Operation name
            operation: Operation instance
            
        Raises:
            ValueError: If operation already registered
        """
        if name in self._operations:
            raise ValueError(f"Operation already registered: {name}")
        self._operations[name] = operation
    
    def get_available_operations(self) -> Set[str]:
        """Get set of available operation names.
        
        Returns:
            Set of operation names
        """
        return set(self._operations.keys())
    
    def process_layer(self, layer_name_or_layer: Union[str, Layer]) -> None:
        """Process all operations for a layer.
        
        Args:
            layer_name_or_layer: Name of layer to process or Layer instance
            
        Raises:
            KeyError: If layer doesn't exist
            GeometryError: If processing fails
        """
        # Get layer name and instance
        if isinstance(layer_name_or_layer, Layer):
            layer = layer_name_or_layer
            layer_name = layer.name
        else:
            layer_name = layer_name_or_layer
            layer = self.layer_manager.get_layer(layer_name)
        
        # Validate operation sequence if validator exists
        if self.validator:
            if not self.validator.validate_operation_sequence(
                layer,
                self.get_available_operations()
            ):
                raise GeometryError(
                    f"Invalid operation sequence: {', '.join(self.validator.get_validation_errors())}"
                )
        
        # Process each operation
        for op_config in layer.operations:
            op_type = op_config['type']
            
            # Get operation
            if op_type not in self._operations:
                raise GeometryError(f"Unknown operation type: {op_type}")
            operation = self._operations[op_type]
            
            # Update processing state
            self.layer_manager.update_processing_state(
                layer_name,
                operation=op_type
            )
            
            try:
                # Create operation context
                context = OperationContext(
                    layer_collection=self.layer_manager.layers,
                    current_layer=layer,
                    parameters=op_config.get('parameters', {})
                )
                
                # Execute operation
                result = operation.execute(context)
                
                # Handle result
                if not result.success:
                    raise GeometryOperationError(
                        f"Operation '{op_type}' failed: {result.error}"
                    )
                
                # Update layer with operation result
                if isinstance(result.result, list):
                    # Multi-operation result
                    if len(result.result) != 1:
                        raise GeometryError(
                            f"Operation '{op_type}' returned multiple results, expected one"
                        )
                    layer.geometry = result.result[0]
                else:
                    # Single operation result
                    layer.geometry = result.result
                
                # Update processing state
                self.layer_manager.update_processing_state(
                    layer_name,
                    completed=op_type
                )
                
                # Add to operation log
                layer.add_operation_log(op_type, **op_config.get('parameters', {}))
                
            except Exception as e:
                # Update processing state with error
                self.layer_manager.update_processing_state(
                    layer_name,
                    error=str(e)
                )
                raise
    
    def process_layers(self) -> None:
        """Process all layers in dependency order.
        
        Raises:
            GeometryError: If processing fails
        """
        try:
            # Get processing order
            order = self.layer_manager.layers.get_processing_order()
            
            # Process each layer
            for layer_name in order:
                self.process_layer(layer_name)
                
        except Exception as e:
            raise GeometryError(f"Layer processing failed: {str(e)}")
    
    def get_layer_errors(self, layer_name: str) -> list[str]:
        """Get errors for a layer.
        
        Args:
            layer_name: Layer name
            
        Returns:
            List of error messages
            
        Raises:
            KeyError: If layer doesn't exist
        """
        state = self.layer_manager.get_processing_state(layer_name)
        return state['errors']
    
    def get_layer_progress(self, layer_name: str) -> Dict[str, Any]:
        """Get processing progress for a layer.
        
        Args:
            layer_name: Layer name
            
        Returns:
            Dictionary with:
                - processed_operations: List of completed operations
                - current_operation: Current operation or None
                - total_operations: Total number of operations
                - errors: List of errors
                
        Raises:
            KeyError: If layer doesn't exist
        """
        layer = self.layer_manager.get_layer(layer_name)
        state = self.layer_manager.get_processing_state(layer_name)
        
        return {
            'processed_operations': state['processed_operations'],
            'current_operation': state['current_operation'],
            'total_operations': len(layer.operations),
            'errors': state['errors']
        } 