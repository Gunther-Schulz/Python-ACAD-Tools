"""Interface for geometry processing services."""
from typing import Protocol, List, Optional, Any, Dict
import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from ezdxf.document import Drawing

from ..domain.config_models import AllOperationParams, GeomLayerDefinition, StyleConfig
from ..domain.exceptions import GeometryError
from ..domain.style_models import NamedStyle
# from ..domain.geometry_models import LayerCollection # If we define a wrapper for dict of GeoDataFrames


class IGeometryProcessor(Protocol):
    """Interface for services that perform geometric operations on layers."""

    def apply_operation(
        self,
        operation_params: AllOperationParams,
        source_layers: Dict[str, gpd.GeoDataFrame],
        # base_crs: Optional[str] = None, # Could be part of a LayerCollection state
        # style_config: Optional[StyleConfig] = None # If operations need style awareness
    ) -> gpd.GeoDataFrame:
        """
        Applies a geometric operation based on the provided parameters.

        Args:
            operation_params: The specific parameters for the operation (e.g., BufferOpParams).
            source_layers: A dictionary of source GeoDataFrames, keyed by layer name.
                           The operation definition will specify which layers are used.

        Returns:
            A GeoDataFrame containing the result of the operation.

        Raises:
            GeometryError: If the operation fails or parameters are invalid.
            NotImplementedError: If the operation type is not supported.
        """
        ...

    def create_layer_from_definition(
        self,
        layer_def: GeomLayerDefinition,
        dxf_drawing: Optional[Any], # ezdxf.document.Drawing, but kept Any for interface flexibility
        style_config: StyleConfig,
        base_crs: str
    ) -> Optional[gpd.GeoDataFrame]:
        """
        Creates a GeoDataFrame for a layer based on its definition.
        This might involve loading from a shapefile, extracting from DXF, etc.

        Args:
            layer_def: The GeomLayerDefinition for the layer.
            dxf_drawing: The ezdxf Drawing object, if DXF extraction is needed.
            style_config: The global style configuration.
            base_crs: The base CRS for the project.

        Returns:
            A GeoDataFrame for the layer, or None if the layer cannot be created (e.g., source not found).

        Raises:
            GeometryError: For issues during geometry processing or DXF extraction.
        """
        ...

    def merge_layers(
        self,
        layers_to_merge: List[gpd.GeoDataFrame],
        target_crs: Optional[str] = None
    ) -> gpd.GeoDataFrame:
        """
        Merges multiple GeoDataFrames into a single GeoDataFrame.
        Handles CRS alignment if necessary.

        Args:
            layers_to_merge: A list of GeoDataFrames to merge.
            target_crs: The target CRS for the merged layer. If None, uses the CRS of the first layer.

        Returns:
            A single merged GeoDataFrame.

        Raises:
            GeometryError: If merging fails (e.g., incompatible schemas without explicit handling).
        """
        ...

    def reproject_layer(self, layer: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        """
        Reprojects a GeoDataFrame to the target CRS.

        Args:
            layer: The GeoDataFrame to reproject.
            target_crs: The target Coordinate Reference System.

        Returns:
            The reprojected GeoDataFrame.

        Raises:
            GeometryError: If reprojection fails.
        """
        ...

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
        """
        Adds geometries from a GeoDataFrame to a DXF drawing, applying specified styles
        and handling label placement.

        Args:
            dxf_drawing: The ezdxf Drawing object to add geometries to.
            gdf: The GeoDataFrame containing the geometries and their attributes.
            layer_name: The name of the DXF layer to add the geometries to.
            style: Optional NamedStyle object containing styling information.
            layer_definition: Optional GeomLayerDefinition providing context like label columns.
        """
        ...

    # Add other common geometry processing methods as identified
    # E.g., simplify_geometries, validate_geometries, extract_by_attribute, etc.
