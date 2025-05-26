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
        self._logger = logger_service.get_logger(__name__)

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

    def get_validated_source_gdf(
        self,
        layer_identifier: Union[str, Dict[str, Any]],
        source_layers: Dict[str, gpd.GeoDataFrame],
        allow_empty: bool = True,
        expected_geom_types: Optional[List[str]] = None,
        context_message: str = ""
    ) -> gpd.GeoDataFrame:
        """Validates and retrieves a source layer from the available layers."""
        layer_name = layer_identifier if isinstance(layer_identifier, str) else layer_identifier.get('name', str(layer_identifier))

        if layer_name not in source_layers:
            msg = f"Layer '{layer_name}' not found in source layers. Available layers: {list(source_layers.keys())}. {context_message}"
            self._logger.error(msg)
            raise GdfValidationError(msg)

        gdf = source_layers[layer_name]

        # Check if GeoDataFrame is valid but empty - this is often legitimate
        if gdf.empty:
            if allow_empty:
                self._logger.debug(f"Layer '{layer_name}' is empty but empty layers are allowed. {context_message}")
                return gdf
            else:
                msg = f"Layer '{layer_name}' is empty but empty layers are not allowed. {context_message}"
                self._logger.error(msg)
                raise GdfValidationError(msg)

        # Only validate non-empty GeoDataFrames for basic structure
        if not self.validate_geodataframe_basic(gdf):
            msg = f"Layer '{layer_name}' failed basic GeoDataFrame validation. {context_message}"
            self._logger.error(msg)
            raise GdfValidationError(msg)

        if expected_geom_types:
            actual_geom_types = set(gdf.geometry.geom_type.unique())
            if not actual_geom_types.intersection(expected_geom_types):
                msg = f"Layer '{layer_name}' has geometry types {actual_geom_types} but expected {expected_geom_types}. {context_message}"
                self._logger.error(msg)
                raise GdfValidationError(msg)

        return gdf

    def get_common_crs(
        self,
        gdfs: List[gpd.GeoDataFrame],
        logger: Any  # Accept logger directly instead of logging service
    ) -> Optional[Union[str, Any]]:
        """Determines a common CRS for multiple GeoDataFrames."""
        if not gdfs:
            return None

        # Collect all unique CRS values
        crs_list = [gdf.crs for gdf in gdfs if gdf.crs is not None]

        if not crs_list:
            logger.warning("No GeoDataFrames have a defined CRS")
            return None

        # Check if all CRS are the same
        unique_crs = set(str(crs) for crs in crs_list)
        if len(unique_crs) == 1:
            return crs_list[0]

        # If multiple CRS, use the first one as target and log warning
        target_crs = crs_list[0]
        logger.warning(f"Multiple CRS found: {unique_crs}. Using first CRS as target: {target_crs}")
        return target_crs

    def ensure_multi_geometry(
        self,
        gdf: gpd.GeoDataFrame,
        geometry_type: str = 'auto'
    ) -> gpd.GeoDataFrame:
        """Ensures all geometries in the GeoDataFrame are Multi-type geometries."""
        from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon

        if gdf.empty:
            return gdf.copy()

        result_gdf = gdf.copy()

        for idx, geom in result_gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            geom_type = geom.geom_type

            if geom_type == 'Point':
                result_gdf.at[idx, 'geometry'] = MultiPoint([geom])
            elif geom_type == 'LineString':
                result_gdf.at[idx, 'geometry'] = MultiLineString([geom])
            elif geom_type == 'Polygon':
                result_gdf.at[idx, 'geometry'] = MultiPolygon([geom])
            # Multi geometries are already Multi, so no change needed

        return result_gdf

    def make_valid_geometries(
        self,
        gdf: gpd.GeoDataFrame,
        context_message: str = ""
    ) -> gpd.GeoDataFrame:
        """Makes all geometries in the GeoDataFrame valid using shapely make_valid."""
        from shapely.validation import make_valid

        if gdf.empty:
            self._logger.debug(f"Skipping make_valid for empty GeoDataFrame. {context_message}")
            return gdf.copy()

        result_gdf = gdf.copy()
        invalid_count = 0
        fixed_count = 0

        for idx, geom in result_gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            if not geom.is_valid:
                invalid_count += 1
                try:
                    valid_geom = make_valid(geom)
                    result_gdf.at[idx, 'geometry'] = valid_geom
                    fixed_count += 1
                except Exception as e:
                    self._logger.warning(f"Failed to make geometry valid at index {idx}: {e}. {context_message}")

        if invalid_count > 0:
            self._logger.info(f"Made {fixed_count}/{invalid_count} invalid geometries valid. {context_message}")

        return result_gdf

    def filter_gdf_by_attribute_values(
        self,
        gdf: gpd.GeoDataFrame,
        attribute_name: str,
        values: List[Any],
        include: bool = True,
        context_message: str = ""
    ) -> gpd.GeoDataFrame:
        """Filters GeoDataFrame by attribute values."""
        if gdf.empty:
            self._logger.debug(f"Skipping attribute filter for empty GeoDataFrame. {context_message}")
            return gdf.copy()

        if attribute_name not in gdf.columns:
            msg = f"Attribute '{attribute_name}' not found in GeoDataFrame columns. {context_message}"
            self._logger.error(msg)
            raise GdfValidationError(msg)

        if include:
            result_gdf = gdf[gdf[attribute_name].isin(values)].copy()
        else:
            result_gdf = gdf[~gdf[attribute_name].isin(values)].copy()

        self._logger.debug(f"Filtered GeoDataFrame from {len(gdf)} to {len(result_gdf)} features by attribute '{attribute_name}'. {context_message}")
        return result_gdf

    def filter_gdf_by_intersection(
        self,
        gdf: gpd.GeoDataFrame,
        filter_geometry: BaseGeometry,
        predicate: str = 'intersects',
        context_message: str = ""
    ) -> gpd.GeoDataFrame:
        """Filters GeoDataFrame by spatial intersection with a geometry."""
        if gdf.empty:
            self._logger.debug(f"Skipping intersection filter for empty GeoDataFrame. {context_message}")
            return gdf.copy()

        valid_predicates = ['intersects', 'within', 'contains', 'touches', 'crosses', 'overlaps']
        if predicate not in valid_predicates:
            msg = f"Invalid predicate '{predicate}'. Must be one of {valid_predicates}. {context_message}"
            self._logger.error(msg)
            raise GdfValidationError(msg)

        try:
            # Use GeoPandas spatial index for efficiency
            spatial_index = gdf.sindex
            if spatial_index is not None:
                possible_matches_index = list(spatial_index.intersection(filter_geometry.bounds))
                possible_matches = gdf.iloc[possible_matches_index]
            else:
                possible_matches = gdf

            # Apply the spatial predicate
            if predicate == 'intersects':
                mask = possible_matches.geometry.intersects(filter_geometry)
            elif predicate == 'within':
                mask = possible_matches.geometry.within(filter_geometry)
            elif predicate == 'contains':
                mask = possible_matches.geometry.contains(filter_geometry)
            elif predicate == 'touches':
                mask = possible_matches.geometry.touches(filter_geometry)
            elif predicate == 'crosses':
                mask = possible_matches.geometry.crosses(filter_geometry)
            elif predicate == 'overlaps':
                mask = possible_matches.geometry.overlaps(filter_geometry)

            result_gdf = possible_matches[mask].copy()

            self._logger.debug(f"Filtered GeoDataFrame from {len(gdf)} to {len(result_gdf)} features by {predicate} with geometry. {context_message}")
            return result_gdf

        except Exception as e:
            msg = f"Error during spatial filtering with predicate '{predicate}': {e}. {context_message}"
            self._logger.error(msg, exc_info=True)
            raise GeometryError(msg) from e
