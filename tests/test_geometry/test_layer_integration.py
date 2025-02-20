"""Integration tests for layer management components."""

import pytest
from unittest.mock import Mock
from shapely.geometry import box, Point
from src.geometry.layers.manager import LayerManager
from src.geometry.layers.validator import LayerValidator
from src.geometry.layers.processor import LayerProcessor
from src.geometry.types.layer import Layer, LayerCollection
from src.geometry.types.base import (
    GeometryData,
    GeometryMetadata,
    GeometryError,
    GeometryOperationError,
    Operation,
    OperationContext,
    OperationResult
)
from src.geometry.operations.buffer import BufferOperation, BufferParameters

@pytest.fixture
def geometry_collection():
    """Create a collection of test geometries."""
    return {
        "point": GeometryData(
            id="test_point",
            geometry=Point(0, 0),
            metadata=GeometryMetadata(source_type="test")
        ),
        "box": GeometryData(
            id="test_box",
            geometry=box(0, 0, 1, 1),
            metadata=GeometryMetadata(source_type="test")
        )
    }

@pytest.fixture
def layer_collection():
    """Create empty layer collection."""
    return LayerCollection()

@pytest.fixture
def layer_validator():
    """Create real layer validator."""
    return LayerValidator()

@pytest.fixture
def layer_manager(layer_collection, layer_validator):
    """Create layer manager with real validator."""
    return LayerManager(layer_collection, validator=layer_validator)

@pytest.fixture
def layer_processor(layer_manager, layer_validator):
    """Create layer processor with real components."""
    processor = LayerProcessor(layer_manager, layer_validator)
    # Register buffer operation
    processor.register_operation("buffer", BufferOperation())
    return processor

def test_create_and_process_single_layer(layer_manager, layer_processor, geometry_collection):
    """Test creating and processing a single layer with buffer operation."""
    # Create layer with buffer operation
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=geometry_collection["point"],
        operations=[{
            "type": "buffer",
            "parameters": {
                "distance": 1.0,
                "resolution": 16,
                "cap_style": 1,
                "join_style": 1,
                "mitre_limit": 5.0,
                "single_sided": False
            }
        }]
    )
    
    # Process layer
    result = layer_processor.process_layer(layer)
    
    # Verify success
    assert result.success
    assert result.geometry is not None
    assert layer_processor.get_layer_errors(layer.name) == []
    
    # Verify operation was logged
    assert len(layer.geometry.metadata.operations_log) == 1
    assert "buffer" in layer.geometry.metadata.operations_log[0]

def test_process_dependent_layers(layer_manager, layer_processor, geometry_collection):
    """Test processing layers with dependencies."""
    # Create layers with dependency chain
    layer1 = layer_manager.create_layer(
        name="layer1",
        geometry=geometry_collection["point"],
        operations=[{
            "type": "buffer",
            "parameters": {"distance": 1.0}
        }]
    )
    
    layer2 = layer_manager.create_layer(
        name="layer2",
        geometry=geometry_collection["box"],
        operations=[{
            "type": "buffer",
            "parameters": {"distance": 0.5}
        }]
    )
    
    # Add dependency
    layer_manager.add_dependency("layer2", "layer1")
    
    # Process all layers
    results = layer_processor.process_layers()
    
    # Verify results
    assert all(result.success for result in results.values())
    assert len(layer1.geometry.metadata.operations_log) == 1
    assert len(layer2.geometry.metadata.operations_log) == 1

def test_validation_during_processing(layer_manager, layer_processor, geometry_collection):
    """Test validation during layer processing."""
    # Create layer with invalid operation parameters
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=geometry_collection["point"],
        operations=[{
            "type": "buffer",
            "parameters": {
                "distance": "invalid",  # Should be a number
                "resolution": -1  # Should be >= 4
            }
        }]
    )
    
    # Process layer
    result = layer_processor.process_layer(layer)
    
    # Verify failure
    assert not result.success
    errors = layer_processor.get_layer_errors(layer.name)
    assert len(errors) > 0
    assert any("Distance must be a number" in error for error in errors)

def test_complex_processing_chain(layer_manager, layer_processor, geometry_collection):
    """Test complex processing chain with multiple layers and operations."""
    # Create layers with multiple operations
    layer1 = layer_manager.create_layer(
        name="layer1",
        geometry=geometry_collection["point"],
        operations=[
            {
                "type": "buffer",
                "parameters": {"distance": 1.0}
            },
            {
                "type": "buffer",
                "parameters": {"distance": 0.5}
            }
        ]
    )
    
    layer2 = layer_manager.create_layer(
        name="layer2",
        geometry=geometry_collection["box"],
        operations=[
            {
                "type": "buffer",
                "parameters": {"distance": 0.5}
            }
        ]
    )
    
    layer3 = layer_manager.create_layer(
        name="layer3",
        geometry=geometry_collection["point"],
        operations=[
            {
                "type": "buffer",
                "parameters": {"distance": 0.25}
            }
        ]
    )
    
    # Create dependency chain: layer3 -> layer2 -> layer1
    layer_manager.add_dependency("layer2", "layer1")
    layer_manager.add_dependency("layer3", "layer2")
    
    # Process all layers
    results = layer_processor.process_layers()
    
    # Verify results
    assert all(result.success for result in results.values())
    assert len(layer1.geometry.metadata.operations_log) == 2  # Two buffer operations
    assert len(layer2.geometry.metadata.operations_log) == 1
    assert len(layer3.geometry.metadata.operations_log) == 1
    
    # Verify processing order through operation logs
    all_logs = (
        layer1.geometry.metadata.operations_log +
        layer2.geometry.metadata.operations_log +
        layer3.geometry.metadata.operations_log
    )
    assert len(all_logs) == 4  # Total number of operations

def test_error_propagation(layer_manager, layer_processor, geometry_collection):
    """Test error propagation through the component chain."""
    # Create layer with valid and invalid operations
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=geometry_collection["point"],
        operations=[
            {
                "type": "buffer",
                "parameters": {"distance": 1.0}  # Valid
            },
            {
                "type": "buffer",
                "parameters": {"distance": "invalid"}  # Invalid
            }
        ]
    )
    
    # Process layer
    result = layer_processor.process_layer(layer)
    
    # Verify failure
    assert not result.success
    errors = layer_processor.get_layer_errors(layer.name)
    assert len(errors) > 0
    
    # Check processing state
    state = layer_manager.get_processing_state(layer.name)
    assert len(state['processed_operations']) == 1  # First operation succeeded
    assert state['current_operation'] is None  # No current operation after error
    assert len(state['errors']) > 0  # Error was recorded

def test_state_tracking_across_components(layer_manager, layer_processor, geometry_collection):
    """Test state tracking across all components during processing."""
    # Create layer with multiple operations
    layer = layer_manager.create_layer(
        name="test_layer",
        geometry=geometry_collection["point"],
        operations=[
            {
                "type": "buffer",
                "parameters": {"distance": 1.0}
            },
            {
                "type": "buffer",
                "parameters": {"distance": 0.5}
            }
        ]
    )
    
    # Start processing
    layer_processor.process_layer(layer)
    
    # Verify final state
    manager_state = layer_manager.get_processing_state(layer.name)
    processor_progress = layer_processor.get_layer_progress(layer.name)
    
    assert len(manager_state['processed_operations']) == 2
    assert manager_state['current_operation'] is None
    assert len(manager_state['errors']) == 0
    
    assert processor_progress['total_operations'] == 2
    assert len(processor_progress['processed_operations']) == 2
    assert processor_progress['current_operation'] is None
    assert len(processor_progress['errors']) == 0
    
    # Verify operation logs
    assert len(layer.geometry.metadata.operations_log) == 2
    assert all("buffer" in log for log in layer.geometry.metadata.operations_log) 