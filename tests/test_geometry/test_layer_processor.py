"""Tests for layer processor."""

import pytest
from unittest.mock import Mock, patch
from src.geometry.layers.processor import LayerProcessor
from src.geometry.layers.manager import LayerManager
from src.geometry.layers.validator import LayerValidator
from src.geometry.types.layer import Layer, LayerCollection
from src.geometry.types.base import (
    GeometryData, 
    GeometryMetadata,
    Operation,
    OperationContext,
    OperationResult,
    GeometryError,
    GeometryOperationError
)

@pytest.fixture
def mock_layer_manager():
    """Create mock layer manager."""
    manager = Mock(spec=LayerManager)
    manager.get_layer.return_value = None
    manager.get_layer_collection.return_value = LayerCollection()
    return manager

@pytest.fixture
def mock_layer_validator():
    """Create mock layer validator."""
    validator = Mock(spec=LayerValidator)
    validator.validate_layer.return_value = True
    validator.validate_dependencies.return_value = True
    validator.validate_operation_sequence.return_value = True
    validator.get_validation_errors.return_value = []
    return validator

@pytest.fixture
def layer_processor(mock_layer_manager, mock_layer_validator):
    """Create layer processor with mock dependencies."""
    return LayerProcessor(
        layer_manager=mock_layer_manager,
        layer_validator=mock_layer_validator
    )

@pytest.fixture
def mock_operation():
    """Create mock operation."""
    operation = Mock(spec=Operation)
    operation.execute.return_value = OperationResult(
        success=True,
        geometry=Mock(),  # Mock shapely geometry
        metadata=GeometryMetadata(source_type="test")
    )
    return operation

def test_register_operation(layer_processor):
    """Test registering operation."""
    mock_op = Mock(spec=Operation)
    layer_processor.register_operation("test_op", mock_op)
    assert "test_op" in layer_processor.get_available_operations()

def test_register_duplicate_operation(layer_processor):
    """Test registering duplicate operation."""
    mock_op = Mock(spec=Operation)
    layer_processor.register_operation("test_op", mock_op)
    with pytest.raises(ValueError):
        layer_processor.register_operation("test_op", mock_op)

def test_process_layer_success(layer_processor, mock_operation):
    """Test successful layer processing."""
    # Setup layer with operation
    layer = Layer(
        name="test_layer",
        geometry=GeometryData(
            id="test",
            geometry=Mock(),
            metadata=GeometryMetadata(source_type="test")
        ),
        operations=[{"type": "test_op", "parameters": {}}]
    )
    
    # Register operation
    layer_processor.register_operation("test_op", mock_operation)
    
    # Process layer
    result = layer_processor.process_layer(layer)
    assert result.success
    assert result.geometry is not None
    assert layer_processor.get_layer_errors(layer.name) == []

def test_process_layer_validation_failure(layer_processor, mock_layer_validator):
    """Test layer processing with validation failure."""
    mock_layer_validator.validate_layer.return_value = False
    mock_layer_validator.get_validation_errors.return_value = ["Invalid layer"]
    
    layer = Layer(
        name="test_layer",
        geometry=GeometryData(
            id="test",
            geometry=Mock(),
            metadata=GeometryMetadata(source_type="test")
        )
    )
    
    result = layer_processor.process_layer(layer)
    assert not result.success
    assert "Invalid layer" in layer_processor.get_layer_errors(layer.name)[0]

def test_process_layer_operation_error(layer_processor, mock_operation):
    """Test layer processing with operation error."""
    # Setup operation to fail
    error_msg = "Operation failed"
    mock_operation.execute.side_effect = GeometryOperationError(error_msg)
    
    layer = Layer(
        name="test_layer",
        geometry=GeometryData(
            id="test",
            geometry=Mock(),
            metadata=GeometryMetadata(source_type="test")
        ),
        operations=[{"type": "test_op", "parameters": {}}]
    )
    
    layer_processor.register_operation("test_op", mock_operation)
    result = layer_processor.process_layer(layer)
    
    assert not result.success
    assert error_msg in layer_processor.get_layer_errors(layer.name)[0]

def test_process_layers_dependency_order(layer_processor, mock_operation):
    """Test processing layers in dependency order."""
    # Setup layers with dependencies
    collection = LayerCollection()
    layer1 = Layer(
        name="layer1",
        geometry=GeometryData(
            id="test1",
            geometry=Mock(),
            metadata=GeometryMetadata(source_type="test")
        )
    )
    layer2 = Layer(
        name="layer2",
        geometry=GeometryData(
            id="test2",
            geometry=Mock(),
            metadata=GeometryMetadata(source_type="test")
        )
    )
    
    collection.add_layer(layer1)
    collection.add_layer(layer2)
    collection.add_dependency("layer2", "layer1")
    
    # Setup layer manager to return our collection
    layer_processor.layer_manager.get_layer_collection.return_value = collection
    
    # Process layers
    results = layer_processor.process_layers()
    assert len(results) == 2
    assert all(result.success for result in results.values())

def test_get_layer_progress(layer_processor):
    """Test getting layer processing progress."""
    layer_name = "test_layer"
    progress = 0.5
    layer_processor._layer_progress[layer_name] = progress
    assert layer_processor.get_layer_progress(layer_name) == progress

def test_get_layer_errors(layer_processor):
    """Test getting layer errors."""
    layer_name = "test_layer"
    error = "Test error"
    layer_processor._layer_errors[layer_name] = [error]
    assert layer_processor.get_layer_errors(layer_name) == [error]

def test_process_layer_unknown_operation(layer_processor):
    """Test processing layer with unknown operation type."""
    layer = Layer(
        name="test_layer",
        geometry=GeometryData(
            id="test",
            geometry=Mock(),
            metadata=GeometryMetadata(source_type="test")
        ),
        operations=[{"type": "unknown_op", "parameters": {}}]
    )
    
    result = layer_processor.process_layer(layer)
    assert not result.success
    assert "Unknown operation type" in layer_processor.get_layer_errors(layer.name)[0] 