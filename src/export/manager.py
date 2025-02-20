"""Export system manager."""

from typing import Dict
from src.core.types import ProcessedGeometry, ExportData
from src.export.interfaces.exporter import GeometryExporter

ExporterDict = Dict[str, GeometryExporter]

class ExportManager:
    """Manages the export process for all formats."""
    
    def __init__(self) -> None:
        self.exporters: ExporterDict = dict()
    
    def register_exporter(self, format_type: str, exporter: ExporterDict) -> None:
        """Register an exporter for a specific format."""
        self.exporters[format_type] = exporter
    
    def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
        """Export using the appropriate registered exporter."""
        if export_data.format_type not in self.exporters:
            raise ValueError(
                f"No exporter registered for format '{export_data.format_type}'. "
                f"Available formats: {list(self.exporters.keys())}"
            )
        
        exporter = self.exporters[export_data.format_type]
        exporter.export(geom, export_data) 