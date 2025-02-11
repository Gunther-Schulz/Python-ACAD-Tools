from typing import Dict, Any, Optional
from pathlib import Path
import ezdxf
from ezdxf.document import Drawing

from src.core.config import ConfigManager
from src.core.processor import BaseProcessor
from src.utils.logging import (
    setup_logging, log_debug, log_info, log_warning, log_error
)
from src.utils.dxf import load_document, save_document, cleanup_document
from src.processors.layer_processor import LayerProcessor
from src.processors.dxf_exporter import DXFExporter
from src.processors.legend_creator import LegendCreator
from src.processors.map_downloader import MapDownloader
from src.processors.block_manager import BlockManager
from src.processors.text_manager import TextManager

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
            
            # Share document with all processors
            self._share_document()
            
            # Download map layers if configured
            if self.config.project_config.wmts_layers or self.config.project_config.wms_layers:
                log_info("Processing map layers...")
                self.map_downloader.process_map_layers()
            
            # Process geometry layers
            if self.config.project_config.geom_layers:
                log_info("Processing geometry layers...")
                self.layer_processor.process_layers()
            
            # Export processed layers to DXF
            if self.layer_processor.processed_layers:
                log_info("Exporting to DXF...")
                self.dxf_exporter.export_to_dxf(
                    self.layer_processor.processed_layers
                )
            
            # Create legends if configured
            if self.config.project_config.legends:
                log_info("Creating legends...")
                self.legend_creator.create_legends()
            
            # Process block insertions if configured
            if self.config.project_config.block_inserts:
                log_info("Processing block insertions...")
                self.block_manager.process_block_inserts()
            
            # Process text insertions if configured
            if self.config.project_config.text_inserts:
                log_info("Processing text insertions...")
                self.text_manager.process_text_inserts()
            
            # Save final document
            self._save_document()
            
            log_info("Processing completed successfully")
            
        except Exception as e:
            log_error(f"Error during processing: {str(e)}")
            raise

    def _share_document(self) -> None:
        """Share the document with all processors."""
        if not self.doc:
            return
            
        processors = [
            self.layer_processor,
            self.dxf_exporter,
            self.legend_creator,
            self.map_downloader,
            self.block_manager,
            self.text_manager
        ]
        
        for processor in processors:
            processor.set_dxf_document(self.doc)
            log_debug(f"Shared document with {processor.__class__.__name__}")

    def _initialize_document(self) -> None:
        """Initialize the DXF document."""
        try:
            dxf_path = Path(self.config.project_config.dxf_filename)
            
            # Create backup of existing file if it exists
            if dxf_path.exists():
                backup_path = dxf_path.with_suffix('.dxf.bak')
                try:
                    from shutil import copy2
                    copy2(dxf_path, backup_path)
                    log_debug(f"Created backup of existing DXF file: {backup_path}")
                except Exception as e:
                    log_warning(f"Failed to create backup: {str(e)}")

            # Try to load existing file first
            if dxf_path.exists():
                log_info(f"Loading existing DXF: {dxf_path}")
                self.doc = load_document(dxf_path)
                log_debug("Successfully loaded existing DXF file")
            
            # Try to load template if specified and no existing file
            elif self.config.project_config.template_dxf:
                template_path = Path(self.config.project_config.template_dxf)
                if template_path.exists():
                    log_info(f"Loading template DXF: {template_path}")
                    self.doc = load_document(template_path)
                    log_debug("Successfully loaded template DXF file")
                else:
                    log_warning(f"Template file not found: {template_path}")
                    log_info("Creating new DXF document")
                    self.doc = ezdxf.new(self.config.project_config.dxf_version)
            
            # Create new document as last resort
            else:
                log_info("Creating new DXF document")
                self.doc = ezdxf.new(self.config.project_config.dxf_version)
            
            # Validate the document
            if self.doc:
                auditor = self.doc.audit()
                if len(auditor.errors) > 0:
                    log_warning(f"DXF document has {len(auditor.errors)} validation errors")
                    for error in auditor.errors:
                        log_warning(f"  - {error}")
            
        except Exception as e:
            log_error(f"Error initializing DXF document: {str(e)}")
            raise

    def _save_document(self) -> None:
        """Save the DXF document."""
        if not self.doc:
            log_warning("No document to save")
            return
            
        try:
            # Phase 1: Processor cleanup
            log_debug("Starting processor cleanup...")
            cleanup_errors = []
            for processor in [
                self.layer_processor,
                self.dxf_exporter,
                self.legend_creator,
                self.map_downloader,
                self.block_manager,
                self.text_manager
            ]:
                try:
                    processor.cleanup()
                    log_debug(f"Cleaned up {processor.__class__.__name__}")
                except Exception as e:
                    error_msg = f"Error cleaning up {processor.__class__.__name__}: {str(e)}"
                    cleanup_errors.append(error_msg)
                    log_warning(error_msg)
            
            if cleanup_errors:
                log_warning("Some cleanup operations failed but continuing with save")
            
            # Phase 2: Prepare output directory
            output_path = Path(self.config.project_config.dxf_filename)
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                log_debug(f"Ensured output directory exists: {output_path.parent}")
            except Exception as e:
                log_error(f"Failed to create output directory: {str(e)}")
                raise
            
            # Phase 3: Save document
            log_info(f"Saving DXF document to: {output_path}")
            try:
                save_document(
                    self.doc,
                    output_path,
                    encoding='utf-8'
                )
                log_info("Document saved successfully")
            except Exception as e:
                log_error(f"Failed to save document: {str(e)}")
                raise
            
        except Exception as e:
            log_error(f"Error during save process: {str(e)}")
            raise 