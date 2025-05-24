"""GeoDataFrame operations service for GDF validation, manipulation, and CRS handling."""
from typing import Optional, List, Dict, Any, Union
import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon
from shapely.ops import unary_union
import pandas as pd

from ...domain.exceptions import GeometryError, GdfValidationError
from ...interfaces.logging_service_interface import ILoggingService

GEOMETRY_COLUMN = 'geometry'


class GdfOperationService:
    """Service for GeoDataFrame operations, validation, and transformations."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize the GDF operation service with dependency injection."""
        self._logger = logger_service

    def validate_geodataframe_basic(self, gdf: gpd.GeoDataFrame) -> bool:
        """Validates a GeoDataFrame for basic integrity."""
        if not isinstance(gdf, gpd.GeoDataFrame):
            self._logger.error("Input is not a GeoDataFrame")
            return False

        if gdf.empty:
            self._logger.warning("GeoDataFrame is empty")
            return False

        if GEOMETRY_COLUMN not in gdf.columns:
            self._logger.error(f"GeoDataFrame is missing the geometry column: '{GEOMETRY_COLUMN}'")
            return False

        if not gdf.geometry.name == GEOMETRY_COLUMN:
            self._logger.error(f"The active geometry column is '{gdf.geometry.name}', not '{GEOMETRY_COLUMN}'")
            return False

        return True

    def reproject_gdf(
        self,
        gdf: gpd.GeoDataFrame,
        target_crs: Union[str, Any],
        source_crs: Optional[Union[str, Any]] = None,
        context_message: str = "",
    ) -> gpd.GeoDataFrame:
        """Reprojects a GeoDataFrame to the target CRS."""
        if gdf.empty:
            self._logger.debug(f"Skipping reprojection for empty GeoDataFrame. {context_message}")
            if gdf.crs is None and target_crs:
                return gpd.GeoDataFrame(geometry=[], crs=target_crs)
            return gdf.copy()

        current_crs = gdf.crs
        if current_crs is None:
            if source_crs is None:
                msg = f"Cannot reproject GeoDataFrame: its CRS is not set and no source_crs provided. {context_message}"
                self._logger.error(msg)
                raise GdfValidationError(msg)
            current_crs = source_crs
            self._logger.debug(f"GeoDataFrame CRS not set, using provided source_crs: {source_crs}. {context_message}")
            try:
                temp_gdf = gdf.copy()
                temp_gdf.crs = current_crs
            except Exception as e:
                msg = f"Failed to assign source_crs ('{source_crs}') to GeoDataFrame: {e}. {context_message}"
                self._logger.error(msg, exc_info=True)
                raise GdfValidationError(msg) from e
        else:
            temp_gdf = gdf

        if temp_gdf.crs == target_crs:
            self._logger.debug(f"GeoDataFrame is already in target CRS ({target_crs}). No reprojection needed. {context_message}")
            return gdf.copy()

        try:
            self._logger.info(f"Reprojecting GeoDataFrame from {temp_gdf.crs} to {target_crs}. {context_message}")
            reprojected_gdf = temp_gdf.to_crs(target_crs)
            return reprojected_gdf
        except Exception as e:
            msg = f"Error during GeoDataFrame reprojection from {temp_gdf.crs} to {target_crs}: {e}. {context_message}"
            self._logger.error(msg, exc_info=True)
            raise GeometryError(msg) from e
