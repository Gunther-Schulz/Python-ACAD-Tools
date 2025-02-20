"""Tests for layer validator."""

import pytest
from unittest.mock import Mock
from src.geometry.layers.validator import LayerValidator
from src.geometry.types.layer import Layer, LayerCollection
from src.geometry.types.base import GeometryData, GeometryMetadata, GeometryValidator

@pytest.fixture
def mock_geometry_validator():
    """Create mock geometry validator."""
    validator = Mock(spec=GeometryValidator)
    validator.validate.return_value = True
    validator.get_validation_errors.return_value = []
    return validator

@pytest.fixture
def layer_validator(mock_geometry_validator):
    """Create layer validator with mock geometry validator."""
    return LayerValidator(geometry_validator=mock_geometry_validator)

@pytest.fixture
def mock_geometry():
    """Create mock geometry data."""
    return GeometryData(
        id="test",
        geometry=Mock(),  # Mock shapely geometry
        metadata=GeometryMetadata(source_type="test")
    )

@pytest.fixture
def valid_layer(mock_geometry):
    """Create valid layer."""
    return Layer(
        name="test_layer",
        geometry=mock_geometry,
        update_dxf=True,
        style_id="test_style"
    )

def test_validate_valid_layer(layer_validator, valid_layer):
    """Test validating valid layer."""
    assert layer_validator.validate_layer(valid_layer)
    assert not layer_validator.get_validation_errors()

def test_validate_layer_no_name(layer_validator, valid_layer):
    """Test validating layer without name."""
    valid_layer.name = ""
    assert not layer_validator.validate_layer(valid_layer)
    errors = layer_validator.get_validation_errors()
    assert len(errors) == 1
    assert "name is required" in errors[0]

def test_validate_layer_no_geometry(layer_validator, valid_layer):
    """Test validating layer without geometry."""
    valid_layer.geometry = None
    assert not layer_validator.validate_layer(valid_layer)
    errors = layer_validator.get_validation_errors()
    assert len(errors) == 1
    assert "geometry is required" in errors[0]

def test_validate_layer_invalid_geometry(layer_validator, valid_layer, mock_geometry_validator):
    """Test validating layer with invalid geometry."""
    mock_geometry_validator.validate.return_value = False
    mock_geometry_validator.get_validation_errors.return_value = ["Invalid geometry"]
    
    assert not layer_validator.validate_layer(valid_layer)
    errors = layer_validator.get_validation_errors()
    assert len(errors) == 1
    assert "Invalid geometry" in errors[0]

def test_validate_layer_invalid_operations(layer_validator, valid_layer):
    """Test validating layer with invalid operations."""
    # Test non-list operations
    valid_layer.operations = "not a list"
    assert not layer_validator.validate_layer(valid_layer)
    assert "must be a list" in layer_validator.get_validation_errors()[0]
    
    # Test non-dict operation
    valid_layer.operations = ["not a dict"]
    assert not layer_validator.validate_layer(valid_layer)
    assert "must be a dictionary" in layer_validator.get_validation_errors()[0]
    
    # Test operation without type
    valid_layer.operations = [{}]
    assert not layer_validator.validate_layer(valid_layer)
    assert "missing 'type' field" in layer_validator.get_validation_errors()[0]
    
    # Test operation with non-string type
    valid_layer.operations = [{"type": 123}]
    assert not layer_validator.validate_layer(valid_layer)
    assert "'type' must be a string" in layer_validator.get_validation_errors()[0]

def test_validate_dependencies(layer_validator):
    """Test validating layer dependencies."""
    collection = LayerCollection()
    
    # Add layers
    layer1 = Layer("layer1", mock_geometry=Mock())
    layer2 = Layer("layer2", mock_geometry=Mock())
    collection.add_layer(layer1)
    collection.add_layer(layer2)
    
    # Add valid dependency
    collection.add_dependency("layer2", "layer1")
    assert layer_validator.validate_dependencies(collection)
    
    # Test missing dependent layer
    collection._layer_dependencies["nonexistent"] = {"layer1"}
    assert not layer_validator.validate_dependencies(collection)
    assert "non-existent layer" in layer_validator.get_validation_errors()[0]
    
    # Test missing dependency layer
    del collection._layer_dependencies["nonexistent"]
    collection._layer_dependencies["layer2"].add("nonexistent")
    assert not layer_validator.validate_dependencies(collection)
    assert "non-existent layer" in layer_validator.get_validation_errors()[0]

def test_validate_operation_sequence(layer_validator, valid_layer):
    """Test validating operation sequence."""
    available_ops = {"buffer", "dissolve"}
    
    # Test valid sequence
    valid_layer.operations = [
        {"type": "buffer", "parameters": {"distance": 1.0}},
        {"type": "dissolve"}
    ]
    assert layer_validator.validate_operation_sequence(valid_layer, available_ops)
    
    # Test missing type
    valid_layer.operations = [{"parameters": {}}]
    assert not layer_validator.validate_operation_sequence(valid_layer, available_ops)
    assert "missing 'type'" in layer_validator.get_validation_errors()[0]
    
    # Test unknown operation
    valid_layer.operations = [{"type": "unknown"}]
    assert not layer_validator.validate_operation_sequence(valid_layer, available_ops)
    assert "Unknown operation type" in layer_validator.get_validation_errors()[0]
    
    # Test invalid parameters format
    valid_layer.operations = [{"type": "buffer", "parameters": "not a dict"}]
    assert not layer_validator.validate_operation_sequence(valid_layer, available_ops)
    assert "invalid parameters format" in layer_validator.get_validation_errors()[0] 