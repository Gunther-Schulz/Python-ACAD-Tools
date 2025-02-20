"""Main project coordinator module."""

import os
from typing import Optional
from src.core.utils import setup_logger, ensure_directory
from src.config.config_manager import ConfigManager
from src.geometry.geometry_manager import GeometryManager
from src.export.dxf_exporter import DXFExporter
from src.export.style_manager import StyleManager
from src.export.layer_manager import LayerManager

class Project:
    """Main project coordinator class."""
    
    def __init__(self, project_name: str, log_file: Optional[str] = None):
        """Initialize project with name and optional log file."""
        self.project_name = project_name
        self.logger = setup_logger(f"project.{project_name}", log_file)
        self._initialize_components()
        
    def _initialize_components(self) -> None:
        """Initialize all project components."""
        try:
            # Initialize configuration
            self.logger.info("Initializing configuration manager")
            self.config_manager = ConfigManager(self.project_name)
            self.project_config = self.config_manager.load_project_config()
            
            # Initialize geometry processing
            self.logger.info("Initializing geometry manager")
            self.geometry_manager = GeometryManager(
                self.config_manager.load_geometry_layers()
            )
            
            # Initialize export components
            self.logger.info("Initializing export components")
            style_configs = self.config_manager.load_styles()
            self.style_manager = StyleManager(style_configs)
            self.layer_manager = LayerManager()
            self.dxf_exporter = DXFExporter(
                self.style_manager,
                self.layer_manager
            )
            
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
                    
                    # Export to DXF if needed
                    if layer.update_dxf:
                        self.logger.info(f"Exporting layer to DXF: {layer_name}")
                        style = self.style_manager.get_style(layer.style)
                        self.dxf_exporter.export_layer(layer, style)
                        
                except Exception as e:
                    self.logger.error(f"Failed to process layer {layer_name}: {str(e)}")
                    raise
            
            # Finalize export
            self.logger.info("Finalizing DXF export")
            self.dxf_exporter.finalize_export()
            
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
            self.dxf_exporter.cleanup()
        except Exception as cleanup_error:
            self.logger.error(f"Failed to cleanup after error: {str(cleanup_error)}") 