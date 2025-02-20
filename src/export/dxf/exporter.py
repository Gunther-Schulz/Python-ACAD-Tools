"""DXF export implementation."""

from typing import Any
from dataclasses import dataclass
from src.core.types import ProcessedGeometry, ExportData
from src.export.interfaces.exporter import GeometryExporter

@dataclass
class DXFConverter:
    """Converts geometry to DXF entities."""
    
    def convert(self, geom: ProcessedGeometry) -> Any:
        """Convert geometry to DXF entity."""
        raise NotImplementedError

@dataclass
class StyleApplicator:
    """Applies styles to DXF entities."""
    
    def apply(self, entity: Any, style_id: str) -> None:
        """Apply style to DXF entity."""
        raise NotImplementedError

class DXFExporter(GeometryExporter):
    """DXF export implementation."""
    
    def __init__(self, converter: DXFConverter, style: StyleApplicator):
        self.converter = converter
        self.style = style
    
    def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
        """Export geometry to DXF format."""
        if export_data.format_type != 'dxf':
            raise ValueError(f"Expected format_type 'dxf', got {export_data.format_type}")
        
        if export_data.style_id is None:
            raise ValueError("style_id is required for DXF export")
        
        # Convert geometry to DXF entity
        entity = self.converter.convert(geom)
        
        # Apply style
        self.style.apply(entity, export_data.style_id) 