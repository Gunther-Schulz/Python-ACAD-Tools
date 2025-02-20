"""Tests for DXF export."""

import pytest
from dataclasses import dataclass
from src.export.dxf.exporter import DXFExporter, DXFConverter, StyleApplicator
from src.core.types import ProcessedGeometry, ExportData
from tests.test_core.test_interfaces import MockGeometry

@dataclass
class MockDXFEntity:
    """Mock DXF entity for testing."""
    style_id: str = None

class MockDXFConverter(DXFConverter):
    """Mock DXF converter for testing."""
    def convert(self, geom: ProcessedGeometry) -> MockDXFEntity:
        return MockDXFEntity()

class MockStyleApplicator(StyleApplicator):
    """Mock style applicator for testing."""
    def apply(self, entity: MockDXFEntity, style_id: str) -> None:
        entity.style_id = style_id

@pytest.fixture
def dxf_exporter():
    """Create a DXF exporter for testing."""
    return DXFExporter(
        converter=MockDXFConverter(),
        style=MockStyleApplicator()
    )

@pytest.fixture
def processed_geometry():
    """Create a processed geometry for testing."""
    from src.core.types import GeometryData
    geom_data = GeometryData(
        id="test",
        geom=MockGeometry(),
        metadata={},
        source_type="test",
        source_crs="EPSG:4326"
    )
    return ProcessedGeometry(data=geom_data, processing_log=[])

@pytest.fixture
def dxf_export_data():
    """Create DXF export data for testing."""
    return ExportData(
        id="test",
        format_type="dxf",
        style_id="test_style",
        layer_name="test_layer",
        target_crs=None,
        properties={}
    )

def test_dxf_export_wrong_format(dxf_exporter, processed_geometry, dxf_export_data):
    """Test that exporting with wrong format raises."""
    wrong_data = ExportData(
        id="test",
        format_type="shapefile",  # Wrong format
        style_id="test_style",
        layer_name="test_layer",
        target_crs=None,
        properties={}
    )
    with pytest.raises(ValueError) as exc:
        dxf_exporter.export(processed_geometry, wrong_data)
    assert "Expected format_type 'dxf'" in str(exc.value)

def test_dxf_export_missing_style(dxf_exporter, processed_geometry, dxf_export_data):
    """Test that exporting without style raises."""
    no_style_data = ExportData(
        id="test",
        format_type="dxf",
        style_id=None,  # Missing style
        layer_name="test_layer",
        target_crs=None,
        properties={}
    )
    with pytest.raises(ValueError) as exc:
        dxf_exporter.export(processed_geometry, no_style_data)
    assert "style_id is required for DXF export" in str(exc.value)

def test_dxf_export_success(dxf_exporter, processed_geometry, dxf_export_data):
    """Test successful DXF export."""
    # Should not raise
    dxf_exporter.export(processed_geometry, dxf_export_data) 