"""Utility functions for GeoDataFrame validation, manipulation, and CRS handling."""
from typing import Optional, List, Dict, Any, Union, Tuple, Sequence

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon, GeometryCollection, base
from shapely.validation import make_valid
from shapely.ops import transform, unary_union # Added unary_union
import pandas as pd

from ..domain.exceptions import GeometryError, ConfigError # Assuming these are appropriate
from ..interfaces.logging_service_interface import ILoggingService # For type hinting logger
from ..services.logging_service import LoggingService # Fallback logger


# Module-level logger (can be injected or use fallback)
_logger_instance: Optional[ILoggingService] = None

def _get_logger():
    """Gets a logger instance for this module."""
    global _logger_instance
    if _logger_instance is None:
        try:
            # This is a simple fallback. In a full app, logger might be configured globally.
            _logger_instance = LoggingService() # type: ignore
        except Exception: # Fallback if LoggingService itself fails
            import logging
            return logging.getLogger(__name__) # Basic Python logger
    return _logger_instance.get_logger(__name__)


GEOMETRY_COLUMN = 'geometry' # Standard GeoPandas geometry column name

class GdfValidationError(ConfigError): # More specific error for GDF validation issues
    """Custom exception for GdfValidationError failures."""
    pass


def get_validated_source_gdf(
    layer_identifier: Union[str, Dict[str, Any]],
    source_layers: Dict[str, gpd.GeoDataFrame],
    expected_geom_types: Optional[Union[str, List[str]]] = None,
    check_crs_match_with: Optional[gpd.GeoDataFrame] = None,
    allow_empty: bool = False,
    ensure_geometry_column: bool = True,
    context_message: str = ""
) -> gpd.GeoDataFrame:
    """
    Retrieves and validates a GeoDataFrame from the source_layers dictionary.

    Args:
        layer_identifier: Name of the layer (str) or a dictionary specifying the layer
                            (e.g., {'name': 'layer_name', 'alias': 'optional_alias'}).
        source_layers: Dictionary of available GeoDataFrames.
        expected_geom_types: Optional string or list of strings of expected geometry types
                                (e.g., 'Polygon', ['LineString', 'MultiLineString']).
        check_crs_match_with: Optional GeoDataFrame whose CRS should be matched.
        allow_empty: If False (default), raises GdfValidationError if the GDF is empty.
        ensure_geometry_column: If True (default), checks for the presence of a geometry column.
        context_message: Additional context for error messages.

    Returns:
        The validated GeoDataFrame.

    Raises:
        GdfValidationError: If validation fails (layer not found, empty, wrong geom type, CRS mismatch).
    """
    logger = _get_logger()
    layer_name: Optional[str] = None

    if isinstance(layer_identifier, str):
        layer_name = layer_identifier
    elif isinstance(layer_identifier, dict):
        layer_name = layer_identifier.get('name')
        if not layer_name:
            msg = f"Invalid layer identifier dictionary (missing 'name'): {layer_identifier}. {context_message}"
            logger.error(msg)
            raise GdfValidationError(msg)
    else:
        msg = f"Invalid layer_identifier type: {type(layer_identifier)}. Must be str or dict. {context_message}"
        logger.error(msg)
        raise GdfValidationError(msg)

    if layer_name not in source_layers:
        msg = f"Source layer '{layer_name}' not found in available layers: {list(source_layers.keys())}. {context_message}"
        logger.error(msg)
        raise GdfValidationError(msg)

    gdf = source_layers[layer_name]

    if not isinstance(gdf, gpd.GeoDataFrame):
        msg = f"Source layer '{layer_name}' is not a GeoDataFrame (type: {type(gdf)}). {context_message}"
        logger.error(msg)
        raise GdfValidationError(msg)

    if ensure_geometry_column:
        if GEOMETRY_COLUMN not in gdf.columns:
            msg = f"Source layer '{layer_name}' is missing the geometry column ('{GEOMETRY_COLUMN}'). {context_message}"
            logger.error(msg)
            raise GdfValidationError(msg)
        if not gdf.geometry.name == GEOMETRY_COLUMN: # Check if the active geometry column is correct
                msg = f"The active geometry column for layer '{layer_name}' is '{gdf.geometry.name}', not '{GEOMETRY_COLUMN}'. {context_message}"
                logger.error(msg)
                raise GdfValidationError(msg)


    if not allow_empty and gdf.empty:
        msg = f"Source layer '{layer_name}' is empty and allow_empty is False. {context_message}"
        logger.warning(msg) # Warning as it might be acceptable in some cases upstream
        raise GdfValidationError(msg)

    if expected_geom_types and not gdf.empty:
        if isinstance(expected_geom_types, str):
            expected_types_list = [expected_geom_types.lower()]
        else:
            expected_types_list = [gt.lower() for gt in expected_geom_types]

        # Check actual geometry types present in the GeoDataFrame
        # gdf.geom_type can be mixed. We need to check if *any* are valid if mixed, or if all are.
        # For simplicity, this check assumes homogeneity or that all geometries should broadly match.
        # A more robust check might iterate unique(gdf.geom_type)
        actual_types = gdf.geom_type.dropna().unique()
        if not any(actual_type.lower() in expected_types_list for actual_type in actual_types):
            msg = f"Source layer '{layer_name}' has unexpected geometry types {actual_types}. Expected one of {expected_types_list}. {context_message}"
            logger.error(msg)
            raise GdfValidationError(msg)

    if check_crs_match_with is not None:
        if gdf.crs != check_crs_match_with.crs:
            msg = (f"CRS mismatch for layer '{layer_name}' ({gdf.crs}) "
                    f"and reference layer ({check_crs_match_with.crs}). {context_message}")
            logger.error(msg)
            raise GdfValidationError(msg)

    logger.debug(f"Successfully validated and retrieved source layer: '{layer_name}'. {context_message}")
    return gdf.copy() # Return a copy to avoid unintended side effects


def reproject_gdf(
    gdf: gpd.GeoDataFrame,
    target_crs: Union[str, Any], # Accepts EPSG code, WKT string, pyproj.CRS object
    source_crs: Optional[Union[str, Any]] = None,
    context_message: str = ""
) -> gpd.GeoDataFrame:
    """
    Reprojects a GeoDataFrame to the target CRS.

    Args:
        gdf: The GeoDataFrame to reproject.
        target_crs: The target Coordinate Reference System.
        source_crs: Optional. The source CRS if gdf.crs is not set. If None and gdf.crs is None,
                    raises GdfValidationError.
        context_message: Additional context for error messages.

    Returns:
        The reprojected GeoDataFrame.

    Raises:
        GdfValidationError: If CRS information is insufficient or reprojection fails.
    """
    logger = _get_logger()
    if gdf.empty:
        logger.debug(f"Skipping reprojection for empty GeoDataFrame. {context_message}")
        # Ensure an empty GDF still has a CRS if target_crs is known
        if gdf.crs is None and target_crs:
            return gpd.GeoDataFrame(geometry=[], crs=target_crs)
        return gdf.copy()

    current_crs = gdf.crs
    if current_crs is None:
        if source_crs is None:
            msg = f"Cannot reproject GeoDataFrame: its CRS is not set and no source_crs provided. {context_message}"
            logger.error(msg)
            raise GdfValidationError(msg)
        current_crs = source_crs
        logger.debug(f"GeoDataFrame CRS not set, using provided source_crs: {source_crs}. {context_message}")
        # Create a temporary GDF with CRS set for reprojection if needed, or assign directly
        try:
            # Check if gdf.crs can be assigned directly
            temp_gdf = gdf.copy()
            temp_gdf.crs = current_crs
        except Exception as e:
            msg = f"Failed to assign source_crs ('{source_crs}') to GeoDataFrame: {e}. {context_message}"
            logger.error(msg, exc_info=True)
            raise GdfValidationError(msg) from e
    else:
        temp_gdf = gdf # Use the original GDF if CRS is already set

    if temp_gdf.crs == target_crs:
        logger.debug(f"GeoDataFrame is already in target CRS ({target_crs}). No reprojection needed. {context_message}")
        return gdf.copy() # Return a copy of the original

    try:
        logger.info(f"Reprojecting GeoDataFrame from {temp_gdf.crs} to {target_crs}. {context_message}")
        reprojected_gdf = temp_gdf.to_crs(target_crs)
        return reprojected_gdf
    except Exception as e:
        msg = f"Error during GeoDataFrame reprojection from {temp_gdf.crs} to {target_crs}: {e}. {context_message}"
        logger.error(msg, exc_info=True)
        raise GeometryError(msg) from e


def get_common_crs(
    gdfs: List[gpd.GeoDataFrame],
    fallback_crs: Optional[Union[str, Any]] = None,
    context_message: str = ""
) -> Any: # Returns a pyproj.CRS compatible type or None
    """
    Determines a common CRS from a list of GeoDataFrames.

    If all GDFs share the same CRS, that CRS is returned.
    If CRSs are mixed or None, and a fallback_crs is provided, it's returned.
    If CRSs are mixed or None, and no fallback_crs, raises GdfValidationError.

    Args:
        gdfs: A list of GeoDataFrames.
        fallback_crs: Optional. A CRS to return if no common CRS can be found.
        context_message: Additional context for error messages.

    Returns:
        The common CRS object, or the fallback_crs, or raises error.

    Raises:
        GdfValidationError: If no common CRS can be determined and no fallback is provided.
    """
    logger = _get_logger()
    if not gdfs:
        if fallback_crs:
            logger.debug(f"No GeoDataFrames provided, using fallback_crs: {fallback_crs}. {context_message}")
            return fallback_crs
        else:
            msg = f"Cannot determine common CRS: no GeoDataFrames provided and no fallback_crs. {context_message}"
            logger.error(msg)
            raise GdfValidationError(msg)

    unique_crs_set = {gdf.crs for gdf in gdfs if gdf.crs is not None and not gdf.empty}

    if len(unique_crs_set) == 1:
        common = unique_crs_set.pop()
        logger.debug(f"Determined common CRS: {common}. {context_message}")
        return common
    elif len(unique_crs_set) == 0: # All GDFs have no CRS or are empty
        if fallback_crs:
            logger.debug(f"All GeoDataFrames have no CRS or are empty, using fallback_crs: {fallback_crs}. {context_message}")
            return fallback_crs
        else:
            msg = f"Cannot determine common CRS: all GeoDataFrames have no CRS or are empty, and no fallback_crs provided. {context_message}"
            logger.warning(msg) # Warning as this might be intentional
            raise GdfValidationError(msg)
    else: # Mixed CRSs
        if fallback_crs:
            logger.warning(f"Mixed CRSs found ({unique_crs_set}), using fallback_crs: {fallback_crs}. {context_message}")
            return fallback_crs
        else:
            msg = f"Cannot determine common CRS: mixed CRSs found ({unique_crs_set}) and no fallback_crs provided. {context_message}"
            logger.error(msg)
            raise GdfValidationError(msg)


def ensure_multi_geometry(gdf: gpd.GeoDataFrame, context_message: str = "") -> gpd.GeoDataFrame:
    """
    Ensures all geometries in the GeoDataFrame are Multi-type (MultiPoint, MultiLineString, MultiPolygon).

    Args:
        gdf: The input GeoDataFrame.
        context_message: Additional context for log messages.

    Returns:
        A new GeoDataFrame with geometries converted to Multi-types if necessary.
    """
    logger = _get_logger()
    if gdf.empty:
        logger.debug(f"Skipping ensure_multi_geometry for empty GeoDataFrame. {context_message}")
        return gdf.copy()

    # Identify single-part geometry types that need conversion
    # This is a common pattern; more robust might be to check geom.type
    def to_multi(geometry: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
        if geometry is None or geometry.is_empty:
            return geometry
        if geometry.geom_type == 'Point':
            return MultiPoint([geometry])
        if geometry.geom_type == 'LineString':
            return MultiLineString([geometry])
        if geometry.geom_type == 'Polygon':
            return MultiPolygon([geometry])
        # Already a multi-geometry or an unhandled type
        return geometry

    try:
        # Apply the conversion. Creates a new Series.
        multi_geoms = gdf.geometry.apply(to_multi)

        # Create a new GeoDataFrame with the modified geometries
        # This ensures that we don't modify the original GDF in place if it was passed by reference
        result_gdf = gdf.copy()
        result_gdf.geometry = multi_geoms

        logger.debug(f"Applied ensure_multi_geometry. {context_message}")
        return result_gdf
    except Exception as e:
        msg = f"Error in ensure_multi_geometry: {e}. {context_message}"
        logger.error(msg, exc_info=True)
        raise GeometryError(msg) from e


def make_valid_geometries(
    gdf: gpd.GeoDataFrame,
    context_message: str = "",
    report_invalid: bool = True
) -> gpd.GeoDataFrame:
    """
    Attempts to make all geometries in the GeoDataFrame valid using geom.buffer(0).

    Args:
        gdf: The input GeoDataFrame.
        context_message: Additional context for log messages.
        report_invalid: If True, logs a warning if invalid geometries are found.

    Returns:
        A new GeoDataFrame with geometries processed by buffer(0).
    """
    logger = _get_logger()
    if gdf.empty:
        logger.debug(f"Skipping make_valid_geometries for empty GeoDataFrame. {context_message}")
        return gdf.copy()

    if report_invalid:
        # This can be slow on large GDFs. Consider sampling or optional execution.
        # invalid_geoms = gdf[~gdf.geometry.is_valid]
        # if not invalid_geoms.empty:
        #    logger.warning(f"{len(invalid_geoms)} invalid geometries found before make_valid. {context_message}")
        # Using a more efficient way to check if any are invalid
        are_all_valid_before = gdf.geometry.is_valid.all()
        if not are_all_valid_before:
                logger.warning(f"Invalid geometries detected before make_valid. {context_message}")


    try:
        # Applying buffer(0) is a common trick to fix invalid geometries
        # This creates a new Series of geometries.
        valid_geoms = gdf.geometry.buffer(0)

        result_gdf = gdf.copy()
        result_gdf.geometry = valid_geoms

        # Optionally, re-check validity
        # are_all_valid_after = result_gdf.geometry.is_valid.all()
        # if not are_all_valid_after:
        #     logger.warning(f"Some geometries may still be invalid after make_valid. {context_message}")
        # else:
        #     logger.debug(f"All geometries are valid after make_valid. {context_message}")

        logger.debug(f"Applied make_valid_geometries (buffer(0)). {context_message}")
        return result_gdf
    except Exception as e:
        msg = f"Error in make_valid_geometries: {e}. {context_message}"
        logger.error(msg, exc_info=True)
        raise GeometryError(msg) from e

def filter_gdf_by_attribute_values(
    gdf: gpd.GeoDataFrame,
    column_name: str,
    filter_values: List[Any],
    keep_matching: bool = True,
    case_sensitive: bool = False,
    context_message: str = ""
) -> gpd.GeoDataFrame:
    """
    Filters a GeoDataFrame based on attribute values in a specified column.

    Args:
        gdf: The input GeoDataFrame.
        column_name: The name of the column to filter on.
        filter_values: A list of values to match against.
        keep_matching: If True (default), rows matching the values are kept.
                       If False, rows matching the values are discarded.
        case_sensitive: If False (default), comparisons are case-insensitive for strings.
        context_message: Additional context for error messages.

    Returns:
        A new GeoDataFrame containing the filtered rows.

    Raises:
        GdfValidationError: If the specified column is not found.
    """
    logger = _get_logger()
    if gdf.empty:
        logger.debug(f"Skipping attribute filter for empty GeoDataFrame. {context_message}")
        return gdf.copy()

    if column_name not in gdf.columns:
        msg = f"Column '{column_name}' not found in GeoDataFrame for filtering. Columns: {gdf.columns.tolist()}. {context_message}"
        logger.error(msg)
        raise GdfValidationError(msg)

    # Prepare filter values: convert to string if not case sensitive or if column is object/string type
    # Ensure column data is also string for robust isin comparison if not case sensitive.
    gdf_column_series = gdf[column_name]

    # Determine if string conversion is appropriate for comparison
    # This is a heuristic. For numeric columns, direct comparison might be better if values are numbers.
    # However, the old logic always converted to string for `isin`.
    # We will replicate that for `isin` but allow more direct comparison for other operators if we add them.

    try:
        if not case_sensitive and pd.api.types.is_string_dtype(gdf_column_series):
            condition_series = gdf_column_series.astype(str).str.lower().isin([str(v).lower() for v in filter_values])
        elif pd.api.types.is_string_dtype(gdf_column_series) or gdf_column_series.dtype == 'object':
            # Handles mixed types in object columns by converting all to string for comparison
            condition_series = gdf_column_series.astype(str).isin([str(v) for v in filter_values])
        else: # For numeric or other specific types, try direct isin if filter_values are compatible
            try:
                # Attempt direct isin if types might match (e.g. column is int, values are ints)
                condition_series = gdf_column_series.isin(filter_values)
            except TypeError as te_direct_isin: # If direct isin fails due to type mismatch (e.g. list in series)
                logger.debug(f"Direct isin failed for column '{column_name}' (type {gdf_column_series.dtype}) with values (first: {type(filter_values[0]) if filter_values else None}). Falling back to string comparison. Error: {te_direct_isin}")
                condition_series = gdf_column_series.astype(str).isin([str(v) for v in filter_values])

    except Exception as e_prepare_filter:
        msg = f"Error preparing filter condition for column '{column_name}': {e_prepare_filter}. {context_message}"
        logger.error(msg, exc_info=True)
        raise GdfValidationError(msg) from e_prepare_filter

    if keep_matching:
        filtered_gdf = gdf[condition_series].copy()
    else:
        filtered_gdf = gdf[~condition_series].copy()

    logger.debug(f"Filtered GeoDataFrame by column '{column_name}'. Original rows: {len(gdf)}, Filtered rows: {len(filtered_gdf)}. {context_message}")
    return filtered_gdf


def filter_gdf_by_intersection(
    source_gdf: gpd.GeoDataFrame,
    filter_items: List[Dict[str, Any]], # List of dicts like FilterLayerItem.model_dump() but with actual GDFs
                                       # e.g. {'gdf': GeoDataFrame, 'attribute_filter_column': str, ... 'add_filter_layer_name_column': str}
    source_layer_name_for_log: str, # For logging context
    base_crs: str, # To ensure consistent CRS operations
    explode_source_before_filter: bool = True,
    filter_geometry_buffer_distance: float = 0.0,
    keep_matching: bool = True,
    context_message: str = "filter_gdf_by_intersection"
) -> gpd.GeoDataFrame:
    """
    Filters a source GeoDataFrame by spatial intersection with one or more filter GeoDataFrames.

    Args:
        source_gdf: The GeoDataFrame to be filtered.
        filter_items: A list of dictionaries, each representing a filter layer.
                      Each dictionary must contain:
                        - 'gdf': The filter GeoDataFrame.
                        - 'layer_name': Name of the filter layer (for logging/column naming).
                        - 'attribute_filter_column': Optional. Column in filter_gdf to filter by.
                        - 'attribute_filter_values': Optional. Values for attribute_filter_column.
                        - 'add_filter_layer_name_column': Optional. If set, a boolean column with this name
                                                          is added to the output, indicating if a source feature
                                                          intersected THIS specific filter_item's geometry.
        source_layer_name_for_log: Name of the source layer, for logging.
        base_crs: The CRS to use for all operations.
        explode_source_before_filter: If True, explode multipart geometries in source_gdf first.
        filter_geometry_buffer_distance: Distance to buffer the UNARY UNION of each filter_item's geometry.
                                          Applied after any attribute filtering on the filter_item.
        keep_matching: If True, keeps source features that intersect the combined filter geometry.
                       If False, keeps source features that do NOT intersect.
        context_message: Context for logging potential errors.

    Returns:
        A new GeoDataFrame containing the filtered geometries from source_gdf.
    """
    if source_gdf.empty:
        _logger_geoutils.info(f"{context_message}: Source GDF '{source_layer_name_for_log}' is empty. Returning empty GDF.")
        return source_gdf.copy()

    if not filter_items:
        _logger_geoutils.warning(f"{context_message}: No filter items provided for '{source_layer_name_for_log}'. Returning original GDF.")
        return source_gdf.copy()

    # Ensure source_gdf is in base_crs
    current_source_gdf = reproject_gdf(source_gdf, base_crs, f"{context_message} source_gdf reprojection")

    if explode_source_before_filter:
        if not current_source_gdf.empty and current_source_gdf.geom_type.str.startswith('Multi').any():
            _logger_geoutils.debug(f"{context_message}: Exploding source GDF '{source_layer_name_for_log}' before filtering.")
            current_source_gdf = current_source_gdf.explode(index_parts=True).reset_index(drop=True) # Changed from ignore_index to preserve original index parts if needed later
                                                                                                # Reset index to avoid issues with sjoin if index_parts=True creates multi-index

    all_filter_geometries: List[base.BaseGeometry] = []
    processed_filter_items_for_individual_sjoin: List[Tuple[str, gpd.GeoDataFrame]] = []


    for i, item_dict in enumerate(filter_items):
        filter_gdf = item_dict.get('gdf')
        filter_layer_name = item_dict.get('layer_name', f"filter_item_{i}")
        attr_filter_col = item_dict.get('attribute_filter_column')
        attr_filter_vals = item_dict.get('attribute_filter_values')
        add_col_name = item_dict.get('add_filter_layer_name_column')

        if not isinstance(filter_gdf, gpd.GeoDataFrame) or filter_gdf.empty:
            _logger_geoutils.warning(f"{context_message}: Filter item '{filter_layer_name}' is empty or not a GDF. Skipping.")
            continue

        # Reproject filter_gdf to base_crs
        current_filter_gdf = reproject_gdf(filter_gdf, base_crs, f"{context_message} filter_gdf '{filter_layer_name}' reprojection")

        # Apply attribute filtering to the filter_gdf itself if specified
        if attr_filter_col and attr_filter_vals:
            if attr_filter_col not in current_filter_gdf.columns:
                _logger_geoutils.error(f"{context_message}: Attribute filter column '{attr_filter_col}' not found in filter GDF '{filter_layer_name}'. Skipping this filter item.")
                continue
            try:
                _logger_geoutils.debug(f"{context_message}: Applying attribute filter to '{filter_layer_name}' on column '{attr_filter_col}'.")
                current_filter_gdf = filter_gdf_by_attribute_values(
                    current_filter_gdf,
                    column_name=attr_filter_col,
                    filter_values=attr_filter_vals,
                    keep_matching=True, # Always keep matching for the filter layer itself
                    context_message=f"{context_message} attribute pre-filter for '{filter_layer_name}'"
                )
                if current_filter_gdf.empty:
                    _logger_geoutils.info(f"{context_message}: Filter GDF '{filter_layer_name}' became empty after attribute filtering. Skipping.")
                    continue
            except Exception as e_attr_filter:
                _logger_geoutils.error(f"{context_message}: Error during attribute pre-filter for '{filter_layer_name}': {e_attr_filter}. Skipping.", exc_info=True)
                continue

        # Buffer the (potentially attribute-filtered) filter_gdf's unary_union
        # We use unary_union to avoid issues with self-intersections if buffering individual geometries then unioning
        if not current_filter_gdf.empty:
            filter_geom_unified = unary_union(current_filter_gdf.geometry)
            if filter_geometry_buffer_distance != 0.0:
                _logger_geoutils.debug(f"{context_message}: Buffering unified geometry of '{filter_layer_name}' by {filter_geometry_buffer_distance}.")
                filter_geom_unified = filter_geom_unified.buffer(filter_geometry_buffer_distance)

            if filter_geom_unified and not filter_geom_unified.is_empty:
                all_filter_geometries.append(filter_geom_unified)
                if add_col_name: # If a column needs to be added for this specific filter layer
                    # We need a GDF with this single (buffered, unified) geometry to sjoin for the specific column
                    temp_filter_gdf_for_sjoin = gpd.GeoDataFrame(geometry=[filter_geom_unified], crs=base_crs)
                    processed_filter_items_for_individual_sjoin.append((add_col_name, temp_filter_gdf_for_sjoin))


    if not all_filter_geometries:
        _logger_geoutils.warning(f"{context_message}: No valid filter geometries obtained for '{source_layer_name_for_log}'. Behavior depends on 'keep_matching'.")
        if keep_matching: # Keep intersecting with nothing -> empty
            return gpd.GeoDataFrame(geometry=[], crs=current_source_gdf.crs, columns=current_source_gdf.columns)
        else: # Keep non-intersecting with nothing -> all original
            # Add any requested 'add_filter_layer_name_column' as False
            result_gdf_no_filters = current_source_gdf.copy()
            for col_name_to_add, _ in processed_filter_items_for_individual_sjoin:
                 if col_name_to_add not in result_gdf_no_filters.columns:
                      result_gdf_no_filters[col_name_to_add] = False
            return result_gdf_no_filters


    # Combine all processed filter geometries into a single geometry for the main sjoin
    combined_filter_geometry = unary_union(all_filter_geometries)
    if combined_filter_geometry.is_empty:
        _logger_geoutils.warning(f"{context_message}: Combined filter geometry for '{source_layer_name_for_log}' is empty. Behavior depends on 'keep_matching'.")
        if keep_matching:
            return gpd.GeoDataFrame(geometry=[], crs=current_source_gdf.crs, columns=current_source_gdf.columns)
        else:
            result_gdf_no_filters = current_source_gdf.copy()
            for col_name_to_add, _ in processed_filter_items_for_individual_sjoin:
                 if col_name_to_add not in result_gdf_no_filters.columns:
                      result_gdf_no_filters[col_name_to_add] = False
            return result_gdf_no_filters

    # Create a GeoDataFrame for the combined filter geometry
    combined_filter_gdf = gpd.GeoDataFrame(geometry=[combined_filter_geometry], crs=base_crs)

    # Perform the main spatial join
    try:
        _logger_geoutils.debug(f"{context_message}: Performing sjoin for '{source_layer_name_for_log}'.")
        # Save original index to select rows from current_source_gdf later
        # We use 'left' join to keep all source_gdf rows initially, and 'intersects' gives 'index_right'
        # The presence of 'index_right' (not NaN) indicates an intersection.
        joined_gdf = gpd.sjoin(current_source_gdf, combined_filter_gdf, how='left', predicate='intersects')

        if keep_matching:
            # Keep rows where index_right is not NaN (i.e., they intersected)
            intersecting_rows_mask = joined_gdf['index_right'].notna()
            result_gdf = current_source_gdf[intersecting_rows_mask].copy()
        else:
            # Keep rows where index_right is NaN (i.e., they did NOT intersect)
            non_intersecting_rows_mask = joined_gdf['index_right'].isna()
            result_gdf = current_source_gdf[non_intersecting_rows_mask].copy()

        # Add individual intersection flag columns if requested
        for col_name_to_add, specific_filter_gdf in processed_filter_items_for_individual_sjoin:
            if col_name_to_add not in result_gdf.columns: # Initialize column
                 result_gdf[col_name_to_add] = False

            # Only sjoin if result_gdf is not empty, otherwise, the False initialization is enough
            if not result_gdf.empty:
                # Perform sjoin with this specific filter GDF on the already filtered result_gdf
                # to determine which of these features intersected THIS specific filter.
                temp_join_for_col = gpd.sjoin(result_gdf, specific_filter_gdf, how='left', predicate='intersects')
                intersect_mask_for_col = temp_join_for_col['index_right'].notna()
                # Ensure to assign back to the original indices of result_gdf
                result_gdf.loc[intersect_mask_for_col, col_name_to_add] = True


        _logger_geoutils.info(f"{context_message}: Successfully filtered '{source_layer_name_for_log}'. Original rows: {len(source_gdf)}, Result rows: {len(result_gdf)}.")
        return result_gdf.reset_index(drop=True) # Ensure clean index

    except Exception as e_sjoin:
        _logger_geoutils.error(f"{context_message}: Error during sjoin for '{source_layer_name_for_log}': {e_sjoin}", exc_info=True)
        raise GdfValidationError(f"Error during spatial join in {context_message} for '{source_layer_name_for_log}': {e_sjoin}") from e_sjoin


# Example of a more complex utility if needed, e.g., for attribute merging:
# def merge_attributes(target_gdf: gpd.GeoDataFrame, source_gdf: gpd.GeoDataFrame,
#                      left_on: Optional[Union[str, List[str]]] = None,
#                      right_on: Optional[Union[str, List[str]]] = None,
#                      how: str = 'inner', # 'left', 'right', 'outer', 'inner'
#                      suffixes: Tuple[str, str] = ('_left', '_right'),
#                      default_value_map: Optional[Dict[str, Any]] = None,
#                      context_message: str = "") -> gpd.GeoDataFrame:
#     logger = _get_logger()
#     # ... implementation ...
