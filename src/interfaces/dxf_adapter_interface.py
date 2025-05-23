"""Interface for DXF library adapters."""
from typing import Protocol, Optional, Any, Dict, List
import geopandas as gpd

from ..domain.exceptions import DXFProcessingError


class IDXFAdapter(Protocol):
    """Interface for adapters that handle DXF library operations."""

    def load_dxf_file(self, file_path: str) -> Optional[Any]:
        """
        Load a DXF file using the underlying DXF library.

        Args:
            file_path: Path to the DXF file to load.

        Returns:
            DXF document object or None if loading fails.

        Raises:
            DXFProcessingError: If DXF file cannot be loaded.
        """
        ...

    def extract_entities_from_layer(
        self,
        dxf_document: Any,
        layer_name: str,
        crs: str
    ) -> Optional[gpd.GeoDataFrame]:
        """
        Extract entities from a specific DXF layer.

        Args:
            dxf_document: The DXF document object.
            layer_name: Name of the layer to extract from.
            crs: Coordinate reference system for the output.

        Returns:
            GeoDataFrame with extracted entities or None if layer not found.

        Raises:
            DXFProcessingError: If entity extraction fails.
        """
        ...

    def save_dxf_file(self, dxf_document: Any, file_path: str) -> None:
        """
        Save a DXF document to file.

        Args:
            dxf_document: The DXF document object to save.
            file_path: Path where to save the DXF file.

        Raises:
            DXFProcessingError: If DXF file cannot be saved.
        """
        ...

    def create_dxf_layer(self, dxf_document: Any, layer_name: str, **properties) -> None:
        """
        Create or update a DXF layer with specified properties.

        Args:
            dxf_document: The DXF document object.
            layer_name: Name of the layer to create/update.
            **properties: Layer properties (color, linetype, etc.).

        Raises:
            DXFProcessingError: If layer creation fails.
        """
        ...

    def add_geodataframe_to_dxf(
        self,
        dxf_document: Any,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        **style_properties
    ) -> None:
        """
        Add geometries from GeoDataFrame to DXF document.

        Args:
            dxf_document: The DXF document object.
            gdf: GeoDataFrame containing geometries to add.
            layer_name: Name of the target DXF layer.
            **style_properties: Style properties to apply.

        Raises:
            DXFProcessingError: If geometry addition fails.
        """
        ...

    def is_available(self) -> bool:
        """
        Check if the DXF library is available.

        Returns:
            True if DXF library is available, False otherwise.
        """
        ...
