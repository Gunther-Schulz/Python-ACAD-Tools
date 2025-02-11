from typing import Dict, Any, Optional
from pathlib import Path
import ezdxf
from ezdxf.document import Drawing

from core.config import ConfigManager
from core.processor import BaseProcessor
from utils.logging import (
    setup_logging, log_debug, log_info, log_warning, log_error
)
from utils.dxf import load_document, save_document, cleanup_document
from processors.layer_processor import LayerProcessor
from processors.dxf_exporter import DXFExporter
from processors.legend_creator import LegendCreator
from processors.map_downloader import MapDownloader
from processors.block_manager import BlockManager
from processors.text_manager import TextManager

class Application:
    """Main application class coordinating all CAD/GIS operations."""
    
    def __init__(self, project_name: str):
        """Initialize the application.
        
        Args:
            project_name: Name of the project to process
        """
        self.project_name = project_name
        self.config = ConfigManager(project_name)
        self.doc: Optional[Drawing] = None
        
        # Initialize logging
        setup_logging(
            self.config.global_config.log_file,
            log_level='INFO'
        )
        
        # Initialize processors
        self.layer_processor = LayerProcessor(self.config)
        self.dxf_exporter = DXFExporter(self.config)
        self.legend_creator = LegendCreator(self.config)
        self.map_downloader = MapDownloader(self.config)
        self.block_manager = BlockManager(self.config)
        self.text_manager = TextManager(self.config)
        
        log_info(f"Initialized application for project: {project_name}")

    def run(self) -> None:
        """Run the complete processing workflow."""
        try:
            # Load or create DXF document
            self._initialize_document()
            
            # Download map layers if configured
            if self.config.project_config.wmts_layers or self.config.project_config.wms_layers:
                log_info("Processing map layers...")
                self.map_downloader.process_map_layers()
            
            # Process geometry layers
            if self.config.project_config.geom_layers:
                log_info("Processing geometry layers...")
                self.layer_processor.set_dxf_document(self.doc)
                self.layer_processor.process_layers()
            
            # Export processed layers to DXF
            if self.layer_processor.processed_layers:
                log_info("Exporting to DXF...")
                self.dxf_exporter.set_dxf_document(self.doc)
                self.dxf_exporter.export_to_dxf(
                    self.layer_processor.processed_layers
                )
            
            # Create legends if configured
            if self.config.project_config.legends:
                log_info("Creating legends...")
                self.legend_creator.set_dxf_document(self.doc)
                self.legend_creator.create_legends()
            
            # Process block insertions if configured
            if self.config.project_config.block_inserts:
                log_info("Processing block insertions...")
                self.block_manager.set_dxf_document(self.doc)
                self.block_manager.process_block_inserts()
            
            # Process text insertions if configured
            if self.config.project_config.text_inserts:
                log_info("Processing text insertions...")
                self.text_manager.set_dxf_document(self.doc)
                self.text_manager.process_text_inserts()
            
            # Save final document
            self._save_document()
            
            log_info("Processing completed successfully")
            
        except Exception as e:
            log_error(f"Error during processing: {str(e)}")
            raise
        finally:
            self._cleanup()

    def _initialize_document(self) -> None:
        """Initialize the DXF document."""
        try:
            # Try to load template if specified
            if self.config.project_config.template_dxf:
                template_path = self.config.project_config.template_dxf
                log_info(f"Loading template DXF: {template_path}")
                self.doc = load_document(template_path)
            
            # Try to load existing file
            elif Path(self.config.project_config.dxf_filename).exists():
                log_info(f"Loading existing DXF: {self.config.project_config.dxf_filename}")
                self.doc = load_document(self.config.project_config.dxf_filename)
            
            # Create new document
            else:
                log_info("Creating new DXF document")
                self.doc = ezdxf.new(self.config.project_config.dxf_version)
            
        except Exception as e:
            log_error(f"Error initializing DXF document: {str(e)}")
            raise

    def _save_document(self) -> None:
        """Save the DXF document."""
        if not self.doc:
            return
            
        try:
            # Create output directory if needed
            output_path = Path(self.config.project_config.dxf_filename)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save document
            save_document(
                self.doc,
                output_path,
                encoding='utf-8'
            )
            log_info(f"Saved DXF document to {output_path}")
            
        except Exception as e:
            log_error(f"Error saving DXF document: {str(e)}")
            raise

    def _cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Clean up processors
            for processor in [
                self.layer_processor,
                self.dxf_exporter,
                self.legend_creator,
                self.map_downloader,
                self.block_manager,
                self.text_manager
            ]:
                processor.cleanup()
            
            # Clean up document
            if self.doc:
                cleanup_document(self.doc)
            
            log_debug("Cleanup completed")
            
        except Exception as e:
            log_warning(f"Error during cleanup: {str(e)}") 