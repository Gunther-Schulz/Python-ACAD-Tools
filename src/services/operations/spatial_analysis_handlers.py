"""Spatial analysis operation handlers following existing patterns."""
from typing import Dict, Any, Union, List, Optional, cast

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.validation import make_valid

from ...domain.config_models import (
    BufferOpParams, DifferenceOpParams, IntersectionOpParams, UnionOpParams,
    SymmetricDifferenceOpParams, BoundingBoxOpParams, EnvelopeOpParams, OffsetCurveOpParams
)
from ...domain.exceptions import GeometryError
from ...services.geometry import EnvelopeService
from .base_operation_handler import BaseOperationHandler

# Import box for bounding box operation
try:
    from shapely.geometry import box
except ImportError:
    box = None


class BufferHandler(BaseOperationHandler):
    """Handle buffer operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "buffer"

    def handle(
        self,
        params: BufferOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle buffer operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Buffer Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        all_results = []
        all_attributes = []
        valid_gdfs = []

        # Collect all valid input GDFs
        for layer_ident in params.layers:
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True
                )
                if not gdf.empty:
                    valid_gdfs.append(gdf)
            except GeometryError:
                continue

        if not valid_gdfs:
            self._logger.warning(f"Buffer Op: No valid source layers found. Returning empty GDF.")
            return self._create_empty_result()

        # Get common CRS
        target_crs = self._get_common_crs_for_layers(valid_gdfs, self.operation_type)

        # Process each valid GDF
        for gdf in valid_gdfs:
            layer_name = "unknown_layer"
            current_gdf = self._reproject_to_common_crs(gdf, target_crs, layer_name, self.operation_type)

            for index, row in current_gdf.iterrows():
                geom = row.geometry
                if not geom or geom.is_empty:
                    continue

                # Determine buffer distance
                buffer_distance = None
                if params.distance is not None:
                    buffer_distance = params.distance
                elif params.distance_field and params.distance_field in row:
                    try:
                        buffer_distance = float(row[params.distance_field])
                    except (ValueError, TypeError):
                        self._logger.warning(f"Invalid distance value in field '{params.distance_field}' at index {index}")
                        continue

                if buffer_distance is None or buffer_distance < 0:
                    continue

                try:
                    # Convert join_style and cap_style to shapely parameters
                    join_style_map = {'round': 1, 'mitre': 2, 'bevel': 3}
                    cap_style_map = {'round': 1, 'flat': 2, 'square': 3}

                    join_style_val = join_style_map.get(params.join_style, 2)  # Default to mitre
                    cap_style_val = cap_style_map.get(params.cap_style, 3)    # Default to square

                    # Apply buffer
                    buffered_geom = geom.buffer(
                        buffer_distance,
                        cap_style=cap_style_val,
                        join_style=join_style_val
                    )

                    if params.make_valid and not buffered_geom.is_valid:
                        buffered_geom = make_valid(buffered_geom)

                    if buffered_geom and not buffered_geom.is_empty:
                        all_results.append(buffered_geom)
                        # Preserve attributes
                        attributes = row.drop('geometry').to_dict()
                        attributes['buffer_distance'] = buffer_distance
                        all_attributes.append(attributes)

                except Exception as e:
                    self._logger.warning(f"Failed to buffer geometry at index {index}: {e}")
                    continue

        if not all_results:
            self._logger.warning(f"Buffer Op: No geometries were buffered successfully. Returning empty GDF.")
            return self._create_empty_result(target_crs)

        result_gdf = gpd.GeoDataFrame(all_attributes, geometry=all_results, crs=target_crs)
        self._log_operation_success(self.operation_type, len(result_gdf), f"Buffer distance: {params.distance or 'field-based'}")
        return result_gdf


class DifferenceHandler(BaseOperationHandler):
    """Handle difference operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "difference"

    def handle(
        self,
        params: DifferenceOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle difference operation (A - B) following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers or len(params.layers) < 2:
            self._logger.warning(f"Difference Op: Need at least 2 layers. Returning empty GDF.")
            return self._create_empty_result()

        try:
            # Get the two input layers
            gdf_a = self._validate_and_get_source_layer(
                params.layers[0], source_layers, self.operation_type, allow_empty=False
            )
            gdf_b = self._validate_and_get_source_layer(
                params.layers[1], source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf_a.empty or gdf_b.empty:
            self._logger.warning(f"Difference Op: One or both input layers are empty.")
            return self._create_empty_result()

        # Get common CRS and reproject
        target_crs = self._get_common_crs_for_layers([gdf_a, gdf_b], self.operation_type)
        gdf_a = self._reproject_to_common_crs(gdf_a, target_crs, "layer_a", self.operation_type)
        gdf_b = self._reproject_to_common_crs(gdf_b, target_crs, "layer_b", self.operation_type)

        try:
            # Perform difference operation using overlay
            result_gdf = gpd.overlay(gdf_a, gdf_b, how='difference', keep_geom_type=False)

            self._log_operation_success(self.operation_type, len(result_gdf))
            return result_gdf

        except Exception as e:
            self._logger.error(f"Error during difference operation: {e}", exc_info=True)
            raise GeometryError(f"Error during difference operation: {e}") from e


class IntersectionHandler(BaseOperationHandler):
    """Handle intersection operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "intersection"

    def handle(
        self,
        params: IntersectionOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle intersection operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers or len(params.layers) < 2:
            self._logger.warning(f"Intersection Op: Need at least 2 layers. Returning empty GDF.")
            return self._create_empty_result()

        try:
            # Get the two input layers
            gdf_a = self._validate_and_get_source_layer(
                params.layers[0], source_layers, self.operation_type, allow_empty=False
            )
            gdf_b = self._validate_and_get_source_layer(
                params.layers[1], source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf_a.empty or gdf_b.empty:
            self._logger.warning(f"Intersection Op: One or both input layers are empty.")
            return self._create_empty_result()

        # Get common CRS and reproject
        target_crs = self._get_common_crs_for_layers([gdf_a, gdf_b], self.operation_type)
        gdf_a = self._reproject_to_common_crs(gdf_a, target_crs, "layer_a", self.operation_type)
        gdf_b = self._reproject_to_common_crs(gdf_b, target_crs, "layer_b", self.operation_type)

        try:
            # Perform intersection operation using overlay
            result_gdf = gpd.overlay(gdf_a, gdf_b, how='intersection', keep_geom_type=False)

            self._log_operation_success(self.operation_type, len(result_gdf))
            return result_gdf

        except Exception as e:
            self._logger.error(f"Error during intersection operation: {e}", exc_info=True)
            raise GeometryError(f"Error during intersection operation: {e}") from e


class UnionHandler(BaseOperationHandler):
    """Handle union operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "union"

    def handle(
        self,
        params: UnionOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle union operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers or len(params.layers) < 2:
            self._logger.warning(f"Union Op: Need at least 2 layers. Returning empty GDF.")
            return self._create_empty_result()

        try:
            # Get the two input layers
            gdf_a = self._validate_and_get_source_layer(
                params.layers[0], source_layers, self.operation_type, allow_empty=False
            )
            gdf_b = self._validate_and_get_source_layer(
                params.layers[1], source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf_a.empty or gdf_b.empty:
            self._logger.warning(f"Union Op: One or both input layers are empty.")
            return self._create_empty_result()

        # Get common CRS and reproject
        target_crs = self._get_common_crs_for_layers([gdf_a, gdf_b], self.operation_type)
        gdf_a = self._reproject_to_common_crs(gdf_a, target_crs, "layer_a", self.operation_type)
        gdf_b = self._reproject_to_common_crs(gdf_b, target_crs, "layer_b", self.operation_type)

        try:
            # Perform union operation using overlay
            result_gdf = gpd.overlay(gdf_a, gdf_b, how='union', keep_geom_type=False)

            self._log_operation_success(self.operation_type, len(result_gdf))
            return result_gdf

        except Exception as e:
            self._logger.error(f"Error during union operation: {e}", exc_info=True)
            raise GeometryError(f"Error during union operation: {e}") from e


class SymmetricDifferenceHandler(BaseOperationHandler):
    """Handle symmetric difference operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "symmetric_difference"

    def handle(
        self,
        params: SymmetricDifferenceOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle symmetric difference operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers or len(params.layers) < 2:
            self._logger.warning(f"Symmetric Difference Op: Need at least 2 layers. Returning empty GDF.")
            return self._create_empty_result()

        try:
            # Get the two input layers
            gdf_a = self._validate_and_get_source_layer(
                params.layers[0], source_layers, self.operation_type, allow_empty=False
            )
            gdf_b = self._validate_and_get_source_layer(
                params.layers[1], source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf_a.empty or gdf_b.empty:
            self._logger.warning(f"Symmetric Difference Op: One or both input layers are empty.")
            return self._create_empty_result()

        # Get common CRS and reproject
        target_crs = self._get_common_crs_for_layers([gdf_a, gdf_b], self.operation_type)
        gdf_a = self._reproject_to_common_crs(gdf_a, target_crs, "layer_a", self.operation_type)
        gdf_b = self._reproject_to_common_crs(gdf_b, target_crs, "layer_b", self.operation_type)

        try:
            # Perform symmetric difference operation using overlay
            result_gdf = gpd.overlay(gdf_a, gdf_b, how='symmetric_difference', keep_geom_type=False)

            self._log_operation_success(self.operation_type, len(result_gdf))
            return result_gdf

        except Exception as e:
            self._logger.error(f"Error during symmetric difference operation: {e}", exc_info=True)
            raise GeometryError(f"Error during symmetric difference operation: {e}") from e


class BoundingBoxHandler(BaseOperationHandler):
    """Handle bounding box operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "bounding_box"

    def handle(
        self,
        params: BoundingBoxOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle bounding box operation following existing implementation pattern."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Bounding Box Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        if not box:
            raise GeometryError("shapely.geometry.box is required for bounding box operation")

        valid_gdfs = []
        for layer_ident in params.layers:
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True
                )
                if not gdf.empty:
                    valid_gdfs.append(gdf)
            except GeometryError:
                continue

        if not valid_gdfs:
            return self._create_empty_result()

        target_crs = self._get_common_crs_for_layers(valid_gdfs, self.operation_type)

        overall_bounds = None
        for gdf in valid_gdfs:
            current_gdf = self._reproject_to_common_crs(gdf, target_crs, "layer", self.operation_type)

            if current_gdf.empty:
                continue

            layer_bounds = current_gdf.total_bounds

            if overall_bounds is None:
                overall_bounds = cast(tuple, layer_bounds)
            else:
                overall_bounds = (
                    min(overall_bounds[0], layer_bounds[0]),
                    min(overall_bounds[1], layer_bounds[1]),
                    max(overall_bounds[2], layer_bounds[2]),
                    max(overall_bounds[3], layer_bounds[3])
                )

        if overall_bounds is None:
            return self._create_empty_result(target_crs)

        minx, miny, maxx, maxy = overall_bounds
        if params.padding != 0:
            minx -= params.padding
            miny -= params.padding
            maxx += params.padding
            maxy += params.padding

        try:
            bbox_polygon = box(minx, miny, maxx, maxy)
            if not bbox_polygon.is_valid:
                bbox_polygon = make_valid(bbox_polygon)

            result_gdf = gpd.GeoDataFrame(geometry=[bbox_polygon], crs=target_crs)
            self._log_operation_success(self.operation_type, len(result_gdf), f"Padding: {params.padding}")
            return result_gdf

        except Exception as e:
            self._logger.error(f"Error creating bounding box: {e}", exc_info=True)
            raise GeometryError(f"Failed to create bounding box: {e}") from e


class EnvelopeHandler(BaseOperationHandler):
    """Handle envelope operation following existing pattern."""

    def __init__(self, logger_service, data_source_service):
        """Initialize with envelope service."""
        super().__init__(logger_service, data_source_service)
        self._envelope_service = EnvelopeService(logger_service)

    @property
    def operation_type(self) -> str:
        return "envelope"

    def handle(
        self,
        params: EnvelopeOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle envelope operation following existing implementation pattern."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Envelope Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        all_results = []
        valid_gdfs = []

        for layer_ident in params.layers:
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True,
                    expected_geom_types=["Polygon", "MultiPolygon"]
                )
                if not gdf.empty:
                    valid_gdfs.append(gdf)
            except GeometryError:
                continue

        if not valid_gdfs:
            return self._create_empty_result()

        target_crs = self._get_common_crs_for_layers(valid_gdfs, self.operation_type)

        for gdf in valid_gdfs:
            current_gdf = self._reproject_to_common_crs(gdf, target_crs, "layer", self.operation_type)

            for geom in current_gdf.geometry:
                if not geom or geom.is_empty or not isinstance(geom, (Polygon, MultiPolygon)):
                    continue

                geometries_to_process = []
                if isinstance(geom, MultiPolygon):
                    geometries_to_process.extend([p for p in geom.geoms if isinstance(p, Polygon)])
                else:
                    geometries_to_process.append(geom)

                for poly in geometries_to_process:
                    if not poly.is_valid:
                        poly = make_valid(poly)
                        if not isinstance(poly, Polygon) or not poly.is_valid:
                            continue

                    envelope = self._envelope_service.create_envelope_for_geometry(
                        poly, params.padding, params.min_ratio, params.cap_style
                    )
                    if envelope and envelope.is_valid:
                        all_results.append(envelope)

        if not all_results:
            return self._create_empty_result(target_crs)

        result_gdf = gpd.GeoDataFrame(geometry=all_results, crs=target_crs)
        self._log_operation_success(self.operation_type, len(result_gdf))
        return result_gdf


class OffsetCurveHandler(BaseOperationHandler):
    """Handle offset_curve operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "offset_curve"

    def handle(
        self,
        params: OffsetCurveOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle offset curve operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False,
                expected_geom_types=["LineString", "MultiLineString"]
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            result_gdf = gdf.copy()
            all_results = []
            all_attributes = []

            for index, row in result_gdf.iterrows():
                geom = row.geometry
                if not geom or geom.is_empty:
                    continue

                # Determine offset distance
                offset_distance = None
                if params.distance is not None:
                    offset_distance = params.distance
                elif params.distance_field and params.distance_field in row:
                    try:
                        offset_distance = float(row[params.distance_field])
                    except (ValueError, TypeError):
                        self._logger.warning(f"Invalid distance value in field '{params.distance_field}' at index {index}")
                        continue

                if offset_distance is None:
                    continue

                try:
                    # Convert join_style parameters
                    join_style_map = {'round': 1, 'mitre': 2, 'bevel': 3}
                    join_style_val = join_style_map.get(params.join_style, 1)  # Default to round

                    # Apply buffer with single side behavior to create offset curve
                    # For lines, buffer creates both sides, but we can use single_sided parameter
                    if hasattr(geom, 'parallel_offset'):
                        # Use parallel_offset for more precise line offsetting
                        offset_geom = geom.parallel_offset(
                            offset_distance,
                            side='left',
                            resolution=params.quad_segs,
                            join_style=join_style_val,
                            mitre_limit=params.mitre_limit
                        )
                    else:
                        # Fallback to buffer method
                        offset_geom = geom.buffer(
                            abs(offset_distance),
                            cap_style=1,  # flat
                            join_style=join_style_val,
                            mitre_limit=params.mitre_limit
                        )

                        # Extract boundary if we created a polygon from a line
                        if hasattr(offset_geom, 'boundary') and offset_geom.boundary:
                            offset_geom = offset_geom.boundary

                    if offset_geom and not offset_geom.is_empty:
                        all_results.append(offset_geom)
                        # Preserve attributes
                        attributes = row.drop('geometry').to_dict()
                        attributes['offset_distance'] = offset_distance
                        all_attributes.append(attributes)

                except Exception as e:
                    self._logger.warning(f"Failed to create offset curve for geometry at index {index}: {e}")
                    continue

            if not all_results:
                return self._create_empty_result(gdf.crs)

            result_gdf = gpd.GeoDataFrame(all_attributes, geometry=all_results, crs=gdf.crs)
            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Offset distance: {params.distance or 'field-based'}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during offset curve operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during offset curve operation on layer '{layer_name}': {e}") from e
