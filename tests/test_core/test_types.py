"""Tests for core type definitions."""

import pytest
from src.core.types import GeometryType, Bounds, GeometryAttributes

def test_geometry_type_enum():
    """Test GeometryType enum values."""
    assert GeometryType.POINT.value == "point"
    assert GeometryType.LINESTRING.value == "linestring"
    assert GeometryType.POLYGON.value == "polygon"
    assert GeometryType.MULTIPOINT.value == "multipoint"
    assert GeometryType.MULTILINESTRING.value == "multilinestring"
    assert GeometryType.MULTIPOLYGON.value == "multipolygon"
    assert GeometryType.GEOMETRYCOLLECTION.value == "geometrycollection"

def test_bounds_dataclass():
    """Test Bounds dataclass creation and attributes."""
    bounds = Bounds(minx=0.0, miny=0.0, maxx=10.0, maxy=10.0)
    
    assert bounds.minx == 0.0
    assert bounds.miny == 0.0
    assert bounds.maxx == 10.0
    assert bounds.maxy == 10.0
    
    # Test bounds validation
    with pytest.raises(TypeError):
        Bounds(minx="0", miny=0.0, maxx=10.0, maxy=10.0)  # Wrong type

def test_geometry_attributes():
    """Test GeometryAttributes dataclass."""
    # Test with minimal attributes
    attrs = GeometryAttributes(
        id="test1",
        properties={"name": "Test Feature"}
    )
    assert attrs.id == "test1"
    assert attrs.properties["name"] == "Test Feature"
    assert attrs.bounds is None
    
    # Test with bounds
    bounds = Bounds(minx=0.0, miny=0.0, maxx=10.0, maxy=10.0)
    attrs_with_bounds = GeometryAttributes(
        id="test2",
        properties={"name": "Test Feature 2"},
        bounds=bounds
    )
    assert attrs_with_bounds.bounds == bounds
    
    # Test validation
    with pytest.raises(TypeError):
        GeometryAttributes(
            id=123,  # Wrong type for id
            properties={}
        ) 