# Test-Driven Development Guidelines

## Overview

This document outlines our Test-Driven Development (TDD) practices for the Python ACAD Tools project. TDD is our primary development methodology, chosen to ensure high quality, maintainable code that meets our strict type safety and component boundary requirements.

## TDD Workflow

### 1. Write Test First
```python
# test_geometry_processor.py
def test_buffer_operation():
    """Test buffer operation processing.

    This test is written BEFORE implementing the buffer operation.
    It defines the expected interface and behavior.
    """
    # Arrange
    processor = GeometryProcessor()
    input_geom = create_test_geometry()
    params = {"distance": 1.0}

    # Act
    result = processor.process_operation(
        operation_type="buffer",
        geometry=input_geom,
        parameters=params
    )

    # Assert
    assert result.success
    assert isinstance(result.geometry, GeometryData)
    assert result.geometry.is_valid
```

### 2. Run Test (Should Fail)
```bash
# Run specific test
pytest tests/test_geometry/test_geometry_processor.py::test_buffer_operation -v

# Expected output:
# FAILED - No implementation for buffer operation
```

### 3. Write Implementation
```python
# geometry_processor.py
class GeometryProcessor:
    """Processes geometry operations."""

    def process_operation(
        self,
        operation_type: str,
        geometry: GeometryData,
        parameters: dict[str, Any]
    ) -> OperationResult:
        """Process geometry operation."""
        if operation_type == "buffer":
            return self._process_buffer(geometry, parameters)
        raise ValueError(f"Unknown operation: {operation_type}")
```

### 4. Run Test (Should Pass)
```bash
# Run test again
pytest tests/test_geometry/test_geometry_processor.py::test_buffer_operation -v

# Expected output:
# PASSED
```

### 5. Refactor
```python
# Refactor with confidence, tests verify behavior
class GeometryProcessor:
    """Processes geometry operations."""

    def __init__(self) -> None:
        self._operations: dict[str, GeometryOperation] = {}

    def register_operation(self, name: str, operation: GeometryOperation) -> None:
        """Register geometry operation."""
        self._operations[name] = operation

    def process_operation(
        self,
        operation_type: str,
        geometry: GeometryData,
        parameters: dict[str, Any]
    ) -> OperationResult:
        """Process geometry operation."""
        if operation_type not in self._operations:
            raise ValueError(f"Unknown operation: {operation_type}")
        return self._operations[operation_type].execute(geometry, parameters)
```

## TDD and Component Boundaries

### 1. Interface First
```python
# First: Define protocol in types/
class GeometryOperation(Protocol):
    """Protocol for geometry operations."""
    def execute(self, geometry: GeometryData, params: dict[str, Any]) -> OperationResult: ...
    def validate(self, params: dict[str, Any]) -> bool: ...

# Second: Write test using protocol
def test_operation_validation():
    """Test operation parameter validation."""
    operation: GeometryOperation = BufferOperation()
    assert operation.validate({"distance": 1.0})
    assert not operation.validate({"invalid": "params"})

# Third: Implement concrete class
class BufferOperation:
    """Buffer operation implementation."""
    def execute(self, geometry: GeometryData, params: dict[str, Any]) -> OperationResult:
        if not self.validate(params):
            return OperationResult.failure("Invalid parameters")
        # Implementation...

    def validate(self, params: dict[str, Any]) -> bool:
        return "distance" in params and isinstance(params["distance"], (int, float))
```

### 2. Mock Dependencies
```python
# test_layer_processor.py
def test_layer_processing(mocker):
    """Test layer processing with mocked dependencies."""
    # Arrange
    mock_geometry = mocker.Mock(spec=GeometryData)
    mock_operation = mocker.Mock(spec=GeometryOperation)
    mock_operation.execute.return_value = OperationResult.success(mock_geometry)

    processor = LayerProcessor()
    processor.register_operation("test_op", mock_operation)

    # Act
    result = processor.process_layer(
        layer_name="test",
        operations=[{"type": "test_op", "params": {}}]
    )

    # Assert
    assert result.success
    mock_operation.execute.assert_called_once()
```

## TDD and Type Safety

### 1. Type Test First
```python
def test_type_safety():
    """Test type safety at component boundaries."""
    # This should raise type error at runtime
    with pytest.raises(TypeError):
        processor = GeometryProcessor()
        processor.process_operation(
            operation_type="buffer",
            geometry="invalid",  # Should be GeometryData
            parameters={"distance": 1.0}
        )
```

### 2. Runtime Validation
```python
@beartype
def process_operation(
    self,
    operation_type: str,
    geometry: GeometryData,
    parameters: dict[str, Any]
) -> OperationResult:
    """Process with runtime type checking."""
    return self._operations[operation_type].execute(geometry, parameters)
```

## TDD and Error Handling

### 1. Error Test First
```python
def test_error_handling():
    """Test error handling and propagation."""
    # Arrange
    processor = GeometryProcessor()

    # Act & Assert
    with pytest.raises(GeometryError) as exc:
        processor.process_operation(
            operation_type="unknown",
            geometry=create_test_geometry(),
            parameters={}
        )
    assert "Unknown operation" in str(exc.value)
```

### 2. Error Implementation
```python
def process_operation(
    self,
    operation_type: str,
    geometry: GeometryData,
    parameters: dict[str, Any]
) -> OperationResult:
    """Process with error handling."""
    try:
        if operation_type not in self._operations:
            raise GeometryError(f"Unknown operation: {operation_type}")
        return self._operations[operation_type].execute(geometry, parameters)
    except Exception as e:
        return OperationResult.failure(str(e))
```

## TDD and Performance

### 1. Performance Test First
```python
def test_processing_performance():
    """Test processing performance."""
    # Arrange
    processor = GeometryProcessor()
    large_geometry = create_large_test_geometry()

    # Act
    with timer() as t:
        result = processor.process_operation(
            operation_type="buffer",
            geometry=large_geometry,
            parameters={"distance": 1.0}
        )

    # Assert
    assert t.elapsed < 1.0  # Should process within 1 second
    assert result.success
```

### 2. Performance Implementation
```python
def process_operation(
    self,
    operation_type: str,
    geometry: GeometryData,
    parameters: dict[str, Any]
) -> OperationResult:
    """Process with performance optimization."""
    # Pre-validate to avoid unnecessary processing
    if not self._validate_input(geometry, parameters):
        return OperationResult.failure("Invalid input")

    # Process with caching
    cache_key = self._get_cache_key(operation_type, geometry, parameters)
    if result := self._cache.get(cache_key):
        return result

    # Process and cache
    result = self._operations[operation_type].execute(geometry, parameters)
    self._cache[cache_key] = result
    return result
```

## TDD Best Practices

1. **Test Organization**
   - One test file per module
   - Clear test names describing behavior
   - Arrange-Act-Assert pattern
   - Independent tests
   - Shared fixtures in conftest.py

2. **Test Coverage**
   - Core functionality: 100%
   - Business logic: >90%
   - Edge cases: >80%
   - Integration points: >70%

3. **Test Quality**
   - Clear assertions
   - Meaningful error messages
   - No test interdependence
   - Clean test environment
   - Proper resource cleanup

4. **Test Maintenance**
   - Regular test review
   - Remove obsolete tests
   - Update with changes
   - Monitor coverage
   - Performance profiling

## Integration with CI/CD

1. **Pre-commit Hooks**
```yaml
- pytest-check:
    name: pytest (unit tests)
    entry: pytest
    language: system
    types: [python]
    pass_filenames: false
    args: ["--cov=src"]
```

2. **Coverage Requirements**
```ini
[coverage:run]
branch = True
source = src

[coverage:report]
fail_under = 80
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
```

3. **Performance Gates**
```yaml
- pytest-benchmark:
    name: pytest (benchmarks)
    entry: pytest
    language: system
    types: [python]
    args: ["--benchmark-only"]
```

## Test Examples by Component

### 1. Core Component
```python
# test_core_types.py
def test_operation_result():
    """Test operation result type."""
    # Success case
    result = OperationResult.success({"data": "test"})
    assert result.success
    assert result.data == {"data": "test"}
    assert not result.error

    # Failure case
    result = OperationResult.failure("Test error")
    assert not result.success
    assert not result.data
    assert result.error == "Test error"
```

### 2. Geometry Component
```python
# test_geometry_layer.py
def test_layer_operations():
    """Test layer operation processing."""
    # Arrange
    layer = Layer("test")
    layer.add_operation(BufferOperation(distance=1.0))
    layer.add_operation(SimplifyOperation(tolerance=0.1))

    # Act
    result = layer.process()

    # Assert
    assert result.success
    assert len(layer.processing_log) == 2
    assert all(op in layer.processing_log for op in ["buffer", "simplify"])
```

### 3. Export Component
```python
# test_export_manager.py
def test_dxf_export():
    """Test DXF export process."""
    # Arrange
    manager = ExportManager()
    geometry = create_test_geometry()
    export_data = ExportData(
        format="dxf",
        path=Path("test.dxf"),
        metadata={"version": "R2018"}
    )

    # Act
    result = manager.export(geometry, export_data)

    # Assert
    assert result.success
    assert Path("test.dxf").exists()
    assert validate_dxf("test.dxf")
```

## Continuous Improvement

1. **Regular Review**
   - Test coverage analysis
   - Performance benchmarks
   - Code quality metrics
   - Documentation updates

2. **Feedback Loop**
   - Developer feedback
   - Test effectiveness
   - Coverage gaps
   - Performance issues

3. **Updates**
   - New test cases
   - Updated assertions
   - Improved mocks
   - Better fixtures
