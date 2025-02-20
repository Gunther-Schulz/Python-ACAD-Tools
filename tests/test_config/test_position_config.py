"""Tests for position configuration."""

import pytest
from src.config.position_config import Position

def test_position_creation():
    """Test Position creation with valid data."""
    pos = Position(x=100.0, y=200.0)
    assert pos.x == 100.0
    assert pos.y == 200.0

def test_position_from_dict():
    """Test Position creation from dictionary."""
    data = {'x': 100.0, 'y': 200.0}
    pos = Position.from_dict(data)
    assert pos.x == 100.0
    assert pos.y == 200.0

def test_position_to_dict():
    """Test Position conversion to dictionary."""
    pos = Position(x=100.0, y=200.0)
    data = pos.to_dict()
    assert data == {'x': 100.0, 'y': 200.0}

def test_position_invalid_data():
    """Test Position creation with invalid data."""
    with pytest.raises(TypeError):
        Position.from_dict({'x': 'invalid', 'y': 200.0})
    with pytest.raises(TypeError):
        Position.from_dict({'x': 100.0, 'y': 'invalid'})
    with pytest.raises(KeyError):
        Position.from_dict({'x': 100.0})  # Missing y
    with pytest.raises(KeyError):
        Position.from_dict({'y': 200.0})  # Missing x 