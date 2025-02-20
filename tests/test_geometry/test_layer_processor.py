"""Tests for layer processor."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from shapely.geometry import Point
from src.geometry.layers.processor import LayerProcessor
from src.geometry.layers.manager import LayerManager
from src.geometry.layers.validator import LayerValidator
from src.geometry.types.layer import Layer, LayerCollection
from src.geometry.types.base import (
    GeometryData, 
    GeometryMetadata,
    GeometryError,
    GeometryOperationError
)
from src.geometry.operations.base import (
    Operation,
    OperationContext,
    OperationResult
)

@pytest.fixture
def test_geometry_data():
    """Create test geometry data."""
    return GeometryData(
        id="test",
        geometry=Point(0, 0),
        metadata=GeometryMetadata(source_type="test")
    )
    
@pytest.fixture
def mock_layer_manager(test_geometry_data):
    """Create mock layer manager."""
    manager = Mock(spec=LayerManager)
    layer_collection = LayerCollection()
    
    def get_layer(name):
        if name in layer_collection.layers:
            return layer_collection.layers[name]
        layer = Layer(name=name, geometry=test_geometry_data)
        layer_collection.add_layer(layer)
        return layer
        
    manager.get_layer = get_layer
    manager.layers = layer_collection
    manager.get_processing_state.return_value = {
        "processed_operations": [],
        "current_operation": None,
        "errors": []
    }
    return manager
    
@pytest.fixture 
def mock_layer_validator():
    """Create mock layer validator."""
    validator = Mock()
    validator.validate.return_value = True
    validator.validate_operation_sequence.return_value = True
    return validator
    
@pytest.fixture 
def mock_operation(test_geometry_data):
    """Create mock operation."""
    operation = Mock(spec=Operation)
    # Create a new GeometryData with updated geometry
    result_data = GeometryData(
        id=test_geometry_data.id,
        geometry=Point(1, 1),
        metadata=test_geometry_data.metadata
    )
    result = OperationResult(success=True, result=result_data)
    operation.execute.return_value = result
    return operation
    
@pytest.fixture 
def processor(mock_layer_manager, mock_layer_validator):
    """Create layer processor."""
    return LayerProcessor(
        layer_manager=mock_layer_manager,
        validator=mock_layer_validator
    )

class TestLayerProcessor:
    def test_process_single_layer(self, processor, mock_layer_manager, test_geometry_data, mock_operation):
        """Test processing a single layer with no dependencies."""
        # Create test layer
        layer = Layer(name="test", geometry=test_geometry_data)
        layer.operations = [{"type": "test_op"}]
        mock_layer_manager.layers.add_layer(layer)
        
        # Register test operation
        processor.register_operation("test_op", mock_operation)
        
        # Process layer
        processor.process_layer(layer)
        
        # Verify operation was called
        mock_operation.execute.assert_called_once()

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

def test_register_operation(processor, mock_operation):
    """Test registering operation."""
    processor.register_operation("test_op", mock_operation)
    assert "test_op" in processor.get_available_operations()

def test_register_duplicate_operation(processor, mock_operation):
    """Test registering duplicate operation."""
    processor.register_operation("test_op", mock_operation)
    with pytest.raises(ValueError, match="Operation already registered"):
        processor.register_operation("test_op", mock_operation)

def test_process_layer_success(processor, mock_layer_manager, test_geometry_data, mock_operation):
    """Test successful layer processing."""
    # Create test layer
    layer = Layer(name="test", geometry=test_geometry_data)
    layer.operations = [{"type": "test_op"}]
    mock_layer_manager.layers.add_layer(layer)
    
    # Register operation
    processor.register_operation("test_op", mock_operation)
    
    # Process layer
    processor.process_layer(layer)
    
    # Verify operation was called
    mock_operation.execute.assert_called_once()

def test_process_layer_validation_failure(processor, mock_layer_manager, test_geometry_data, mock_layer_validator):
    """Test layer processing with validation failure."""
    # Setup validation failure
    mock_layer_validator.validate_operation_sequence.return_value = False
    mock_layer_validator.get_validation_errors.return_value = ["Invalid operation"]
    
    # Create test layer
    layer = Layer(name="test", geometry=test_geometry_data)
    layer.operations = [{"type": "test_op"}]
    mock_layer_manager.layers.add_layer(layer)
    
    # Process layer should fail
    with pytest.raises(GeometryError, match="Invalid operation sequence"):
        processor.process_layer(layer)

def test_process_layer_operation_error(processor, mock_layer_manager, test_geometry_data, mock_operation):
    """Test layer processing with operation error."""
    # Setup operation failure
    mock_operation.execute.return_value = OperationResult(success=False, error="Operation failed")
    
    # Create test layer
    layer = Layer(name="test", geometry=test_geometry_data)
    layer.operations = [{"type": "test_op"}]
    mock_layer_manager.layers.add_layer(layer)
    
    # Register operation
    processor.register_operation("test_op", mock_operation)
    
    # Process layer should fail
    with pytest.raises(GeometryOperationError, match="Operation 'test_op' failed"):
        processor.process_layer(layer)

def test_process_layers_dependency_order(processor, mock_layer_manager, test_geometry_data, mock_operation):
    """Test processing layers in dependency order."""
    # Create test layers
    layer1 = Layer(name="layer1", geometry=test_geometry_data)
    layer2 = Layer(name="layer2", geometry=test_geometry_data)
    layer1.operations = [{"type": "test_op"}]
    layer2.operations = [{"type": "test_op"}]
    
    # Create layer collection with dependencies
    layer_collection = LayerCollection()
    layer_collection.add_layer(layer1)
    layer_collection.add_layer(layer2)
    layer_collection.add_dependency("layer2", "layer1")  # layer2 depends on layer1
    
    # Setup mock layer manager
    mock_layer_manager.layers = layer_collection
    mock_layer_manager.get_layer = lambda name: layer_collection.layers[name]  # Use lambda instead of side_effect
    mock_layer_manager.get_processing_state.return_value = {
        "processed_operations": [],
        "current_operation": None,
        "errors": []
    }
    
    # Register operation
    processor.register_operation("test_op", mock_operation)
    
    # Process layers
    processor.process_layers()
    
    # Verify operation was called twice in correct order
    assert mock_operation.execute.call_count == 2
    calls = mock_operation.execute.call_args_list
    assert calls[0].args[0].current_layer.name == "layer1"
    assert calls[1].args[0].current_layer.name == "layer2"

def test_get_layer_progress(processor, mock_layer_manager, test_geometry_data):
    """Test getting layer progress."""
    # Create test layer with operation
    layer = Layer(name="test", geometry=test_geometry_data)
    layer.operations = [{"type": "test_op"}]
    
    # Add layer to collection
    layer_collection = LayerCollection()
    layer_collection.add_layer(layer)
    
    # Setup mock layer manager
    mock_layer_manager.layers = layer_collection
    mock_layer_manager.get_layer = lambda name: layer_collection.layers[name]  # Use lambda instead of side_effect
    mock_layer_manager.get_processing_state.return_value = {
        "processed_operations": ["test_op"],
        "current_operation": None,
        "errors": []
    }
    
    # Get progress
    progress = processor.get_layer_progress("test")
    
    # Verify operations are set correctly
    assert len(layer.operations) == 1
    assert progress["total_operations"] == 1
    assert progress["processed_operations"] == ["test_op"]
    assert progress["current_operation"] is None
    assert progress["errors"] == []

def test_get_layer_errors(processor, mock_layer_manager):
    """Test getting layer errors."""
    # Setup mock state
    mock_layer_manager.get_processing_state.return_value = {
        "errors": ["Test error"]
    }
    
    # Get errors
    errors = processor.get_layer_errors("test")
    assert errors == ["Test error"]

def test_process_layer_unknown_operation(processor, mock_layer_manager, test_geometry_data):
    """Test processing layer with unknown operation."""
    # Create test layer
    layer = Layer(name="test", geometry=test_geometry_data)
    layer.operations = [{"type": "unknown_op"}]
    mock_layer_manager.layers.add_layer(layer)
    
    # Process layer should fail
    with pytest.raises(GeometryError, match="Unknown operation type"):
        processor.process_layer(layer) 