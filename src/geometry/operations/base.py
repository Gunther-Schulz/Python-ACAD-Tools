"""Base classes for geometry operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Protocol, TypeVar, Generic
from ..types.base import GeometryData, GeometryError
from ..types.layer import Layer, LayerCollection

T = TypeVar('T')  # Type variable for operation parameters
R = TypeVar('R')  # Type variable for operation result

@dataclass
class OperationContext:
    """Context for operation execution."""
    layer_collection: LayerCollection
    current_layer: Layer
    parameters: Dict[str, Any]

class OperationResult(Generic[R]):
    """Result of an operation execution."""
    def __init__(self, success: bool, result: Optional[R] = None, error: Optional[str] = None):
        self.success = success
        self.result = result
        self.error = error

    @classmethod
    def success(cls, result: R) -> 'OperationResult[R]':
        """Create successful result."""
        return cls(success=True, result=result)

    @classmethod
    def failure(cls, error: str) -> 'OperationResult[R]':
        """Create failure result."""
        return cls(success=False, error=error)

class OperationValidator(Protocol[T]):
    """Protocol for operation parameter validation."""
    def validate(self, params: T) -> bool: ...
    def get_validation_errors(self) -> List[str]: ...

class Operation(ABC, Generic[T, R]):
    """Base class for all geometry operations."""
    
    def __init__(self, validator: Optional[OperationValidator[T]] = None):
        self.validator = validator
        
    @abstractmethod
    def execute(self, context: OperationContext) -> OperationResult[R]:
        """Execute the operation."""
        pass
    
    def validate(self, params: T) -> bool:
        """Validate operation parameters."""
        if self.validator:
            return self.validator.validate(params)
        return True  # No validation by default

    def get_validation_errors(self) -> List[str]:
        """Get validation errors."""
        if self.validator:
            return self.validator.get_validation_errors()
        return []

class UnaryOperation(Operation[T, GeometryData]):
    """Operation that works on a single geometry."""
    
    @abstractmethod
    def process_geometry(self, geometry: GeometryData, params: T) -> GeometryData:
        """Process single geometry."""
        pass
    
    def execute(self, context: OperationContext) -> OperationResult[GeometryData]:
        """Execute unary operation."""
        try:
            if not self.validate(context.parameters):
                return OperationResult.failure(
                    f"Invalid parameters: {', '.join(self.get_validation_errors())}"
                )
            
            result = self.process_geometry(
                context.current_layer.geometry,
                context.parameters
            )
            
            return OperationResult.success(result)
            
        except GeometryError as e:
            return OperationResult.failure(str(e))
        except Exception as e:
            return OperationResult.failure(f"Operation failed: {str(e)}")

class BinaryOperation(Operation[T, GeometryData]):
    """Operation that works on two geometries."""
    
    @abstractmethod
    def process_geometries(
        self,
        geometry1: GeometryData,
        geometry2: GeometryData,
        params: T
    ) -> GeometryData:
        """Process two geometries."""
        pass
    
    def execute(self, context: OperationContext) -> OperationResult[GeometryData]:
        """Execute binary operation."""
        try:
            if not self.validate(context.parameters):
                return OperationResult.failure(
                    f"Invalid parameters: {', '.join(self.get_validation_errors())}"
                )
            
            # Get second geometry from layer collection
            second_layer_name = context.parameters.get('second_layer')
            if not second_layer_name:
                return OperationResult.failure("Second layer name not provided")
            
            second_layer = context.layer_collection.layers.get(second_layer_name)
            if not second_layer:
                return OperationResult.failure(f"Layer not found: {second_layer_name}")
            
            result = self.process_geometries(
                context.current_layer.geometry,
                second_layer.geometry,
                context.parameters
            )
            
            return OperationResult.success(result)
            
        except GeometryError as e:
            return OperationResult.failure(str(e))
        except Exception as e:
            return OperationResult.failure(f"Operation failed: {str(e)}")

class MultiOperation(Operation[T, List[GeometryData]]):
    """Operation that works on multiple geometries."""
    
    @abstractmethod
    def process_geometries(
        self,
        geometries: List[GeometryData],
        params: T
    ) -> List[GeometryData]:
        """Process multiple geometries."""
        pass
    
    def execute(self, context: OperationContext) -> OperationResult[List[GeometryData]]:
        """Execute multi-geometry operation."""
        try:
            if not self.validate(context.parameters):
                return OperationResult.failure(
                    f"Invalid parameters: {', '.join(self.get_validation_errors())}"
                )
            
            # Get all required geometries
            layer_names = context.parameters.get('layers', [])
            if not layer_names:
                return OperationResult.failure("No layer names provided")
            
            geometries = []
            for name in layer_names:
                layer = context.layer_collection.layers.get(name)
                if not layer:
                    return OperationResult.failure(f"Layer not found: {name}")
                geometries.append(layer.geometry)
            
            result = self.process_geometries(geometries, context.parameters)
            
            return OperationResult.success(result)
            
        except GeometryError as e:
            return OperationResult.failure(str(e))
        except Exception as e:
            return OperationResult.failure(f"Operation failed: {str(e)}") 