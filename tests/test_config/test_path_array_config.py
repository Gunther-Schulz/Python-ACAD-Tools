"""Tests for path array configuration."""

import pytest
from src.config.path_array_config import PathArrayConfig, PathArraysConfig

def test_path_array_config_creation():
    """Test PathArrayConfig creation with valid data."""
    array = PathArrayConfig(
        name="test_array",
        path="test_path",
        block="test_block",
        spacing=50.0,
        align=True,
        layer="test_layer"
    )
    assert array.name == "test_array"
    assert array.path == "test_path"
    assert array.block == "test_block"
    assert array.spacing == 50.0
    assert array.align is True
    assert array.layer == "test_layer"

def test_path_array_config_from_dict():
    """Test PathArrayConfig creation from dictionary."""
    data = {
        'name': 'test_array',
        'path': 'test_path',
        'block': 'test_block',
        'spacing': 50.0,
        'align': True,
        'layer': 'test_layer'
    }
    array = PathArrayConfig.from_dict(data)
    assert array.name == 'test_array'
    assert array.path == 'test_path'
    assert array.block == 'test_block'
    assert array.spacing == 50.0
    assert array.align is True
    assert array.layer == 'test_layer'

def test_path_array_config_to_dict():
    """Test PathArrayConfig conversion to dictionary."""
    array = PathArrayConfig(
        name="test_array",
        path="test_path",
        block="test_block",
        spacing=50.0,
        align=True,
        layer="test_layer"
    )
    data = array.to_dict()
    assert data == {
        'name': 'test_array',
        'path': 'test_path',
        'block': 'test_block',
        'spacing': 50.0,
        'align': True,
        'layer': 'test_layer'
    }

def test_path_array_config_defaults():
    """Test PathArrayConfig with default values."""
    data = {
        'name': 'test_array',
        'path': 'test_path',
        'block': 'test_block',
        'spacing': 50.0
    }
    array = PathArrayConfig.from_dict(data)
    assert array.align is True  # Default align
    assert array.layer is None  # Default layer
    
    # Test to_dict with default values
    data = array.to_dict()
    assert data['align'] is True
    assert 'layer' not in data

def test_path_arrays_config_creation():
    """Test PathArraysConfig creation with valid data."""
    array1 = PathArrayConfig(
        name="array1",
        path="path1",
        block="block1",
        spacing=50.0
    )
    array2 = PathArrayConfig(
        name="array2",
        path="path2",
        block="block2",
        spacing=75.0,
        align=False,
        layer="test_layer"
    )
    arrays = PathArraysConfig(path_arrays=[array1, array2])
    assert len(arrays.path_arrays) == 2
    assert arrays.path_arrays[0] == array1
    assert arrays.path_arrays[1] == array2

def test_path_arrays_config_from_dict():
    """Test PathArraysConfig creation from dictionary."""
    data = {
        'pathArrays': [
            {
                'name': 'array1',
                'path': 'path1',
                'block': 'block1',
                'spacing': 50.0
            },
            {
                'name': 'array2',
                'path': 'path2',
                'block': 'block2',
                'spacing': 75.0,
                'align': False,
                'layer': 'test_layer'
            }
        ]
    }
    arrays = PathArraysConfig.from_dict(data)
    assert len(arrays.path_arrays) == 2
    assert arrays.path_arrays[0].name == 'array1'
    assert arrays.path_arrays[1].align is False

def test_path_arrays_config_to_dict():
    """Test PathArraysConfig conversion to dictionary."""
    arrays = PathArraysConfig(path_arrays=[
        PathArrayConfig(
            name="array1",
            path="path1",
            block="block1",
            spacing=50.0
        ),
        PathArrayConfig(
            name="array2",
            path="path2",
            block="block2",
            spacing=75.0,
            align=False,
            layer="test_layer"
        )
    ])
    data = arrays.to_dict()
    assert data == {
        'pathArrays': [
            {
                'name': 'array1',
                'path': 'path1',
                'block': 'block1',
                'spacing': 50.0,
                'align': True
            },
            {
                'name': 'array2',
                'path': 'path2',
                'block': 'block2',
                'spacing': 75.0,
                'align': False,
                'layer': 'test_layer'
            }
        ]
    }

def test_path_arrays_config_empty():
    """Test PathArraysConfig with empty arrays list."""
    arrays = PathArraysConfig(path_arrays=[])
    assert len(arrays.path_arrays) == 0
    assert arrays.to_dict() == {'pathArrays': []} 