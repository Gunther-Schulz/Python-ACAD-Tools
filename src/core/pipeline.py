"""Core processing pipeline for ACAD Tools."""

from typing import Optional
import ezdxf
from .project.loader import ProjectLoader
from .layer import LayerProcessor
from .export.exporter import DXFExporter
from ..utils.logging import log_debug, log_error

class Pipeline:
    """Main processing pipeline that coordinates project loading, layer processing, and DXF export."""
    
    def __init__(self, project_name: str, plot_ops: bool = False):
        """Initialize the pipeline with a project name.
        
        Args:
            project_name: Name of the project to process
            plot_ops: Whether to plot layer operations for debugging
        """
        self.project_loader = ProjectLoader(project_name)
        if not self.project_loader.project_settings:
            raise ValueError(
                f"Could not load settings for project '{project_name}'. "
                "Please check if the project files exist and are valid YAML."
            )
        
        # Initialize core processors
        self.layer_processor = LayerProcessor(self.project_loader, plot_ops)
        self.dxf_exporter = DXFExporter(self.project_loader, self.layer_processor)
        self.doc = None

    def process(self, skip_dxf_processor: bool = False) -> Optional[ezdxf.document.Drawing]:
        """Process the project and return the DXF document.
        
        Args:
            skip_dxf_processor: Whether to skip DXF preprocessing
        
        Returns:
            The processed DXF document
        """
        try:
            # Load or create DXF document
            doc = self.dxf_exporter._load_or_create_dxf(skip_dxf_processor)
            self.layer_processor.set_dxf_document(doc)
            
            # Process layers
            self.layer_processor.process_layers()
            
            # Export to DXF
            self.dxf_exporter.export_to_dxf(skip_dxf_processor=True)
            
            # Store and return document
            self.doc = doc
            return doc
            
        except Exception as e:
            log_error(f"Error during pipeline processing: {str(e)}")
            raise

    def cleanup(self):
        """Perform cleanup operations on the DXF document."""
        if self.doc:
            from ..utils.cleanup import cleanup_document
            log_debug("Performing document cleanup...")
            cleanup_document(self.doc)
            log_debug("Document cleanup completed") 