# Integration Patterns

## Overview
This document outlines the integration patterns and best practices for connecting components in the Python ACAD Tools project.

## Related Documents
- [Boundaries](BOUNDARIES.md) - Component boundary rules
- [Code Quality Guidelines](CODE_QUALITY.md) - Code quality standards
- [Testing Guidelines](TESTING.md) - Testing requirements
- [INDEX](../INDEX.md) - Documentation index

## Version Applicability
- Python Version: 3.12+
- Last Updated: 2024-02-22
- Status: Draft

## Dependencies
- Dependency injection framework
- Protocol-based interfaces
- Type checking tools
- Testing frameworks

## Integration Principles

### 1. Component Communication
```python
# Example: Component interface definition
from src.core.types import Protocol, GeometryData, Result

class GeometryProcessor(Protocol):
    """Protocol for geometry processing."""
    def process(self, data: GeometryData) -> Result: ...
    def validate(self, data: GeometryData) -> bool: ...
    def cleanup(self) -> None: ...
```

**Requirements**:
- Protocol-based interfaces
- Clear contract boundaries
- Type-safe communication
- Error propagation rules

### 2. Dependency Management
```python
# Example: Dependency container
from dependency_injector import containers, providers
from src.geometry.processor import GeometryProcessor
from src.export.manager import ExportManager

class Container(containers.DeclarativeContainer):
    """Application dependency container."""

    config = providers.Configuration()

    # Core services
    geometry_processor = providers.Singleton(GeometryProcessor)
    export_manager = providers.Singleton(
        ExportManager,
        processor=geometry_processor
    )
```

**Requirements**:
- Centralized dependency management
- Clear dependency direction
- Lifecycle management
- Configuration injection

## Integration Patterns

### 1. Factory Pattern
```python
# Example: Component factory
class GeometryFactory(Protocol):
    """Factory for creating geometry processors."""

    def create_processor(self) -> GeometryProcessor: ...
    def create_validator(self) -> GeometryValidator: ...

class GeometryFactoryImpl:
    """Concrete factory implementation."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def create_processor(self) -> GeometryProcessor:
        return GeometryProcessorImpl(self.config)

    def create_validator(self) -> GeometryValidator:
        return GeometryValidatorImpl(self.config)
```

### 2. Observer Pattern
```python
# Example: Processing events
class ProcessingObserver(Protocol):
    """Observer for processing events."""

    def on_layer_start(self, layer_name: str) -> None: ...
    def on_layer_complete(self, layer_name: str, result: Result) -> None: ...
    def on_error(self, layer_name: str, error: Exception) -> None: ...

class ProcessingManager:
    """Manages processing with observers."""

    def __init__(self) -> None:
        self._observers: list[ProcessingObserver] = []

    def add_observer(self, observer: ProcessingObserver) -> None:
        self._observers.append(observer)

    def process_layer(self, layer_name: str) -> None:
        for observer in self._observers:
            observer.on_layer_start(layer_name)
        try:
            result = self._process(layer_name)
            for observer in self._observers:
                observer.on_layer_complete(layer_name, result)
        except Exception as e:
            for observer in self._observers:
                observer.on_error(layer_name, e)
            raise
```

### 3. Strategy Pattern
```python
# Example: Export strategies
class ExportStrategy(Protocol):
    """Strategy for exporting geometry."""

    def export(self, geometry: GeometryData, path: Path) -> None: ...
    def validate(self, geometry: GeometryData) -> bool: ...

class DXFStrategy(ExportStrategy):
    """DXF export strategy."""

    def export(self, geometry: GeometryData, path: Path) -> None:
        # DXF-specific export logic
        ...

    def validate(self, geometry: GeometryData) -> bool:
        # DXF-specific validation
        ...

class ShapefileStrategy(ExportStrategy):
    """Shapefile export strategy."""

    def export(self, geometry: GeometryData, path: Path) -> None:
        # Shapefile-specific export logic
        ...

    def validate(self, geometry: GeometryData) -> bool:
        # Shapefile-specific validation
        ...
```

## Integration Testing

### 1. Component Integration
```python
# Example: Component integration test
def test_geometry_export_integration(
    geometry_processor: GeometryProcessor,
    export_manager: ExportManager,
) -> None:
    """Test geometry processing and export integration."""
    # Arrange
    geometry = create_test_geometry()
    export_path = Path("test_output.dxf")

    # Act
    processed = geometry_processor.process(geometry)
    export_manager.export(processed, export_path)

    # Assert
    assert export_path.exists()
    assert validate_export(export_path)
```

### 2. Boundary Testing
```python
# Example: Component boundary test
def test_component_boundaries():
    """Test component boundary integrity."""
    # Arrange
    container = create_test_container()
    processor = container.geometry_processor()

    # Act & Assert
    # Should not expose implementation details
    assert not hasattr(processor, "_internal_state")
    # Should implement protocol
    assert isinstance(processor, GeometryProcessor)
    # Should maintain type safety
    with pytest.raises(TypeError):
        processor.process("invalid_input")  # type: ignore
```

## Error Handling

### 1. Error Propagation
```python
# Example: Error handling across boundaries
class GeometryError(Exception):
    """Base error for geometry operations."""
    pass

class ProcessingError(GeometryError):
    """Error during geometry processing."""
    def __init__(self, message: str, context: dict[str, Any]) -> None:
        super().__init__(message)
        self.context = context

class ExportError(Exception):
    """Error during export operations."""
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause

def process_and_export(
    geometry: GeometryData,
    export_path: Path,
    processor: GeometryProcessor,
    exporter: ExportStrategy,
) -> None:
    """Process and export geometry with error handling."""
    try:
        # Process geometry
        processed = processor.process(geometry)
    except Exception as e:
        raise ProcessingError(
            "Failed to process geometry",
            {"error": str(e), "geometry_id": geometry.id}
        ) from e

    try:
        # Export processed geometry
        exporter.export(processed, export_path)
    except Exception as e:
        raise ExportError(
            f"Failed to export to {export_path}",
            cause=e
        ) from e
```

### 2. Error Recovery
```python
# Example: Error recovery strategy
class ErrorRecoveryStrategy(Protocol):
    """Strategy for error recovery."""

    def can_recover(self, error: Exception) -> bool: ...
    def recover(self, error: Exception) -> None: ...

class ProcessingErrorRecovery(ErrorRecoveryStrategy):
    """Recovery strategy for processing errors."""

    def can_recover(self, error: Exception) -> bool:
        return isinstance(error, ProcessingError)

    def recover(self, error: Exception) -> None:
        if not isinstance(error, ProcessingError):
            raise TypeError("Invalid error type")

        # Implement recovery logic
        self._cleanup_failed_processing(error.context)
        self._reset_processing_state()
```

## Resource Management

### 1. Resource Lifecycle
```python
# Example: Resource management across components
class ResourceManager:
    """Manages resources across components."""

    def __init__(self) -> None:
        self._resources: list[Any] = []
        self._locks: dict[str, Lock] = {}

    def acquire(self, resource: Any, name: str) -> None:
        """Acquire a resource with locking."""
        if name not in self._locks:
            self._locks[name] = Lock()

        with self._locks[name]:
            self._resources.append(resource)

    def release(self, name: str) -> None:
        """Release a resource."""
        with self._locks[name]:
            if resource := self._find_resource(name):
                resource.close()
                self._resources.remove(resource)

    def cleanup(self) -> None:
        """Clean up all resources."""
        for name in list(self._locks.keys()):
            self.release(name)
```

### 2. Resource Sharing
```python
# Example: Shared resource management
class SharedResourceProvider(Protocol):
    """Provider for shared resources."""

    def get_resource(self, name: str) -> Any: ...
    def release_resource(self, name: str) -> None: ...

class SharedGeometryCache(SharedResourceProvider):
    """Shared geometry cache implementation."""

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: LRUCache = LRUCache(maxsize=max_size)
        self._locks: dict[str, Lock] = {}

    def get_resource(self, name: str) -> Any:
        if name not in self._locks:
            self._locks[name] = Lock()

        with self._locks[name]:
            return self._cache.get(name)

    def release_resource(self, name: str) -> None:
        with self._locks[name]:
            self._cache.pop(name, None)
```

## Quality Gates

### 1. Integration Quality
- All components properly connected
- Type safety maintained
- Error handling verified
- Resource management confirmed

### 2. Testing Quality
- Integration tests pass
- Boundary tests pass
- Error handling tested
- Resource cleanup verified

### 3. Performance Quality
- Integration overhead acceptable
- Resource usage within limits
- Error recovery time acceptable
- Memory usage verified

## Version History

| Version | Date | Changes | Status |
|---------|------|---------|--------|
| 0.1.0   | 2024-02-22 | Initial integration patterns | Draft |
