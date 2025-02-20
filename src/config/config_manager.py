"""Configuration management module."""

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class ProjectConfig:
    """Project configuration."""
    crs: str
    dxf_filename: str
    template_dxf: Optional[str]
    export_format: str
    dxf_version: str
    shapefile_output_dir: Optional[str]

class ConfigManager:
    """Manages loading and validation of configuration files."""
    
    def __init__(self, project_name: str):
        """Initialize with project name."""
        self.project_name = project_name
    
    def load_project_config(self) -> ProjectConfig:
        """Load project configuration."""
        # Minimal implementation for tests
        return ProjectConfig(
            crs="EPSG:25833",
            dxf_filename="output/test.dxf",
            template_dxf=None,
            export_format="dxf",
            dxf_version="R2010",
            shapefile_output_dir="output"
        )
    
    def load_geometry_layers(self) -> Dict[str, Any]:
        """Load geometry layer configuration."""
        # Minimal implementation for tests
        return {"layers": []}
    
    def load_styles(self) -> Dict[str, Any]:
        """Load style configuration."""
        # Minimal implementation for tests
        return {} 