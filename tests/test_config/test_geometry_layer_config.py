"""Tests for geometry layer configuration."""

import pytest
from src.config.geometry_layer_config import GeometryOperation, GeometryLayerConfig

def test_geometry_operation():
    """Test GeometryOperation configuration."""
    # Test minimal operation
    op = GeometryOperation(type="buffer")
    assert op.type == "buffer"
    assert op.layers is None
    assert op.distance is None
    
    # Test full operation
    op = GeometryOperation(
        type="buffer",
        layers=["layer1", "layer2"],
        distance=1.0,
        reverse_difference=True,
        use_buffer_trick=True,
        buffer_distance=0.5,
        use_asymmetric_buffer=False,
        min_area=1.0,
        params={"param1": "value1"}
    )
    assert op.type == "buffer"
    assert op.layers == ["layer1", "layer2"]
    assert op.distance == 1.0
    assert op.reverse_difference is True
    assert op.use_buffer_trick is True
    assert op.buffer_distance == 0.5
    assert op.use_asymmetric_buffer is False
    assert op.min_area == 1.0
    assert op.params == {"param1": "value1"}
    
    # Test from_dict
    data = {
        'type': 'buffer',
        'layers': 'layer1',
        'distance': 1.0,
        'reverseDifference': 'auto',
        'useBufferTrick': True
    }
    op = GeometryOperation.from_dict(data)
    assert op.type == "buffer"
    assert op.layers == "layer1"
    assert op.distance == 1.0
    assert op.reverse_difference == "auto"
    assert op.use_buffer_trick is True
    
    # Test to_dict
    data = op.to_dict()
    assert data['type'] == "buffer"
    assert data['layers'] == "layer1"
    assert data['distance'] == 1.0
    assert data['reverseDifference'] == "auto"
    assert data['useBufferTrick'] is True

def test_geometry_layer_config():
    """Test GeometryLayerConfig configuration."""
    # Test minimal layer
    layer = GeometryLayerConfig(name="test_layer")
    assert layer.name == "test_layer"
    assert layer.update_dxf is True
    assert layer.close is False
    assert layer.shape_file is None
    assert layer.simple_label_column is None
    assert layer.style is None
    assert layer.operations is None
    assert layer.viewports is None
    assert layer.hatches is None
    
    # Test full layer
    operations = [
        GeometryOperation(type="buffer", distance=1.0),
        GeometryOperation(type="dissolve")
    ]
    viewports = [{"name": "viewport1", "style": "style1"}]
    hatches = [{"name": "hatch1", "pattern": "SOLID"}]
    
    layer = GeometryLayerConfig(
        name="test_layer",
        update_dxf=False,
        close=True,
        shape_file="input/test.shp",
        simple_label_column="name",
        style="default_style",
        operations=operations,
        viewports=viewports,
        hatches=hatches
    )
    assert layer.name == "test_layer"
    assert layer.update_dxf is False
    assert layer.close is True
    assert layer.shape_file == "input/test.shp"
    assert layer.simple_label_column == "name"
    assert layer.style == "default_style"
    assert len(layer.operations) == 2
    assert layer.viewports == viewports
    assert layer.hatches == hatches
    
    # Test from_dict
    data = {
        'name': 'test_layer',
        'updateDxf': False,
        'close': True,
        'shapeFile': 'input/test.shp',
        'simpleLabelColumn': 'name',
        'style': 'default_style',
        'operations': [
            {'type': 'buffer', 'distance': 1.0},
            {'type': 'dissolve'}
        ],
        'viewports': viewports,
        'hatches': hatches
    }
    layer = GeometryLayerConfig.from_dict(data)
    assert layer.name == "test_layer"
    assert layer.update_dxf is False
    assert layer.close is True
    assert layer.shape_file == "input/test.shp"
    assert layer.simple_label_column == "name"
    assert layer.style == "default_style"
    assert len(layer.operations) == 2
    assert layer.operations[0].type == "buffer"
    assert layer.operations[0].distance == 1.0
    assert layer.operations[1].type == "dissolve"
    assert layer.viewports == viewports
    assert layer.hatches == hatches
    
    # Test from_dict with folder prefix
    layer = GeometryLayerConfig.from_dict(data, folder_prefix="project1")
    assert layer.shape_file == "project1/input/test.shp"
    
    # Test to_dict
    data = layer.to_dict()
    assert data['name'] == "test_layer"
    assert data['updateDxf'] is False
    assert data['close'] is True
    assert data['shapeFile'] == "project1/input/test.shp"
    assert data['simpleLabelColumn'] == "name"
    assert data['style'] == "default_style"
    assert len(data['operations']) == 2
    assert data['operations'][0]['type'] == "buffer"
    assert data['operations'][0]['distance'] == 1.0
    assert data['operations'][1]['type'] == "dissolve"
    assert data['viewports'] == viewports
    assert data['hatches'] == hatches 