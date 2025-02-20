"""Tests for export manager."""

import pytest
from src.export.manager import ExportManager
from src.core.types import ProcessedGeometry, ExportData
from tests.test_core.test_interfaces import MockGeometry, MockExporter

@pytest.fixture
def export_manager():
    """Create an export manager for testing."""
    return ExportManager()

@pytest.fixture
def mock_exporter():
    """Create a mock exporter for testing."""
    return MockExporter()

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
def export_data():
    """Create export data for testing."""
    return ExportData(
        id="test",
        format_type="test",
        style_id="test",
        layer_name="test",
        target_crs="EPSG:4326",
        properties={}
    )

def test_register_exporter(export_manager, mock_exporter):
    """Test registering an exporter."""
    export_manager.register_exporter("test", mock_exporter)
    assert "test" in export_manager.exporters
    assert export_manager.exporters["test"] is mock_exporter

def test_export_with_registered_exporter(
    export_manager, mock_exporter, processed_geometry, export_data
):
    """Test exporting with a registered exporter."""
    export_manager.register_exporter("test", mock_exporter)
    # Should not raise
    export_manager.export(processed_geometry, export_data)

def test_export_with_unregistered_format(
    export_manager, processed_geometry, export_data
):
    """Test that exporting with an unregistered format raises."""
    with pytest.raises(ValueError) as exc:
        export_manager.export(processed_geometry, export_data)
    assert "No exporter registered for format 'test'" in str(exc.value) 