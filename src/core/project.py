"""Main project coordinator module."""

import os
import yaml
from pathlib import Path
from typing import Optional
from src.core.utils import setup_logger, ensure_directory
from src.core.types import ExportData
from src.core.style_manager import StyleManager
from src.config.config_manager import ConfigManager
from src.geometry.geometry_manager import GeometryManager
from src.export.manager import ExportManager
from src.export.dxf.exporter import DXFExporter, DXFConverter
from src.export.dxf.style import StyleApplicator
from src.export.dxf.layer import LayerManager
from src.export.dxf.validators import DXFStyleValidator

def get_project_dir(project_name: str) -> Path:
    """Get project directory path.
    
    Args:
        project_name: Name of the project
        
    Returns:
        Path to project directory
    """
    # Get repository root directory (two levels up from this file)
    root_dir = Path(__file__).parent.parent.parent
    
    # Project directory is in the projects/ subdirectory
    project_dir = root_dir / 'projects' / project_name
    
    if not project_dir.exists():
        raise ValueError(f"Project directory does not exist: {project_dir}")
    
    return project_dir

def load_folder_prefix() -> Optional[str]:
    """Load folder prefix from projects.yaml.
    
    Returns:
        Folder prefix if found, None otherwise
    """
    # Get repository root directory (two levels up from this file)
    root_dir = Path(__file__).parent.parent.parent
    projects_yaml = root_dir / 'projects.yaml'
    
    if not projects_yaml.exists():
        return None
        
    try:
        with open(projects_yaml, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('folderPrefix')
    except Exception:
        return None

class Project:
    """Main project coordinator class."""
    
    def __init__(self, project_name: str, log_file: Optional[str] = None):
        """Initialize project with name and optional log file."""
        self.project_name = project_name
        self.project_dir = get_project_dir(project_name)
        self.folder_prefix = load_folder_prefix()
        self.logger = setup_logger(f"project.{project_name}", log_file)
        self._initialize_components()
        
    def _initialize_components(self) -> None:
        """Initialize all project components."""
        try:
            # Initialize configuration
            self.logger.info("Initializing configuration manager")
            self.config_manager = ConfigManager(str(self.project_dir))
            self.project_config = self.config_manager.load_project_config(
                folder_prefix=self.folder_prefix
            )
            
            # Initialize style management
            self.logger.info("Initializing style manager")
            style_configs = self.config_manager.load_styles()
            self.style_manager = StyleManager(
                styles=style_configs,
                validator=DXFStyleValidator()
            )
            
            # Initialize geometry processing
            self.logger.info("Initializing geometry manager")
            self.geometry_manager = GeometryManager(
                self.config_manager.load_geometry_layers(
                    folder_prefix=self.folder_prefix
                )
            )
            
            # Initialize export components
            self.logger.info("Initializing export components")
            
            # Create export manager and register DXF exporter
            self.export_manager = ExportManager()
            dxf_exporter = DXFExporter(
                converter=DXFConverter(),
                style=StyleApplicator(styles=style_configs)
            )
            self.export_manager.register_exporter('dxf', dxf_exporter)
            
            # Ensure output directory exists
            if self.project_config.shapefile_output_dir:
                ensure_directory(self.project_config.shapefile_output_dir)
                
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {str(e)}")
            raise
    
    def process(self) -> None:
        """Process the entire project."""
        try:
            self.logger.info("Starting project processing")
            
            # Process each layer
            for layer_name in self.geometry_manager.get_layer_names():
                try:
                    self.logger.info(f"Processing layer: {layer_name}")
                    
                    # Get processed geometry
                    layer = self.geometry_manager.process_layer(layer_name)
                    
                    # Export using export manager
                    if layer.update_dxf:
                        self.logger.info(f"Exporting layer: {layer_name}")
                        export_data = ExportData(
                            id=layer_name,
                            format_type='dxf',
                            style_id=layer.style,
                            layer_name=layer_name,
                            target_crs=None,
                            properties={}
                        )
                        self.export_manager.export(layer, export_data)
                        
                except Exception as e:
                    self.logger.error(f"Failed to process layer {layer_name}: {str(e)}")
                    raise
            
            self.logger.info("Project processing completed successfully")
            
        except Exception as e:
            self.logger.error(f"Project processing failed: {str(e)}")
            self._handle_error(e)
            raise
    
    def _handle_error(self, error: Exception) -> None:
        """Handle project processing errors."""
        # Log error details
        self.logger.error(f"Error type: {type(error).__name__}")
        self.logger.error(f"Error message: {str(error)}")
        
        # Cleanup if needed
        try:
            self.export_manager.cleanup()
        except Exception as cleanup_error:
            self.logger.error(f"Failed to cleanup after error: {str(cleanup_error)}") 