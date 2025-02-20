"""Project configuration module."""

from dataclasses import dataclass
from typing import Optional
from src.core.utils import resolve_path

@dataclass
class ProjectConfig:
    """Project configuration."""
    crs: str
    dxf_filename: str
    template_dxf: Optional[str]
    export_format: str
    dxf_version: str
    shapefile_output_dir: Optional[str]

    @classmethod
    def from_dict(cls, data: dict, folder_prefix: Optional[str] = None) -> 'ProjectConfig':
        """Create ProjectConfig from dictionary."""
        return cls(
            crs=data['crs'],
            dxf_filename=resolve_path(data['dxfFilename'], folder_prefix),
            template_dxf=resolve_path(data.get('template'), folder_prefix),
            export_format=data['exportFormat'],
            dxf_version=data['dxfVersion'],
            shapefile_output_dir=resolve_path(data.get('shapefileOutputDir'), folder_prefix)
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'crs': self.crs,
            'dxfFilename': self.dxf_filename,
            'template': self.template_dxf,
            'exportFormat': self.export_format,
            'dxfVersion': self.dxf_version,
            'shapefileOutputDir': self.shapefile_output_dir
        } 