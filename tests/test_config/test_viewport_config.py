"""Tests for viewport configuration."""

import pytest
from src.config.viewport_config import ViewportConfig, ViewportsConfig
from src.config.position_config import Position

def test_viewport_config_creation():
    """Test ViewportConfig creation with valid data."""
    center = Position(x=100.0, y=200.0)
    viewport = ViewportConfig(
        name="test_viewport",
        center=center,
        scale=50.0,
        rotation=45.0
    )
    assert viewport.name == "test_viewport"
    assert viewport.center == center
    assert viewport.scale == 50.0
    assert viewport.rotation == 45.0

def test_viewport_config_from_dict():
    """Test ViewportConfig creation from dictionary."""
    data = {
        'name': 'test_viewport',
        'center': {'x': 100.0, 'y': 200.0},
        'scale': 50.0,
        'rotation': 45.0
    }
    viewport = ViewportConfig.from_dict(data)
    assert viewport.name == 'test_viewport'
    assert viewport.center.x == 100.0
    assert viewport.center.y == 200.0
    assert viewport.scale == 50.0
    assert viewport.rotation == 45.0

def test_viewport_config_to_dict():
    """Test ViewportConfig conversion to dictionary."""
    viewport = ViewportConfig(
        name="test_viewport",
        center=Position(x=100.0, y=200.0),
        scale=50.0,
        rotation=45.0
    )
    data = viewport.to_dict()
    assert data == {
        'name': 'test_viewport',
        'center': {'x': 100.0, 'y': 200.0},
        'scale': 50.0,
        'rotation': 45.0
    }

def test_viewport_config_default_rotation():
    """Test ViewportConfig with default rotation."""
    data = {
        'name': 'test_viewport',
        'center': {'x': 100.0, 'y': 200.0},
        'scale': 50.0
    }
    viewport = ViewportConfig.from_dict(data)
    assert viewport.rotation == 0.0
    
    # Test to_dict includes default rotation
    assert viewport.to_dict()['rotation'] == 0.0

def test_viewports_config_creation():
    """Test ViewportsConfig creation with valid data."""
    viewport1 = ViewportConfig(
        name="viewport1",
        center=Position(x=100.0, y=200.0),
        scale=50.0
    )
    viewport2 = ViewportConfig(
        name="viewport2",
        center=Position(x=300.0, y=400.0),
        scale=75.0,
        rotation=90.0
    )
    viewports = ViewportsConfig(viewports=[viewport1, viewport2])
    assert len(viewports.viewports) == 2
    assert viewports.viewports[0] == viewport1
    assert viewports.viewports[1] == viewport2

def test_viewports_config_from_dict():
    """Test ViewportsConfig creation from dictionary."""
    data = {
        'viewports': [
            {
                'name': 'viewport1',
                'center': {'x': 100.0, 'y': 200.0},
                'scale': 50.0
            },
            {
                'name': 'viewport2',
                'center': {'x': 300.0, 'y': 400.0},
                'scale': 75.0,
                'rotation': 90.0
            }
        ]
    }
    viewports = ViewportsConfig.from_dict(data)
    assert len(viewports.viewports) == 2
    assert viewports.viewports[0].name == 'viewport1'
    assert viewports.viewports[1].rotation == 90.0

def test_viewports_config_to_dict():
    """Test ViewportsConfig conversion to dictionary."""
    viewports = ViewportsConfig(viewports=[
        ViewportConfig(
            name="viewport1",
            center=Position(x=100.0, y=200.0),
            scale=50.0
        ),
        ViewportConfig(
            name="viewport2",
            center=Position(x=300.0, y=400.0),
            scale=75.0,
            rotation=90.0
        )
    ])
    data = viewports.to_dict()
    assert data == {
        'viewports': [
            {
                'name': 'viewport1',
                'center': {'x': 100.0, 'y': 200.0},
                'scale': 50.0,
                'rotation': 0.0
            },
            {
                'name': 'viewport2',
                'center': {'x': 300.0, 'y': 400.0},
                'scale': 75.0,
                'rotation': 90.0
            }
        ]
    }

def test_viewports_config_empty():
    """Test ViewportsConfig with empty viewports list."""
    viewports = ViewportsConfig(viewports=[])
    assert len(viewports.viewports) == 0
    assert viewports.to_dict() == {'viewports': []} 