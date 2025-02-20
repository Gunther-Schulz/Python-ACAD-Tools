"""Tests for buffer operation."""

import pytest
from shapely.geometry import Point, Polygon, LineString
from src.geometry.operations.buffer import (
    BufferOperation,
    BufferParameters,
    BufferValidator
)
from src.geometry.types.base import GeometryData, GeometryMetadata

@pytest.fixture
def buffer_operation():
    """Create buffer operation instance."""
    return BufferOperation()

@pytest.fixture
def buffer_validator():
    """Create buffer validator instance."""
    return BufferValidator()

@pytest.fixture
def valid_parameters():
    """Create valid buffer parameters."""
    return BufferParameters(
        distance=1.0,
        resolution=16,
        cap_style=1,  # round
        join_style=1,  # round
        mitre_limit=5.0,
        single_sided=False
    )

@pytest.fixture
def test_geometries():
    """Create test geometries."""
    return {
        'point': GeometryData(
            id='test_point',
            geometry=Point(0, 0),
            metadata=GeometryMetadata(source_type='test')
        ),
        'line': GeometryData(
            id='test_line',
            geometry=LineString([(0, 0), (1, 1)]),
            metadata=GeometryMetadata(source_type='test')
        ),
        'polygon': GeometryData(
            id='test_polygon',
            geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            metadata=GeometryMetadata(source_type='test')
        )
    }

def test_buffer_parameters_defaults():
    """Test buffer parameters default values."""
    params = BufferParameters(distance=1.0)
    assert params.distance == 1.0
    assert params.resolution == 16
    assert params.cap_style == 1
    assert params.join_style == 1
    assert params.mitre_limit == 5.0
    assert params.single_sided is False

def test_buffer_parameters_custom():
    """Test buffer parameters with custom values."""
    params = BufferParameters(
        distance=2.0,
        resolution=32,
        cap_style=2,  # flat
        join_style=3,  # bevel
        mitre_limit=2.5,
        single_sided=True
    )
    assert params.distance == 2.0
    assert params.resolution == 32
    assert params.cap_style == 2
    assert params.join_style == 3
    assert params.mitre_limit == 2.5
    assert params.single_sided is True

def test_buffer_validator_valid_parameters(buffer_validator, valid_parameters):
    """Test validator with valid parameters."""
    assert buffer_validator.validate(valid_parameters)
    assert not buffer_validator.get_validation_errors()

@pytest.mark.parametrize('invalid_params,expected_error', [
    (
        BufferParameters(distance='invalid'),
        'Distance must be a number'
    ),
    (
        BufferParameters(distance=1.0, resolution=3),
        'Resolution must be an integer >= 4'
    ),
    (
        BufferParameters(distance=1.0, cap_style=4),
        'Cap style must be 1 (round), 2 (flat), or 3 (square)'
    ),
    (
        BufferParameters(distance=1.0, join_style=4),
        'Join style must be 1 (round), 2 (mitre), or 3 (bevel)'
    ),
    (
        BufferParameters(distance=1.0, mitre_limit=0),
        'Mitre limit must be a positive number'
    )
])
def test_buffer_validator_invalid_parameters(buffer_validator, invalid_params, expected_error):
    """Test validator with invalid parameters."""
    assert not buffer_validator.validate(invalid_params)
    errors = buffer_validator.get_validation_errors()
    assert len(errors) == 1
    assert expected_error in errors[0]

def test_buffer_operation_point(buffer_operation, test_geometries, valid_parameters):
    """Test buffer operation on point geometry."""
    result = buffer_operation.process_geometry(
        test_geometries['point'],
        valid_parameters
    )
    
    # Check result
    assert result.id == 'test_point_buffered'
    assert result.geometry.is_valid
    assert isinstance(result.geometry, Polygon)
    assert result.geometry.area > 0
    
    # Check metadata
    assert result.metadata.source_type == 'test'
    assert len(result.metadata.operations_log) == 1
    assert 'buffer' in result.metadata.operations_log[0]
    assert str(valid_parameters.distance) in result.metadata.operations_log[0]

def test_buffer_operation_line(buffer_operation, test_geometries, valid_parameters):
    """Test buffer operation on line geometry."""
    result = buffer_operation.process_geometry(
        test_geometries['line'],
        valid_parameters
    )
    
    assert result.id == 'test_line_buffered'
    assert result.geometry.is_valid
    assert isinstance(result.geometry, Polygon)
    assert result.geometry.area > 0
    assert result.geometry.length > test_geometries['line'].geometry.length

def test_buffer_operation_polygon(buffer_operation, test_geometries, valid_parameters):
    """Test buffer operation on polygon geometry."""
    result = buffer_operation.process_geometry(
        test_geometries['polygon'],
        valid_parameters
    )
    
    assert result.id == 'test_polygon_buffered'
    assert result.geometry.is_valid
    assert isinstance(result.geometry, Polygon)
    assert result.geometry.area > test_geometries['polygon'].geometry.area

def test_buffer_operation_zero_distance(buffer_operation, test_geometries):
    """Test buffer operation with zero distance."""
    params = BufferParameters(distance=0.0)
    result = buffer_operation.process_geometry(
        test_geometries['polygon'],
        params
    )
    
    assert result.geometry.is_valid
    assert result.geometry.area == pytest.approx(
        test_geometries['polygon'].geometry.area,
        rel=1e-10
    )

def test_buffer_operation_negative_distance(buffer_operation, test_geometries):
    """Test buffer operation with negative distance."""
    params = BufferParameters(distance=-1.0)
    result = buffer_operation.process_geometry(
        test_geometries['polygon'],
        params
    )
    
    assert result.geometry.is_valid
    assert result.geometry.area < test_geometries['polygon'].geometry.area

def test_buffer_operation_different_styles(buffer_operation, test_geometries):
    """Test buffer operation with different cap and join styles."""
    # Test flat cap and mitre join
    params = BufferParameters(
        distance=1.0,
        cap_style=2,  # flat
        join_style=2  # mitre
    )
    result1 = buffer_operation.process_geometry(
        test_geometries['line'],
        params
    )
    
    # Test square cap and bevel join
    params = BufferParameters(
        distance=1.0,
        cap_style=3,  # square
        join_style=3  # bevel
    )
    result2 = buffer_operation.process_geometry(
        test_geometries['line'],
        params
    )
    
    # Results should be different due to different styles
    assert result1.geometry.area != pytest.approx(result2.geometry.area, rel=1e-10)

def test_buffer_operation_single_sided(buffer_operation, test_geometries):
    """Test buffer operation with single sided option."""
    params = BufferParameters(
        distance=1.0,
        single_sided=True
    )
    result = buffer_operation.process_geometry(
        test_geometries['line'],
        params
    )
    
    assert result.geometry.is_valid
    # Single sided buffer should have different area than regular buffer
    regular_params = BufferParameters(distance=1.0)
    regular_result = buffer_operation.process_geometry(
        test_geometries['line'],
        regular_params
    )
    assert result.geometry.area != pytest.approx(regular_result.geometry.area, rel=1e-10)

def test_buffer_operation_high_resolution(buffer_operation, test_geometries):
    """Test buffer operation with high resolution."""
    params = BufferParameters(
        distance=1.0,
        resolution=64  # High resolution
    )
    result = buffer_operation.process_geometry(
        test_geometries['point'],
        params
    )
    
    # Higher resolution should result in more vertices
    low_res_params = BufferParameters(distance=1.0, resolution=4)
    low_res_result = buffer_operation.process_geometry(
        test_geometries['point'],
        low_res_params
    )
    
    assert len(result.geometry.exterior.coords) > len(low_res_result.geometry.exterior.coords) 