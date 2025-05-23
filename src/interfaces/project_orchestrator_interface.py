"""Interface for the core project processing orchestration service."""
from typing import Protocol

class IProjectOrchestrator(Protocol):
    """Defines the contract for a service that orchestrates the entire project processing workflow."""

    def process_project(self, project_name: str) -> None:
        """
        Processes a given project based on its name.
        This involves loading configurations, data sources, applying operations, styling, and exporting.

        Args:
            project_name: The name of the project to process.

        Raises:
            ConfigError: If project configuration cannot be loaded.
            ProcessingError: For general errors during processing.
            DXFProcessingError: For errors specific to DXF loading or manipulation if critical.
            GeometryError: For errors during geometric operations.
            # Other specific exceptions from underlying services might also propagate.
        """
        ...
