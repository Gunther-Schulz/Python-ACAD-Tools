"""Concrete implementation of the IGeometryProcessor interface."""
import os
from typing import List, Optional, Any, Dict, Tuple, Callable, cast, Union

import geopandas as gpd
import pandas as pd # New
from shapely.geometry import LineString, Polygon, Point, MultiPolygon, box # Added box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.validation import make_valid # New
from shapely import affinity # New import for shapely.affinity.rotate
import numpy as np # Added numpy
from scipy.spatial.distance import cdist # Added cdist

# Import proper CRS type
try:
    from pyproj import CRS
    CRS_TYPE = CRS
except ImportError:
    # Fallback if pyproj not available
    CRS_TYPE = type(None)

# Attempt ezdxf import
try:
    import ezdxf
    from ezdxf.document import Drawing
    from ezdxf.entities import (
        DXFGraphic,
        LWPolyline, Line, Circle, Arc, Ellipse, Spline, Text, MText, Insert, Hatch
    )
    from ezdxf.math import OCS # For bulge handling if needed
    from ezdxf.enums import MTextEntityAlignment # For MTEXT attachment point
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None)
    DXFGraphic = type(None)
    LWPolyline, Line, Circle, Arc, Ellipse, Spline, Text, MText, Insert, Hatch = (type(None),) * 10
    OCS = type(None)
    MTextEntityAlignment = type(None) # Placeholder
    box = type(None) # Added box placeholder
    EZDXF_AVAILABLE = False

from ..interfaces.geometry_processor_interface import IGeometryProcessor
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.data_source_interface import IDataSource
from ..domain.config_models import (
    TranslateOpParams,
    BoundingBoxOpParams,
    EnvelopeOpParams,
    CreateCirclesOpParams,
    ConnectPointsOpParams, # Added ConnectPointsOpParams
    AllOperationParams,
    GeomLayerDefinition,
    StyleConfig
)
from ..domain.exceptions import GeometryError, DXFProcessingError, ConfigError # Added ConfigError
from ..utils.geodataframe_utils import get_validated_source_gdf, reproject_gdf, get_common_crs, GdfValidationError # Assuming utils are here
from ..utils.advanced_geometry_utils import create_envelope_for_geometry # Added import for new util

class GeometryProcessorService(IGeometryProcessor):
    # Forward declaration for type hint in OPERATION_HANDLERS
    # This assumes the methods are defined later in the class.
    # If Python version is < 3.7, string literal might be needed for _handle_bounding_box_op etc.
    _OPERATION_HANDLERS_SELF_TYPE = Any # Placeholder for self type

    def __init__(self, logger_service: ILoggingService, data_source_service: IDataSource): # Ensure data_source_service is here
        self._logger = logger_service.get_logger(__name__)
        self._data_source_service = data_source_service # Ensure it's stored

    def _handle_translate_op(
        self,
        op_specific_params: TranslateOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        op_name = "translate"
        self._logger.info(f"Handling {op_name} operation with params: {op_specific_params.model_dump_json(indent=2)}")

        if not op_specific_params.layers:
            self._logger.warning(f"{op_name.capitalize()} Op: No source layers specified. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[])

        current_gdf = None
        for layer_ident in op_specific_params.layers:
            try:
                gdf = get_validated_source_gdf(
                    layer_identifier=layer_ident,
                    source_layers=source_layers,
                    allow_empty=True, # Allow empty GDFs, we'll skip them
                    context_message=f"{op_name} source layer validation: {layer_ident}"
                )
                if not gdf.empty:
                    current_gdf = gdf
                    break
            except GdfValidationError as e_val:
                self._logger.warning(f"Could not validate/load layer '{layer_ident}' for {op_name}: {e_val}. Skipping.")
                continue

        if current_gdf is None:
            self._logger.warning(f"{op_name.capitalize()} Op: No valid source layers found after validation. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[])

        try:
            # Apply translation using the correct field names
            translated_gdf = current_gdf.copy()
            translated_gdf.geometry = translated_gdf.geometry.translate(xoff=op_specific_params.dx, yoff=op_specific_params.dy)
            self._logger.info(f"{op_name.capitalize()} operation successful. Translated by dx={op_specific_params.dx}, dy={op_specific_params.dy}")
            return translated_gdf
        except Exception as e:
            # Fixed: Use op_specific_params.layers instead of non-existent layer field
            layer_names = [str(l) for l in op_specific_params.layers]
            self._logger.error(f"Error during translate operation on layers {layer_names}: {e}", exc_info=True)
            raise GeometryError(f"Error during translate operation on layers {layer_names}: {e}") from e

    def _handle_bounding_box_op(
        self,
        params: BoundingBoxOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        op_name = "bounding_box"
        self._logger.info(f"Handling {op_name} operation with params: {params.model_dump_json(indent=2)}")

        if not params.layers:
            self._logger.warning(f"{op_name.capitalize()} Op: No source layers specified. Returning empty GDF.")
            any_crs = None
            if source_layers:
                first_available_gdf = next((gdf for gdf in source_layers.values() if gdf is not None and gdf.crs is not None), None)
                if first_available_gdf is not None:
                    any_crs = first_available_gdf.crs
            return gpd.GeoDataFrame(geometry=[], crs=any_crs)

        overall_bounds: Optional[Tuple[float, float, float, float]] = None
        target_crs_for_output: Optional[Union[str, CRS_TYPE]] = None  # Fixed: was Any, now proper CRS type

        processed_gdfs_for_crs_check: List[gpd.GeoDataFrame] = []
        for layer_ident in params.layers:
            try:
                gdf = get_validated_source_gdf(
                    layer_identifier=layer_ident,
                    source_layers=source_layers,
                    allow_empty=True,
                    context_message=f"{op_name} source layer validation: {layer_ident}"
                )
                if not gdf.empty:
                    processed_gdfs_for_crs_check.append(gdf)
            except GdfValidationError as e_val:
                self._logger.error(f"Failed to validate/load layer '{layer_ident}' for {op_name}: {e_val}")  # Changed from warning to error
                # Don't silently continue - this could lead to empty results with unclear cause
                raise GeometryError(f"Layer validation failed for {op_name} operation on layer '{layer_ident}': {e_val}") from e_val

        if not processed_gdfs_for_crs_check:
            self._logger.warning(f"{op_name.capitalize()} Op: No valid source layers found after validation. Returning empty GDF.")
            # Try to get a CRS from params if possible for the empty GDF
            # For now, returning with potentially None CRS if no valid layers
            return gpd.GeoDataFrame(geometry=[])

        target_crs_for_output = get_common_crs(processed_gdfs_for_crs_check, self._logger.get_logger("utils_common_crs")) # Pass a sub-logger

        if not target_crs_for_output:
             if processed_gdfs_for_crs_check[0].crs:
                  target_crs_for_output = processed_gdfs_for_crs_check[0].crs # Use the CRS object directly
                  self._logger.info(f"Using CRS from first valid layer for output: {str(target_crs_for_output)}")
             else:
                  self._logger.error(f"{op_name.capitalize()} Op: Cannot determine a target CRS for the bounding box output.")
                  raise ConfigError(f"Bounding box operation cannot proceed without a determinable target CRS.")

        for gdf_validated in processed_gdfs_for_crs_check:
            current_gdf = gdf_validated.copy() # Work on a copy

            # Ensure current_gdf is in target_crs_for_output
            if current_gdf.crs and current_gdf.crs != target_crs_for_output:
                try:
                    current_gdf = reproject_gdf(current_gdf, target_crs_for_output, context_message=f"{op_name} reprojection of {str(layer_ident)}")
                except Exception as e_reproject:
                    self._logger.error(f"Failed to reproject layer to {str(target_crs_for_output)} for {op_name}: {e_reproject}. Skipping this layer's bounds.")
                    continue
            elif not current_gdf.crs:
                current_gdf.crs = target_crs_for_output
                self._logger.info(f"Assigned target CRS {str(target_crs_for_output)} to layer formerly lacking CRS.")

            if current_gdf.empty:
                self._logger.debug(f"Skipping empty GDF for bounds calculation in {op_name} ({str(layer_ident)}).")
                continue

            layer_bounds = current_gdf.total_bounds

            if overall_bounds is None:
                overall_bounds = cast(Tuple[float, float, float, float], layer_bounds)
            else:
                overall_bounds = (
                    min(overall_bounds[0], layer_bounds[0]),
                    min(overall_bounds[1], layer_bounds[1]),
                    max(overall_bounds[2], layer_bounds[2]),
                    max(overall_bounds[3], layer_bounds[3])
                )

        if overall_bounds is None:
            self._logger.warning(f"{op_name.capitalize()} Op: No geometries found across all valid source layers. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=target_crs_for_output)

        minx, miny, maxx, maxy = overall_bounds
        if params.padding != 0:
            minx -= params.padding
            miny -= params.padding
            maxx += params.padding
            maxy += params.padding

        try:
            bbox_polygon = box(minx, miny, maxx, maxy)
            if not bbox_polygon.is_valid:
                self._logger.warning(f"Bounding box created from bounds ({minx},{miny},{maxx},{maxy}) with padding {params.padding} is invalid. Attempting to make valid.")
                bbox_polygon = make_valid(bbox_polygon) # make_valid is already imported
                if not bbox_polygon.is_valid: # Still invalid
                     self._logger.error(f"Bounding box remains invalid after make_valid. Bounds: ({minx},{miny},{maxx},{maxy}), Padding: {params.padding}")
                     raise GeometryError(f"Failed to create a valid bounding box polygon for {op_name} after attempting make_valid.")

        except Exception as e_box:
            self._logger.error(f"Error creating shapely.geometry.box for {op_name}: {e_box}. Bounds: ({minx},{miny},{maxx},{maxy})", exc_info=True)
            raise GeometryError(f"Failed to create bounding box polygon for {op_name}: {e_box}") from e_box

        result_gdf = gpd.GeoDataFrame(geometry=[bbox_polygon], crs=target_crs_for_output)
        self._logger.info(f"{op_name.capitalize()} operation successful. Created bounding box: {bbox_polygon.wkt[:100]}...")
        return result_gdf

    def _handle_envelope_op(
        self,
        params: EnvelopeOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        op_name = "envelope"
        self._logger.info(f"Handling {op_name} operation with params: {params.model_dump_json(indent=2)}")

        if not params.layers:
            self._logger.warning(f"{op_name.capitalize()} Op: No source layers specified. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=None)

        all_results: List[Polygon] = []
        valid_input_gdfs_for_crs: List[gpd.GeoDataFrame] = []
        for layer_ident in params.layers:
            try:
                # Ensure layer_ident is a string if it's a dict for logging purposes later
                log_layer_ident = layer_ident if isinstance(layer_ident, str) else layer_ident.get('name', str(layer_ident))
                gdf = get_validated_source_gdf(
                    layer_identifier=layer_ident,
                    source_layers=source_layers,
                    allow_empty=True,
                    expected_geom_types=["Polygon", "MultiPolygon"],
                    context_message=f"{op_name} source layer validation (CRS pre-check) for '{log_layer_ident}'"
                )
                if not gdf.empty:
                    # Store original layer identifier if it was a dict, for later logging
                    if isinstance(layer_ident, dict) and 'name' in layer_ident :
                         gdf.attrs['original_layer_identifier'] = layer_ident['name']
                    elif isinstance(layer_ident, str):
                         gdf.attrs['original_layer_identifier'] = layer_ident
                    valid_input_gdfs_for_crs.append(gdf)
            except GdfValidationError as e_val:
                log_layer_ident_err = layer_ident if isinstance(layer_ident, str) else layer_ident.get('name', str(layer_ident))
                self._logger.warning(f"Could not validate/load layer '{log_layer_ident_err}' for {op_name} (CRS pre-check): {e_val}. Skipping.")

        if not valid_input_gdfs_for_crs:
            self._logger.warning(f"{op_name.capitalize()} Op: No valid source layers with polygons found after validation. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=None)

        util_logger = self._logger

        target_crs = get_common_crs(valid_input_gdfs_for_crs, util_logger)
        if not target_crs:
            self._logger.warning(f"{op_name.capitalize()} Op: Could not determine a common CRS. Using CRS of first valid layer if available.")
            # Attempt to get CRS from the first GDF that has one
            first_gdf_with_crs = next((gdf for gdf in valid_input_gdfs_for_crs if gdf.crs is not None), None)
            if first_gdf_with_crs is None:
                 self._logger.error(f"{op_name.capitalize()} operation failed: No common CRS and no valid input layers have a CRS. Aborting.")
                 raise ConfigError(f"{op_name.capitalize()} operation failed: No common CRS could be determined and no layers had CRS.")
            target_crs = first_gdf_with_crs.crs
            self._logger.info(f"{op_name.capitalize()} Op: Using CRS of first valid layer with CRS: {target_crs}")


        for gdf_validated in valid_input_gdfs_for_crs:
            current_gdf = gdf_validated
            # Retrieve the original identifier for logging
            original_layer_name_for_log = gdf_validated.attrs.get('original_layer_identifier', 'unknown_layer')


            if current_gdf.crs != target_crs:
                try:
                    current_gdf = reproject_gdf(current_gdf, target_crs, context_message=f"{op_name} reprojection of '{original_layer_name_for_log}'")
                except Exception as e_reproject:
                    self._logger.error(f"Failed to reproject layer '{original_layer_name_for_log}' to {target_crs} for {op_name}: {e_reproject}. Skipping this layer.")
                    continue

            for geom_idx, geom in enumerate(current_gdf.geometry):
                if not geom or geom.is_empty or not isinstance(geom, (Polygon, MultiPolygon)):
                    continue

                geometries_to_process: List[Polygon] = []
                if isinstance(geom, MultiPolygon):
                    for i, part_poly in enumerate(geom.geoms):
                        if isinstance(part_poly, Polygon) and not part_poly.is_empty:
                            geometries_to_process.append(part_poly)
                        else:
                            self._logger.debug(f"{op_name} Op: Skipping non-Polygon or empty part {i} in MultiPolygon from layer '{original_layer_name_for_log}', geom {geom_idx}.")
                elif isinstance(geom, Polygon):
                    geometries_to_process.append(geom)

                for poly_idx, poly_to_process in enumerate(geometries_to_process):
                    current_polygon_for_op = poly_to_process
                    # Log which part of original geometry this is, if from MultiPolygon
                    log_geom_part_id = f"part {poly_idx}" if isinstance(geom, MultiPolygon) else "single"

                    if not current_polygon_for_op.is_valid:
                        self._logger.warning(f"{op_name} Op: Input polygon ({log_geom_part_id}) for envelope (from layer '{original_layer_name_for_log}', orig_geom_idx {geom_idx}) is invalid, attempting to make valid. WKT: {current_polygon_for_op.wkt[:50]}...")
                        current_polygon_for_op = make_valid(current_polygon_for_op)

                        if not isinstance(current_polygon_for_op, Polygon):
                             self._logger.error(f"{op_name} Op: make_valid on part ({log_geom_part_id}) resulted in non-Polygon type ({type(current_polygon_for_op)}). Skipping this geometry part.")
                             continue
                        if not current_polygon_for_op.is_valid:
                            self._logger.error(f"{op_name} Op: Failed to make polygon part ({log_geom_part_id}) valid. Skipping.")
                            continue

                    envelope = create_envelope_for_geometry(
                        current_polygon_for_op, params.padding, params.min_ratio, params.cap_style, util_logger
                    )
                    if envelope:
                        if not envelope.is_valid:
                            self._logger.warning(f"{op_name} Op: Envelope created for part ({log_geom_part_id}) is invalid, attempting make_valid. WKT: {envelope.wkt[:50]}")
                            envelope = make_valid(envelope)
                            if not envelope.is_valid or not isinstance(envelope, Polygon):
                                self._logger.error(f"{op_name} Op: Failed to make envelope for part ({log_geom_part_id}) valid or it's not a Polygon. Discarding.")
                                continue
                        all_results.append(envelope)

        if not all_results:
            self._logger.warning(f"{op_name.capitalize()} Op: No envelopes were generated. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=target_crs)

        result_gdf = gpd.GeoDataFrame(geometry=all_results, crs=target_crs)
        self._logger.info(f"{op_name.capitalize()} operation successful. Generated {len(result_gdf)} envelopes.")
        return result_gdf

    def _handle_create_circles_op(
        self,
        params: CreateCirclesOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        op_name = "create_circles"
        self._logger.info(f"Handling {op_name} operation with params: {params.model_dump_json(indent=2)}")

        if not params.layers:
            self._logger.warning(f"{op_name.capitalize()} Op: No source layers specified. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=None)

        all_created_circles: List[BaseGeometry] = []
        all_attributes: List[Dict[str, Any]] = [] # To store attributes from source

        valid_input_gdfs_for_crs: List[gpd.GeoDataFrame] = []
        processed_layer_names: List[str] = []

        for layer_ident_idx, layer_ident in enumerate(params.layers):
            log_layer_ident = layer_ident if isinstance(layer_ident, str) else layer_ident.get('name', f"layer_at_index_{layer_ident_idx}")
            try:
                gdf = get_validated_source_gdf(
                    layer_identifier=layer_ident,
                    source_layers=source_layers,
                    allow_empty=True,
                    expected_geom_types=["Point"],
                    context_message=f"{op_name} source layer validation (CRS pre-check) for '{log_layer_ident}'"
                )
                if not gdf.empty:
                    if isinstance(layer_ident, dict) and 'name' in layer_ident:
                        gdf.attrs['original_layer_identifier'] = layer_ident['name']
                    elif isinstance(layer_ident, str):
                        gdf.attrs['original_layer_identifier'] = layer_ident
                    else:
                        gdf.attrs['original_layer_identifier'] = f"input_layer_{layer_ident_idx}"

                    valid_input_gdfs_for_crs.append(gdf)
                    processed_layer_names.append(gdf.attrs['original_layer_identifier'])

            except GdfValidationError as e_val:
                self._logger.warning(f"Could not validate/load layer '{log_layer_ident}' for {op_name} (CRS pre-check): {e_val}. Skipping.")

        if not valid_input_gdfs_for_crs:
            self._logger.warning(f"{op_name.capitalize()} Op: No valid source layers with points found after validation. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=None)

        target_crs = get_common_crs(valid_input_gdfs_for_crs, self._logger)
        if not target_crs and valid_input_gdfs_for_crs:
            # Try to get CRS from the first GDF that has one
            first_gdf_with_crs = next((gdf for gdf in valid_input_gdfs_for_crs if gdf.crs is not None), None)
            if first_gdf_with_crs:
                target_crs = first_gdf_with_crs.crs
                self._logger.info(f"{op_name.capitalize()} Op: Using CRS of first valid layer with CRS: {target_crs}")
            else: # Still no CRS
                 self._logger.error(f"{op_name.capitalize()} Op: Cannot determine a target CRS. Processed layers: {', '.join(processed_layer_names)}. Aborting.")
                 raise ConfigError(f"{op_name.capitalize()} operation cannot determine a target CRS from layers: {', '.join(processed_layer_names)}.")

        self._logger.info(f"Target CRS for {op_name}: {target_crs}")

        for gdf_validated in valid_input_gdfs_for_crs:
            current_gdf = gdf_validated.copy() # Work on a copy
            original_layer_name_for_log = current_gdf.attrs.get('original_layer_identifier', 'unknown_layer')

            if current_gdf.crs != target_crs and target_crs is not None:
                try:
                    self._logger.debug(f"Reprojecting layer '{original_layer_name_for_log}' from {current_gdf.crs} to {target_crs} for {op_name}.")
                    current_gdf = reproject_gdf(current_gdf, target_crs, context_message=f"{op_name} reprojection of '{original_layer_name_for_log}'")
                except Exception as e_reproject:
                    self._logger.error(f"Failed to reproject layer '{original_layer_name_for_log}' to {target_crs} for {op_name}: {e_reproject}. Skipping this layer.")
                    continue
            elif not current_gdf.crs and target_crs is not None:
                current_gdf.crs = target_crs
                self._logger.info(f"Assigned target CRS {str(target_crs)} to layer '{original_layer_name_for_log}' which formerly lacked CRS.")


            for index, row in current_gdf.iterrows():
                point_geom = row.geometry
                if not isinstance(point_geom, Point) or point_geom.is_empty:
                    self._logger.debug(f"Skipping non-Point or empty geometry at index {index} in layer '{original_layer_name_for_log}'.")
                    continue

                radius_val: Optional[float] = None
                if params.radius is not None: # Fixed radius
                    radius_val = params.radius
                elif params.radius_field:
                    if params.radius_field not in row:
                        self._logger.warning(f"Radius field '{params.radius_field}' not found in attributes for point at index {index} in layer '{original_layer_name_for_log}'. Skipping.")
                        continue
                    try:
                        field_val = row[params.radius_field]
                        if field_val is None:
                            self._logger.warning(f"Radius field '{params.radius_field}' has None value for point at index {index}, layer '{original_layer_name_for_log}'. Skipping.")
                            continue
                        radius_val = float(field_val)
                    except (ValueError, TypeError) as e_conv:
                        self._logger.warning(f"Could not convert radius value '{row[params.radius_field]}' from field '{params.radius_field}' to float for point at index {index}, layer '{original_layer_name_for_log}': {e_conv}. Skipping.")
                        continue

                if radius_val is None: # Should have been caught by validator, but defensive check
                    self._logger.error(f"Logic error: No radius determined for point at index {index}, layer '{original_layer_name_for_log}', despite Pydantic validation. Params: {params}. Skipping.")
                    continue

                if radius_val <= 0:
                    self._logger.warning(f"Radius value '{radius_val}' (from {'fixed param' if params.radius else 'field ' + str(params.radius_field)}) is non-positive for point at index {index}, layer '{original_layer_name_for_log}'. Skipping circle creation.")
                    continue

                try:
                    circle_poly = point_geom.buffer(radius_val)
                    if not circle_poly.is_valid:
                        self._logger.warning(f"Created circle for point at index {index}, layer '{original_layer_name_for_log}' is invalid. Attempting make_valid.")
                        circle_poly = make_valid(circle_poly)
                        if not circle_poly.is_valid:
                             self._logger.error(f"Circle remains invalid after make_valid for point at index {index}, layer '{original_layer_name_for_log}'. Skipping.")
                             continue

                    all_created_circles.append(circle_poly)
                    # Preserve attributes from the source point
                    attributes = row.drop('geometry').to_dict()
                    attributes['source_layer'] = original_layer_name_for_log # Add source layer info
                    attributes['original_index'] = index
                    all_attributes.append(attributes)

                except Exception as e_buffer:
                    self._logger.error(f"Error creating circle buffer for point at index {index}, layer '{original_layer_name_for_log}' with radius {radius_val}: {e_buffer}", exc_info=True)
                    continue

        if not all_created_circles:
            self._logger.warning(f"{op_name.capitalize()} Op: No circles were generated from any source layers. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=target_crs)

        # Create the final GeoDataFrame
        try:
            result_gdf = gpd.GeoDataFrame(all_attributes, geometry=all_created_circles, crs=target_crs)
            self._logger.info(f"{op_name.capitalize()} operation successful. Generated {len(result_gdf)} circles from layers: {', '.join(processed_layer_names)}.")
        except Exception as e_gdf_create:
            self._logger.error(f"Error creating final GeoDataFrame for {op_name}: {e_gdf_create}", exc_info=True)
            raise GeometryError(f"Failed to create result GeoDataFrame for {op_name}: {e_gdf_create}")

        return result_gdf

    def _handle_connect_points_op(
        self,
        params: ConnectPointsOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        op_name = "connect_points"
        self._logger.info(f"Handling {op_name} operation with params: {params.model_dump_json(indent=2)}")

        if not params.layers:
            self._logger.warning(f"{op_name.capitalize()} Op: No source layers specified. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=None)

        all_points_coords: List[Tuple[float, float]] = []
        # Consider preserving attributes if a single line is created or if lines can be associated with a group ID.
        # For now, focusing on geometry creation.

        valid_input_gdfs_for_crs: List[gpd.GeoDataFrame] = []
        processed_layer_names: List[str] = []

        for layer_ident_idx, layer_ident in enumerate(params.layers):
            log_layer_ident = layer_ident if isinstance(layer_ident, str) else layer_ident.get('name', f"layer_at_index_{layer_ident_idx}")
            try:
                gdf = get_validated_source_gdf(
                    layer_identifier=layer_ident,
                    source_layers=source_layers,
                    allow_empty=True,
                    expected_geom_types=["Point", "MultiPoint"], # Corrected string literals
                    context_message=f"{op_name} source layer validation for '{log_layer_ident}'" # Corrected f-string
                )
                if not gdf.empty:
                    # Store original layer identifier
                    attr_name = f"input_layer_{layer_ident_idx}"
                    if isinstance(layer_ident, dict) and 'name' in layer_ident: attr_name = layer_ident['name']
                    elif isinstance(layer_ident, str): attr_name = layer_ident
                    gdf.attrs['original_layer_identifier'] = attr_name

                    valid_input_gdfs_for_crs.append(gdf)
                    processed_layer_names.append(attr_name)

                    # Extract points
                    for geom in gdf.geometry:
                        if isinstance(geom, Point):
                            all_points_coords.append((geom.x, geom.y))
                        elif isinstance(geom, MultiPoint):
                            for p_geom in geom.geoms:
                                if isinstance(p_geom, Point):
                                    all_points_coords.append((p_geom.x, p_geom.y))
            except GdfValidationError as e_val:
                self._logger.warning(f"Could not validate/load layer '{log_layer_ident}' for {op_name}: {e_val}. Skipping.")

        if not valid_input_gdfs_for_crs:
            self._logger.warning(f"{op_name.capitalize()} Op: No valid source layers with points found. Returning empty GDF.")
            return gpd.GeoDataFrame(geometry=[], crs=None)

        target_crs = get_common_crs(valid_input_gdfs_for_crs, self._logger)
        if not target_crs and valid_input_gdfs_for_crs:
            first_gdf_with_crs = next((gdf for gdf in valid_input_gdfs_for_crs if gdf.crs is not None), None)
            if first_gdf_with_crs: target_crs = first_gdf_with_crs.crs

        if not target_crs: # Still no CRS after trying first valid GDF
            self._logger.error(f"{op_name.capitalize()} Op: Cannot determine a target CRS. Processed layers: {', '.join(processed_layer_names)}. Aborting.")
            raise ConfigError(f"{op_name.capitalize()} operation cannot determine a target CRS from layers: {', '.join(processed_layer_names)}.")

        self._logger.info(f"Target CRS for {op_name}: {target_crs}. Total unique points extracted: {len(set(all_points_coords))}")

        # Remove duplicate points before processing
        unique_points_list = sorted(list(set(all_points_coords))) # Sort for consistent ordering if it matters later

        if not unique_points_list:
            self._logger.warning(f"{op_name.capitalize()} Op: No unique points found to connect. Layers processed: {', '.join(processed_layer_names)}.")
            return gpd.GeoDataFrame(geometry=[], crs=target_crs)

        if len(unique_points_list) == 1:
            self._logger.warning(f"{op_name.capitalize()} Op: Only one unique point found. Cannot create connecting line.")
            return gpd.GeoDataFrame(geometry=[], crs=target_crs)

        points_array = np.array(unique_points_list)
        lines: List[LineString] = []

        if params.max_distance is not None:
            self._logger.info(f"{op_name.capitalize()} Op: Grouping points with max_distance: {params.max_distance}")
            groups_indices: List[List[int]] = []
            remaining_indices = list(range(len(points_array))) # Use list for pop

            while remaining_indices:
                current_group_indices = [remaining_indices.pop(0)] # Start group with first available point

                # Iteratively add points to current_group_indices
                # This loop ensures we capture all points connected to the current group
                # A bit complex; might need refinement if performance is critical for huge numbers of sparse groups.
                group_changed_this_iteration = True
                while group_changed_this_iteration:
                    group_changed_this_iteration = False
                    newly_added_to_group = []

                    # Points currently in the group being built
                    current_group_coords = points_array[current_group_indices]

                    # Check against points not yet in any group
                    temp_remaining_indices = []
                    for rem_idx in remaining_indices:
                        point_to_check_coords = points_array[rem_idx].reshape(1, -1)
                        distances_to_group = cdist(point_to_check_coords, current_group_coords)

                        if np.min(distances_to_group) <= params.max_distance:
                            newly_added_to_group.append(rem_idx)
                            group_changed_this_iteration = True
                        else:
                            temp_remaining_indices.append(rem_idx)

                    if newly_added_to_group:
                        current_group_indices.extend(newly_added_to_group)
                    remaining_indices = temp_remaining_indices # Update overall remaining_indices

                groups_indices.append(current_group_indices)

            self._logger.info(f"{op_name.capitalize()} Op: Formed {len(groups_indices)} groups.")

            for group_idx_list in groups_indices:
                if len(group_idx_list) > 1:
                    group_points_coords = points_array[group_idx_list]

                    # Nearest neighbor path within the group
                    path_in_group_indices = [0] # Start with the first point in this group's sub-array
                    points_left_in_group = list(range(1, len(group_points_coords)))

                    while points_left_in_group:
                        current_path_end_idx = path_in_group_indices[-1]
                        current_path_end_coords = group_points_coords[current_path_end_idx].reshape(1, -1)

                        remaining_group_points_coords = group_points_coords[points_left_in_group]

                        distances_in_group = cdist(current_path_end_coords, remaining_group_points_coords)[0]
                        nearest_in_group_temp_idx = np.argmin(distances_in_group)

                        actual_next_point_idx_in_group = points_left_in_group.pop(nearest_in_group_temp_idx)
                        path_in_group_indices.append(actual_next_point_idx_in_group)

                    connected_group_points_coords = [tuple(coord) for coord in group_points_coords[path_in_group_indices]]
                    lines.append(LineString(connected_group_points_coords))
                elif len(group_idx_list) == 1:
                    self._logger.debug(f"{op_name.capitalize()} Op: Group with single point found. Skipping line creation for this group.")
        else: # No max_distance, connect all points
            self._logger.info(f"{op_name.capitalize()} Op: Connecting all {len(points_array)} unique points into a single line.")
            path_indices = [0] # Start with the first point
            remaining_overall_indices = list(range(1, len(points_array)))

            while remaining_overall_indices:
                current_path_end_idx = path_indices[-1]
                current_path_end_coords = points_array[current_path_end_idx].reshape(1, -1)

                remaining_points_coords = points_array[remaining_overall_indices]

                distances = cdist(current_path_end_coords, remaining_points_coords)[0]
                nearest_temp_idx = np.argmin(distances)

                actual_next_point_idx = remaining_overall_indices.pop(nearest_temp_idx)
                path_indices.append(actual_next_point_idx)

            connected_all_points_coords = [tuple(coord) for coord in points_array[path_indices]]
            lines.append(LineString(connected_all_points_coords))

        if not lines:
            self._logger.warning(f"{op_name.capitalize()} Op: No lines were created. Layers processed: {', '.join(processed_layer_names)}.")
            return gpd.GeoDataFrame(geometry=[], crs=target_crs)

        result_gdf = gpd.GeoDataFrame(geometry=lines, crs=target_crs)
        self._logger.info(f"{op_name.capitalize()} operation successful. Generated {len(result_gdf)} LineString(s).")
        return result_gdf

    def process_operations(
        self,
        operations: List[Dict[str, Any]],
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> Dict[str, gpd.GeoDataFrame]:
        result_gdfs: Dict[str, gpd.GeoDataFrame] = {}
        for operation in operations:
            op_name = operation['name']
            if op_name in self.OPERATION_HANDLERS:
                result_gdfs[op_name] = self.OPERATION_HANDLERS[op_name](self, operation, source_layers)
            else:
                self._logger.warning(f"Operation '{op_name}' not recognized. Skipping.")
        return result_gdfs

    def _extract_entities_as_gdf_from_dxf_layer(
        self,
        dxf_layer: Drawing,
        layer_name: str
    ) -> gpd.GeoDataFrame:
        # Implementation of _extract_entities_as_gdf_from_dxf_layer method
        pass

    # Interface method implementations

    def apply_operation(
        self,
        operation_params: AllOperationParams,
        source_layers: Dict[str, gpd.GeoDataFrame],
    ) -> gpd.GeoDataFrame:
        """Applies a geometric operation based on the provided parameters."""
        operation_type = operation_params.type
        self._logger.info(f"Applying operation: {operation_type}")

        if operation_type in self.OPERATION_HANDLERS:
            return self.OPERATION_HANDLERS[operation_type](self, operation_params, source_layers)
        else:
            self._logger.error(f"Unsupported operation type: {operation_type}")
            raise GeometryError(f"Unsupported operation type: {operation_type}")

    def create_layer_from_definition(
        self,
        layer_def: GeomLayerDefinition,
        dxf_drawing: Optional[Drawing],
        style_config: StyleConfig,
        base_crs: str,
        project_root: Optional[str] = None
    ) -> Optional[gpd.GeoDataFrame]:
        """Creates a GeoDataFrame for a layer based on its definition."""
        self._logger.info(f"Creating layer '{layer_def.name}' from definition")

        try:
            # Handle GeoJSON file source
            if layer_def.geojson_file:
                geojson_path = layer_def.geojson_file

                # Resolve path relative to project directory if project_root is provided
                if project_root and not os.path.isabs(geojson_path):
                    geojson_path = os.path.join(project_root, geojson_path)
                    geojson_path = os.path.normpath(geojson_path)

                self._logger.info(f"Loading GeoJSON file: {geojson_path}")
                gdf = self._data_source_service.load_geojson_file(geojson_path)

                # Apply selectByProperties filtering if specified
                if layer_def.select_by_properties:
                    self._logger.info(f"Applying selectByProperties filter: {layer_def.select_by_properties}")
                    original_count = len(gdf)

                    # Create filter mask based on all property conditions
                    filter_mask = pd.Series([True] * len(gdf))

                    for prop_name, prop_value in layer_def.select_by_properties.items():
                        if prop_name in gdf.columns:
                            prop_mask = gdf[prop_name] == prop_value
                            filter_mask = filter_mask & prop_mask
                            self._logger.debug(f"Applied filter {prop_name}=={prop_value}, matching features: {prop_mask.sum()}")
                        else:
                            self._logger.warning(f"Property '{prop_name}' not found in GeoJSON columns: {list(gdf.columns)}")
                            # If property doesn't exist, no features match this condition
                            filter_mask = pd.Series([False] * len(gdf))
                            break

                    # Apply the filter
                    gdf = gdf[filter_mask].reset_index(drop=True)
                    filtered_count = len(gdf)

                    self._logger.info(f"Filtered layer '{layer_def.name}': {original_count} -> {filtered_count} features")

                    if filtered_count == 0:
                        self._logger.warning(f"No features match the selectByProperties filter for layer '{layer_def.name}'")

                # Set CRS if not present
                if gdf.crs is None:
                    gdf.crs = base_crs
                    self._logger.info(f"Assigned base CRS {base_crs} to layer '{layer_def.name}'")
                elif str(gdf.crs) != base_crs:
                    self._logger.info(f"Reprojecting layer '{layer_def.name}' from {gdf.crs} to {base_crs}")
                    gdf = gdf.to_crs(base_crs)

                return gdf

            # Handle DXF layer extraction (placeholder - would need full implementation)
            elif layer_def.dxf_layer and dxf_drawing:
                self._logger.warning(f"DXF layer extraction not fully implemented for layer '{layer_def.name}'")
                return gpd.GeoDataFrame(geometry=[], crs=base_crs)

            # Handle shapefile source (placeholder)
            elif layer_def.shape_file:
                self._logger.warning(f"Shapefile loading not implemented for layer '{layer_def.name}'")
                return gpd.GeoDataFrame(geometry=[], crs=base_crs)

            else:
                self._logger.warning(f"No valid data source found for layer '{layer_def.name}'")
                return None

        except Exception as e:
            self._logger.error(f"Failed to create layer '{layer_def.name}': {e}", exc_info=True)
            raise GeometryError(f"Failed to create layer '{layer_def.name}': {e}") from e

    def merge_layers(
        self,
        layers_to_merge: List[gpd.GeoDataFrame],
        target_crs: Optional[str] = None
    ) -> gpd.GeoDataFrame:
        """Merges multiple GeoDataFrames into a single GeoDataFrame."""
        if not layers_to_merge:
            return gpd.GeoDataFrame(geometry=[])

        if len(layers_to_merge) == 1:
            return layers_to_merge[0].copy()

        # Use first layer's CRS if target_crs not specified
        if target_crs is None:
            target_crs = str(layers_to_merge[0].crs)

        merged_layers = []
        for gdf in layers_to_merge:
            if gdf.crs and str(gdf.crs) != target_crs:
                gdf = gdf.to_crs(target_crs)
            merged_layers.append(gdf)

        return gpd.concat(merged_layers, ignore_index=True)

    def reproject_layer(self, layer: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        """Reprojects a GeoDataFrame to the target CRS."""
        if layer.crs and str(layer.crs) != target_crs:
            return layer.to_crs(target_crs)
        return layer

    @property
    def OPERATION_HANDLERS(self) -> Dict[str, Callable[["GeometryProcessorService", Any, Dict[str, gpd.GeoDataFrame]], gpd.GeoDataFrame]]:
        """Returns the operation handlers dictionary."""
        return {
            "translate": self._handle_translate_op,
            "bounding_box": self._handle_bounding_box_op,
            "envelope": self._handle_envelope_op,
            "create_circles": self._handle_create_circles_op,
            "connect_points": self._handle_connect_points_op,
        }
