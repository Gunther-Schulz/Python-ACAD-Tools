"""Tests for core interfaces."""

import pytest
from typing import List, Dict, Any
from src.core.types import (
    Geometry, GeometrySource, GeometryOperation, GeometryExporter,
    GeometryData, ProcessedGeometry, ExportData
)

class MockGeometry:
    """Mock implementation of Geometry protocol."""
    def get_bounds(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, 1.0, 1.0)
    
    def get_coordinates(self) -> List[tuple[float, float]]:
        return [(0.0, 0.0), (1.0, 1.0)]

class MockGeometrySource:
    """Mock implementation of GeometrySource protocol."""
    def read(self) -> GeometryData:
        return GeometryData(
            id="test",
            geom=MockGeometry(),
            metadata={},
            source_type="test",
            source_crs="EPSG:4326"
        )
    
    def get_metadata(self) -> Dict[str, Any]:
        return {"test": "metadata"}

class MockOperation:
    """Mock implementation of GeometryOperation protocol."""
    def execute(self, geom: Geometry) -> Geometry:
        return geom

class MockExporter:
    """Mock implementation of GeometryExporter protocol."""
    def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
        pass

def test_geometry_protocol():
    """Test that MockGeometry implements Geometry protocol."""
    geom = MockGeometry()
    assert isinstance(geom, Geometry)
    assert geom.get_bounds() == (0.0, 0.0, 1.0, 1.0)
    assert geom.get_coordinates() == [(0.0, 0.0), (1.0, 1.0)]

def test_geometry_source_protocol():
    """Test that MockGeometrySource implements GeometrySource protocol."""
    source = MockGeometrySource()
    assert isinstance(source, GeometrySource)
    data = source.read()
    assert isinstance(data, GeometryData)
    assert isinstance(data.geom, Geometry)
    assert data.source_type == "test"
    assert data.source_crs == "EPSG:4326"

def test_operation_protocol():
    """Test that MockOperation implements GeometryOperation protocol."""
    op = MockOperation()
    assert isinstance(op, GeometryOperation)
    geom = MockGeometry()
    result = op.execute(geom)
    assert isinstance(result, Geometry)

def test_exporter_protocol():
    """Test that MockExporter implements GeometryExporter protocol."""
    exporter = MockExporter()
    assert isinstance(exporter, GeometryExporter)
    
    geom_data = GeometryData(
        id="test",
        geom=MockGeometry(),
        metadata={},
        source_type="test",
        source_crs="EPSG:4326"
    )
    processed = ProcessedGeometry(data=geom_data, processing_log=[])
    export_data = ExportData(
        id="test",
        format_type="test",
        style_id="test",
        layer_name="test",
        target_crs="EPSG:4326",
        properties={}
    )
    
    # Should not raise
    exporter.export(processed, export_data) 