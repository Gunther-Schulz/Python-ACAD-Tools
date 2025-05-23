"""Interface for resource management services."""
from typing import Protocol, Dict, Any, Generator, Optional
from contextlib import contextmanager
import geopandas as gpd

from ..domain.exceptions import ApplicationBaseException


class IResourceManager(Protocol):
    """Interface for services that manage application resources and memory."""

    def register_geodataframe(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Register a GeoDataFrame for memory tracking.

        Args:
            gdf: The GeoDataFrame to register for tracking.

        Returns:
            The same GeoDataFrame for chaining.
        """
        ...

    def create_temporary_file(self, suffix: str = ".tmp", prefix: str = "python_acad_") -> str:
        """
        Create a temporary file and register it for cleanup.

        Args:
            suffix: File suffix for the temporary file.
            prefix: File prefix for the temporary file.

        Returns:
            Path to the created temporary file.

        Raises:
            ApplicationBaseException: If temporary file creation fails.
        """
        ...

    @contextmanager
    def temporary_file_context(self, suffix: str = ".tmp", prefix: str = "python_acad_") -> Generator[str, None, None]:
        """
        Context manager for temporary files with automatic cleanup.

        Args:
            suffix: File suffix for the temporary file.
            prefix: File prefix for the temporary file.

        Yields:
            Path to the temporary file.

        Raises:
            ApplicationBaseException: If temporary file operations fail.
        """
        ...

    @contextmanager
    def memory_managed_operation(self, operation_name: str) -> Generator[None, None, None]:
        """
        Context manager for memory-managed operations.

        Args:
            operation_name: Name of the operation for logging purposes.

        Yields:
            None - provides context for the operation.

        Raises:
            ApplicationBaseException: If memory management fails.
        """
        ...

    def copy_geodataframe_safely(self, gdf: gpd.GeoDataFrame, operation_context: str = "unknown") -> gpd.GeoDataFrame:
        """
        Create a safe copy of GeoDataFrame with memory tracking.

        Args:
            gdf: The GeoDataFrame to copy.
            operation_context: Context description for logging.

        Returns:
            A safe copy of the GeoDataFrame.

        Raises:
            ApplicationBaseException: If copying fails.
        """
        ...

    def optimize_geodataframe_memory(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Optimize GeoDataFrame memory usage.

        Args:
            gdf: The GeoDataFrame to optimize.

        Returns:
            The optimized GeoDataFrame.
        """
        ...

    def cleanup_temporary_files(self) -> None:
        """Clean up all temporary files."""
        ...

    def get_memory_statistics(self) -> Dict[str, Any]:
        """
        Get current memory usage statistics.

        Returns:
            Dictionary with memory statistics.
        """
        ...

    def cleanup_all_resources(self) -> None:
        """Clean up all managed resources."""
        ...
