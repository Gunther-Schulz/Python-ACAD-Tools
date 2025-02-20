"""Tests for legend configuration."""

import pytest
from src.config.legend_config import LegendConfig, LegendsConfig
from src.config.position_config import Position

def test_legend_config_creation():
    """Test LegendConfig creation with valid data."""
    pos = Position(x=100.0, y=200.0)
    legend = LegendConfig(name="test_legend", position=pos, style="test_style")
    assert legend.name == "test_legend"
    assert legend.position == pos
    assert legend.style == "test_style"

def test_legend_config_from_dict():
    """Test LegendConfig creation from dictionary."""
    data = {
        'name': 'test_legend',
        'position': {'x': 100.0, 'y': 200.0},
        'style': 'test_style'
    }
    legend = LegendConfig.from_dict(data)
    assert legend.name == 'test_legend'
    assert legend.position.x == 100.0
    assert legend.position.y == 200.0
    assert legend.style == 'test_style'

def test_legend_config_to_dict():
    """Test LegendConfig conversion to dictionary."""
    legend = LegendConfig(
        name="test_legend",
        position=Position(x=100.0, y=200.0),
        style="test_style"
    )
    data = legend.to_dict()
    assert data == {
        'name': 'test_legend',
        'position': {'x': 100.0, 'y': 200.0},
        'style': 'test_style'
    }

def test_legend_config_optional_style():
    """Test LegendConfig with optional style field."""
    data = {
        'name': 'test_legend',
        'position': {'x': 100.0, 'y': 200.0}
    }
    legend = LegendConfig.from_dict(data)
    assert legend.style is None
    
    # Test to_dict with None style
    assert 'style' not in legend.to_dict()

def test_legends_config_creation():
    """Test LegendsConfig creation with valid data."""
    legend1 = LegendConfig(name="legend1", position=Position(x=100.0, y=200.0))
    legend2 = LegendConfig(name="legend2", position=Position(x=300.0, y=400.0), style="style2")
    legends = LegendsConfig(legends=[legend1, legend2])
    assert len(legends.legends) == 2
    assert legends.legends[0] == legend1
    assert legends.legends[1] == legend2

def test_legends_config_from_dict():
    """Test LegendsConfig creation from dictionary."""
    data = {
        'legends': [
            {
                'name': 'legend1',
                'position': {'x': 100.0, 'y': 200.0}
            },
            {
                'name': 'legend2',
                'position': {'x': 300.0, 'y': 400.0},
                'style': 'style2'
            }
        ]
    }
    legends = LegendsConfig.from_dict(data)
    assert len(legends.legends) == 2
    assert legends.legends[0].name == 'legend1'
    assert legends.legends[1].style == 'style2'

def test_legends_config_to_dict():
    """Test LegendsConfig conversion to dictionary."""
    legends = LegendsConfig(legends=[
        LegendConfig(name="legend1", position=Position(x=100.0, y=200.0)),
        LegendConfig(name="legend2", position=Position(x=300.0, y=400.0), style="style2")
    ])
    data = legends.to_dict()
    assert data == {
        'legends': [
            {
                'name': 'legend1',
                'position': {'x': 100.0, 'y': 200.0}
            },
            {
                'name': 'legend2',
                'position': {'x': 300.0, 'y': 400.0},
                'style': 'style2'
            }
        ]
    }

def test_legends_config_empty():
    """Test LegendsConfig with empty legends list."""
    legends = LegendsConfig(legends=[])
    assert len(legends.legends) == 0
    assert legends.to_dict() == {'legends': []} 