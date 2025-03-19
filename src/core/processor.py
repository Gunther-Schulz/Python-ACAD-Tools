"""
Main processing pipeline for OLADPP.
"""
from typing import Optional
from src.core.exceptions import ProcessingError
from src.core.project import Project
from src.processing import LayerProcessor
from src.style import StyleManager
from src.export.dxf import DXFExporter


class Processor:
    """Main processing pipeline orchestrator."""

    def __init__(self, project: Project):
        """
        Initialize the processor.

        Args:
            project: Project instance to process
        """
        self.project = project

        # Initialize style manager first
        self.style_manager = StyleManager(project)

        # Initialize layer processor with style manager
        self.layer_processor = LayerProcessor(project)
        self.layer_processor.set_style_manager(self.style_manager)

        # Initialize DXF exporter with all components
        self.dxf_exporter = DXFExporter(
            project=project,
            layer_processor=self.layer_processor,
            style_manager=self.style_manager
        )

    def process(self) -> None:
        """Process the project."""
        try:
            # Load or create DXF document
            doc = self.dxf_exporter._load_or_create_dxf(
                skip_dxf_processor=False
            )

            # Set document in layer processor
            self.layer_processor.set_dxf_document(doc)

            # Process layers
            self.layer_processor.process_layers()

            # Export to DXF
            self.dxf_exporter.export_to_dxf(skip_dxf_processor=True)

        except Exception as e:
            raise ProcessingError(f"Error processing project: {str(e)}")

    def get_document(self) -> Optional[object]:
        """
        Get the current document.

        Returns:
            The current document or None if not set
        """
        return self.layer_processor.get_dxf_document()

    def set_document(self, doc: object) -> None:
        """
        Set the current document.

        Args:
            doc: Document to set
        """
        self.layer_processor.set_dxf_document(doc)
