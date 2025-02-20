"""Tests for layer manager."""

import pytest
from unittest.mock import Mock
from src.geometry.layers.manager import LayerManager
from src.geometry.layers.validator import LayerValidator
from src.geometry.types.layer import Layer, LayerCollection
from src.geometry.types.base import GeometryData, GeometryMetadata, GeometryError, InvalidGeometryError

@pytest.fixture
def mock_geometry():
    """Create mock geometry data."""
    return GeometryData(
        id="test",
        geometry=Mock(),  # Mock shapely geometry
        metadata=GeometryMetadata(source_type="test")
    )

@pytest.fixture
def layer_collection():
    """Create empty layer collection."""
    return LayerCollection()

@pytest.fixture
def mock_validator():
    """Create mock validator."""
    validator = Mock(spec=LayerValidator)
    validator.validate_layer.return_value = True
    validator.get_validation_errors.return_value = []
    return validator

@pytest.fixture
def layer_manager(layer_collection, mock_validator):
    """Create layer manager with mock validator."""
    return LayerManager(layer_collection, validator=mock_validator)

def test_create_layer(layer_manager, mock_geometry):
    """Test layer creation."""
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=mock_geometry,
        update_dxf=True,
        style_id="test_style"
    )
    
    assert layer.name == "test_layer"
    assert layer.geometry == mock_geometry
    assert layer.update_dxf is True
    assert layer.style_id == "test_style"
    assert layer.operations == []
    
    # Check layer was added to collection
    assert "test_layer" in layer_manager.layers.layers
    
    # Check processing state was initialized
    state = layer_manager.get_processing_state("test_layer")
    assert state['processed_operations'] == []
    assert state['current_operation'] is None
    assert state['errors'] == []

def test_create_duplicate_layer(layer_manager, mock_geometry):
    """Test creating layer with duplicate name."""
    layer_manager.create_layer("test_layer", mock_geometry)
    
    with pytest.raises(GeometryError) as exc:
        layer_manager.create_layer("test_layer", mock_geometry)
    assert "Layer already exists" in str(exc.value)

def test_create_invalid_layer(layer_manager, mock_geometry, mock_validator):
    """Test creating invalid layer."""
    mock_validator.validate_layer.return_value = False
    mock_validator.get_validation_errors.return_value = ["Invalid geometry"]
    
    with pytest.raises(InvalidGeometryError) as exc:
        layer_manager.create_layer("test_layer", mock_geometry)
    assert "Invalid layer" in str(exc.value)

def test_update_layer(layer_manager, mock_geometry):
    """Test layer update."""
    layer = layer_manager.create_layer("test_layer", mock_geometry)
    
    new_geometry = GeometryData(
        id="test2",
        geometry=Mock(),
        metadata=GeometryMetadata(source_type="test")
    )
    
    updated = layer_manager.update_layer(
        name="test_layer",
        geometry=new_geometry,
        update_dxf=False,
        style_id="new_style",
        operations=[{"type": "test_op"}]
    )
    
    assert updated.geometry == new_geometry
    assert updated.update_dxf is False
    assert updated.style_id == "new_style"
    assert updated.operations == [{"type": "test_op"}]

def test_update_nonexistent_layer(layer_manager, mock_geometry):
    """Test updating non-existent layer."""
    with pytest.raises(KeyError) as exc:
        layer_manager.update_layer("nonexistent", mock_geometry)
    assert "Layer not found" in str(exc.value)

def test_delete_layer(layer_manager, mock_geometry):
    """Test layer deletion."""
    layer_manager.create_layer("test_layer", mock_geometry)
    layer_manager.delete_layer("test_layer")
    
    assert "test_layer" not in layer_manager.layers.layers
    with pytest.raises(KeyError):
        layer_manager.get_processing_state("test_layer")

def test_add_dependency(layer_manager, mock_geometry):
    """Test adding layer dependency."""
    layer_manager.create_layer("layer1", mock_geometry)
    layer_manager.create_layer("layer2", mock_geometry)
    
    layer_manager.add_dependency("layer2", "layer1")
    
    deps = layer_manager.layers.get_dependencies("layer2")
    assert "layer1" in deps

def test_add_cyclic_dependency(layer_manager, mock_geometry):
    """Test adding cyclic dependency."""
    layer_manager.create_layer("layer1", mock_geometry)
    layer_manager.create_layer("layer2", mock_geometry)
    
    layer_manager.add_dependency("layer2", "layer1")
    
    with pytest.raises(ValueError) as exc:
        layer_manager.add_dependency("layer1", "layer2")
    assert "cycle" in str(exc.value)

def test_processing_state_updates(layer_manager, mock_geometry):
    """Test processing state updates."""
    layer_manager.create_layer("test_layer", mock_geometry)
    
    # Update current operation
    layer_manager.update_processing_state("test_layer", operation="test_op")
    state = layer_manager.get_processing_state("test_layer")
    assert state['current_operation'] == "test_op"
    
    # Complete operation
    layer_manager.update_processing_state("test_layer", completed="test_op")
    state = layer_manager.get_processing_state("test_layer")
    assert "test_op" in state['processed_operations']
    assert state['current_operation'] is None
    
    # Add error
    layer_manager.update_processing_state("test_layer", error="Test error")
    state = layer_manager.get_processing_state("test_layer")
    assert "Test error" in state['errors']

def test_partial_layer_update(layer_manager, mock_geometry):
    """Test updating only specific fields of a layer."""
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=mock_geometry,
        update_dxf=True,
        style_id="test_style"
    )
    
    # Update only style_id
    updated = layer_manager.update_layer(
        name="test_layer",
        style_id="new_style"
    )
    
    assert updated.geometry == mock_geometry  # Unchanged
    assert updated.update_dxf is True  # Unchanged
    assert updated.style_id == "new_style"  # Changed
    assert updated.operations == []  # Unchanged

def test_update_layer_operations(layer_manager, mock_geometry):
    """Test updating layer operations."""
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=mock_geometry
    )
    
    operations = [
        {"type": "buffer", "parameters": {"distance": 1.0}},
        {"type": "dissolve", "parameters": {}}
    ]
    
    updated = layer_manager.update_layer(
        name="test_layer",
        operations=operations
    )
    
    assert updated.operations == operations
    assert updated.geometry == mock_geometry  # Other fields unchanged

def test_delete_layer_with_dependencies(layer_manager, mock_geometry):
    """Test deleting a layer that has dependencies."""
    # Create layers with dependency
    layer1 = layer_manager.create_layer("layer1", mock_geometry)
    layer2 = layer_manager.create_layer("layer2", mock_geometry)
    layer_manager.add_dependency("layer2", "layer1")
    
    # Delete dependency layer
    layer_manager.delete_layer("layer1")
    
    # Check layer2's dependencies are cleaned up
    assert "layer1" not in layer_manager.layers.get_dependencies("layer2")

def test_get_layer_nonexistent(layer_manager):
    """Test getting non-existent layer."""
    with pytest.raises(KeyError) as exc:
        layer_manager.get_layer("nonexistent")
    assert "Layer not found" in str(exc.value)

def test_add_dependency_nonexistent_layers(layer_manager, mock_geometry):
    """Test adding dependency with non-existent layers."""
    layer_manager.create_layer("layer1", mock_geometry)
    
    with pytest.raises(KeyError):
        layer_manager.add_dependency("layer1", "nonexistent")
    
    with pytest.raises(KeyError):
        layer_manager.add_dependency("nonexistent", "layer1")

def test_complex_dependency_chain(layer_manager, mock_geometry):
    """Test creating and validating a complex dependency chain."""
    # Create layers
    layer1 = layer_manager.create_layer("layer1", mock_geometry)
    layer2 = layer_manager.create_layer("layer2", mock_geometry)
    layer3 = layer_manager.create_layer("layer3", mock_geometry)
    layer4 = layer_manager.create_layer("layer4", mock_geometry)
    
    # Create dependency chain: layer4 -> layer3 -> layer2 -> layer1
    layer_manager.add_dependency("layer2", "layer1")
    layer_manager.add_dependency("layer3", "layer2")
    layer_manager.add_dependency("layer4", "layer3")
    
    # Verify dependencies
    assert layer_manager.layers.get_dependencies("layer2") == {"layer1"}
    assert layer_manager.layers.get_dependencies("layer3") == {"layer2"}
    assert layer_manager.layers.get_dependencies("layer4") == {"layer3"}
    
    # Verify processing order
    order = layer_manager.layers.get_processing_order()
    assert order.index("layer1") < order.index("layer2")
    assert order.index("layer2") < order.index("layer3")
    assert order.index("layer3") < order.index("layer4")

def test_processing_state_initialization(layer_manager, mock_geometry):
    """Test processing state is properly initialized for new layers."""
    layer = layer_manager.create_layer("test_layer", mock_geometry)
    state = layer_manager.get_processing_state("test_layer")
    
    assert isinstance(state, dict)
    assert 'processed_operations' in state
    assert 'current_operation' in state
    assert 'errors' in state
    assert len(state['processed_operations']) == 0
    assert state['current_operation'] is None
    assert len(state['errors']) == 0

def test_update_processing_state_validation(layer_manager, mock_geometry):
    """Test validation in processing state updates."""
    layer = layer_manager.create_layer("test_layer", mock_geometry)
    
    # Test with non-existent layer
    with pytest.raises(KeyError):
        layer_manager.update_processing_state("nonexistent", operation="test")
    
    # Test normal update sequence
    layer_manager.update_processing_state("test_layer", operation="op1")
    state = layer_manager.get_processing_state("test_layer")
    assert state['current_operation'] == "op1"
    
    layer_manager.update_processing_state("test_layer", completed="op1")
    state = layer_manager.get_processing_state("test_layer")
    assert "op1" in state['processed_operations']
    assert state['current_operation'] is None

def test_layer_validation_on_update(layer_manager, mock_geometry, mock_validator):
    """Test layer validation is performed on updates."""
    layer = layer_manager.create_layer("test_layer", mock_geometry)
    
    # Make validator fail
    mock_validator.validate_layer.return_value = False
    mock_validator.get_validation_errors.return_value = ["Invalid update"]
    
    with pytest.raises(InvalidGeometryError) as exc:
        layer_manager.update_layer(
            name="test_layer",
            update_dxf=True
        )
    assert "Invalid layer after update" in str(exc.value)

def test_create_layer_with_operations(layer_manager, mock_geometry):
    """Test creating layer with initial operations."""
    operations = [
        {"type": "buffer", "parameters": {"distance": 1.0}},
        {"type": "dissolve", "parameters": {}}
    ]
    
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=mock_geometry,
        operations=operations
    )
    
    assert layer.operations == operations
    assert layer.name == "test_layer"
    assert layer.geometry == mock_geometry 