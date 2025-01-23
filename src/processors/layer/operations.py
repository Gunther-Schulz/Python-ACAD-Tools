from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from ...utils.logging import get_logger

logger = get_logger(__name__)

class LayerOperation(ABC):
    """Base class for layer operations."""
    
    @abstractmethod
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        """Execute the operation.
        
        Args:
            doc: DXF document
            msp: Modelspace
            layer_name: Name of the layer to operate on
            params: Operation parameters
            
        Raises:
            ValueError: If operation fails
        """
        pass

class CopyOperation(LayerOperation):
    """Copy entities from one or more layers."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            source_layers = params.get('layers', [])
            if not source_layers:
                raise ValueError("No source layers specified")
            
            # Get entities from source layers
            for source_layer in source_layers:
                if source_layer not in doc.layers:
                    logger.warning(f"Source layer not found: {source_layer}")
                    continue
                
                # Copy entities
                for entity in msp.query(f'*[layer=="{source_layer}"]'):
                    try:
                        new_entity = msp.add_entity(entity.dxf.dxftype)
                        new_entity.dxf.update(entity.dxf.all_existing_dxf_attribs())
                        new_entity.dxf.layer = layer_name
                    except Exception as e:
                        logger.warning(f"Failed to copy entity: {e}")
            
            logger.info(f"Copied entities to layer: {layer_name}")
            
        except Exception as e:
            raise ValueError(f"Error in copy operation: {e}") from e

class BufferOperation(LayerOperation):
    """Create buffer around geometries."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            distance = params.get('distance', 0.0)
            mode = params.get('mode', 'outer')
            join_style = params.get('joinStyle', 'round')
            
            # Get entities from layer
            entities = list(msp.query(f'*[layer=="{layer_name}"]'))
            
            # Create buffers
            for entity in entities:
                try:
                    # Convert entity to shapely geometry
                    # Apply buffer
                    # Convert back to DXF
                    # Add to layer
                    pass  # TODO: Implement buffer logic
                except Exception as e:
                    logger.warning(f"Failed to buffer entity: {e}")
            
            logger.info(f"Created buffers in layer: {layer_name}")
            
        except Exception as e:
            raise ValueError(f"Error in buffer operation: {e}") from e

class DifferenceOperation(LayerOperation):
    """Create difference between layers."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            layers = params.get('layers', [])
            if len(layers) < 2:
                raise ValueError("At least two layers required for difference operation")
            
            # Get entities from layers
            # Convert to shapely geometries
            # Apply difference
            # Convert back to DXF
            # Add to layer
            pass  # TODO: Implement difference logic
            
        except Exception as e:
            raise ValueError(f"Error in difference operation: {e}") from e

class IntersectionOperation(LayerOperation):
    """Create intersection between layers."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            layers = params.get('layers', [])
            if len(layers) < 2:
                raise ValueError("At least two layers required for intersection operation")
            
            # Get entities from layers
            # Convert to shapely geometries
            # Apply intersection
            # Convert back to DXF
            # Add to layer
            pass  # TODO: Implement intersection logic
            
        except Exception as e:
            raise ValueError(f"Error in intersection operation: {e}") from e

class FilterOperation(LayerOperation):
    """Filter entities based on criteria."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            values = params.get('values', [])
            if not values:
                raise ValueError("No filter values specified")
            
            # Get entities from layer
            # Apply filter criteria
            # Keep or remove entities based on filter
            pass  # TODO: Implement filter logic
            
        except Exception as e:
            raise ValueError(f"Error in filter operation: {e}") from e

class MergeOperation(LayerOperation):
    """Merge multiple layers into one."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            source_layers = params.get('layers', [])
            if not source_layers:
                raise ValueError("No source layers specified")
            
            # Copy entities from all source layers
            for source_layer in source_layers:
                if source_layer not in doc.layers:
                    logger.warning(f"Source layer not found: {source_layer}")
                    continue
                
                for entity in msp.query(f'*[layer=="{source_layer}"]'):
                    try:
                        new_entity = msp.add_entity(entity.dxf.dxftype)
                        new_entity.dxf.update(entity.dxf.all_existing_dxf_attribs())
                        new_entity.dxf.layer = layer_name
                    except Exception as e:
                        logger.warning(f"Failed to merge entity: {e}")
            
            logger.info(f"Merged layers into: {layer_name}")
            
        except Exception as e:
            raise ValueError(f"Error in merge operation: {e}") from e

class SmoothOperation(LayerOperation):
    """Smooth geometries in layer."""
    
    def execute(self, doc: Drawing, msp: Modelspace, layer_name: str, params: Dict[str, Any]) -> None:
        try:
            strength = params.get('strength', 1.0)
            
            # Get entities from layer
            # Apply smoothing algorithm
            # Update or replace entities
            pass  # TODO: Implement smooth logic
            
        except Exception as e:
            raise ValueError(f"Error in smooth operation: {e}") from e

class OperationManager:
    """Manages layer operations."""
    
    def __init__(self):
        """Initialize operation manager."""
        self._operations: Dict[str, Type[LayerOperation]] = {
            'copy': CopyOperation,
            'buffer': BufferOperation,
            'difference': DifferenceOperation,
            'intersection': IntersectionOperation,
            'filter': FilterOperation,
            'merge': MergeOperation,
            'smooth': SmoothOperation
        }
    
    def register_operation(self, name: str, operation_class: Type[LayerOperation]) -> None:
        """Register a new operation type.
        
        Args:
            name: Name of the operation
            operation_class: Operation class to register
        """
        self._operations[name] = operation_class
        logger.debug(f"Registered operation: {name}")
    
    def get_operation(self, name: str) -> Optional[Type[LayerOperation]]:
        """Get operation class by name.
        
        Args:
            name: Name of the operation
            
        Returns:
            Operation class or None if not found
        """
        return self._operations.get(name)
    
    def execute_operation(self, op_type: str, doc: Drawing, msp: Modelspace,
                         layer_name: str, params: Dict[str, Any]) -> None:
        """Execute an operation.
        
        Args:
            op_type: Type of operation to execute
            doc: DXF document
            msp: Modelspace
            layer_name: Name of the layer to operate on
            params: Operation parameters
            
        Raises:
            ValueError: If operation type not found or execution fails
        """
        operation_class = self.get_operation(op_type)
        if not operation_class:
            raise ValueError(f"Unknown operation type: {op_type}")
        
        try:
            operation = operation_class()
            operation.execute(doc, msp, layer_name, params)
        except Exception as e:
            raise ValueError(f"Failed to execute operation '{op_type}': {e}") from e 