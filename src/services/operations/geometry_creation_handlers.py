"""Geometry creation operation handlers following existing patterns."""
from typing import Dict, Any, Union, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, MultiPoint, LineString
from shapely.validation import make_valid
from scipy.spatial.distance import cdist

from ...domain.config_models import CreateCirclesOpParams, ConnectPointsOpParams
from ...domain.exceptions import GeometryError
from .base_operation_handler import BaseOperationHandler


class CreateCirclesHandler(BaseOperationHandler):
    """Handle create_circles operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "create_circles"

    def handle(
        self,
        params: CreateCirclesOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle create circles operation following existing implementation pattern."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Create Circles Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        all_created_circles = []
        all_attributes = []
        valid_input_gdfs = []
        processed_layer_names = []

        # Collect valid input GDFs
        for layer_ident_idx, layer_ident in enumerate(params.layers):
            log_layer_ident = layer_ident if isinstance(layer_ident, str) else layer_ident.get('name', f"layer_at_index_{layer_ident_idx}")
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True,
                    expected_geom_types=["Point"]
                )
                if not gdf.empty:
                    gdf.attrs['original_layer_identifier'] = log_layer_ident
                    valid_input_gdfs.append(gdf)
                    processed_layer_names.append(log_layer_ident)
            except GeometryError:
                continue

        if not valid_input_gdfs:
            self._logger.warning(f"Create Circles Op: No valid source layers with points found. Returning empty GDF.")
            return self._create_empty_result()

        target_crs = self._get_common_crs_for_layers(valid_input_gdfs, self.operation_type)

        # Process each valid GDF
        for gdf_validated in valid_input_gdfs:
            original_layer_name = gdf_validated.attrs.get('original_layer_identifier', 'unknown_layer')
            current_gdf = self._reproject_to_common_crs(gdf_validated, target_crs, original_layer_name, self.operation_type)

            for index, row in current_gdf.iterrows():
                point_geom = row.geometry
                if not isinstance(point_geom, Point) or point_geom.is_empty:
                    self._logger.debug(f"Skipping non-Point or empty geometry at index {index} in layer '{original_layer_name}'.")
                    continue

                # Determine radius
                radius_val = None
                if params.radius is not None:  # Fixed radius
                    radius_val = params.radius
                elif params.radius_field:
                    if params.radius_field not in row:
                        self._logger.warning(f"Radius field '{params.radius_field}' not found in attributes for point at index {index} in layer '{original_layer_name}'. Skipping.")
                        continue
                    try:
                        field_val = row[params.radius_field]
                        if field_val is None:
                            self._logger.warning(f"Radius field '{params.radius_field}' has None value for point at index {index}, layer '{original_layer_name}'. Skipping.")
                            continue
                        radius_val = float(field_val)
                    except (ValueError, TypeError) as e_conv:
                        self._logger.warning(f"Could not convert radius value '{row[params.radius_field]}' from field '{params.radius_field}' to float for point at index {index}, layer '{original_layer_name}': {e_conv}. Skipping.")
                        continue

                if radius_val is None or radius_val <= 0:
                    self._logger.warning(f"Invalid radius value '{radius_val}' for point at index {index}, layer '{original_layer_name}'. Skipping circle creation.")
                    continue

                try:
                    circle_poly = point_geom.buffer(radius_val)
                    if not circle_poly.is_valid:
                        self._logger.warning(f"Created circle for point at index {index}, layer '{original_layer_name}' is invalid. Attempting make_valid.")
                        circle_poly = make_valid(circle_poly)
                        if not circle_poly.is_valid:
                            self._logger.error(f"Circle remains invalid after make_valid for point at index {index}, layer '{original_layer_name}'. Skipping.")
                            continue

                    all_created_circles.append(circle_poly)
                    # Preserve attributes from the source point
                    attributes = row.drop('geometry').to_dict()
                    attributes['source_layer'] = original_layer_name
                    attributes['original_index'] = index
                    attributes['radius'] = radius_val
                    all_attributes.append(attributes)

                except Exception as e_buffer:
                    self._logger.error(f"Error creating circle buffer for point at index {index}, layer '{original_layer_name}' with radius {radius_val}: {e_buffer}", exc_info=True)
                    continue

        if not all_created_circles:
            self._logger.warning(f"Create Circles Op: No circles were generated from any source layers. Returning empty GDF.")
            return self._create_empty_result(target_crs)

        try:
            result_gdf = gpd.GeoDataFrame(all_attributes, geometry=all_created_circles, crs=target_crs)
            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Generated from layers: {', '.join(processed_layer_names)}"
            )
            return result_gdf
        except Exception as e_gdf_create:
            self._logger.error(f"Error creating final GeoDataFrame for {self.operation_type}: {e_gdf_create}", exc_info=True)
            raise GeometryError(f"Failed to create result GeoDataFrame for {self.operation_type}: {e_gdf_create}")


class ConnectPointsHandler(BaseOperationHandler):
    """Handle connect_points operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "connect_points"

    def handle(
        self,
        params: ConnectPointsOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle connect points operation following existing implementation pattern."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Connect Points Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        all_points_coords = []
        valid_input_gdfs = []
        processed_layer_names = []

        # Collect all valid input GDFs and extract points
        for layer_ident_idx, layer_ident in enumerate(params.layers):
            log_layer_ident = layer_ident if isinstance(layer_ident, str) else layer_ident.get('name', f"layer_at_index_{layer_ident_idx}")
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True,
                    expected_geom_types=["Point", "MultiPoint"]
                )
                if not gdf.empty:
                    gdf.attrs['original_layer_identifier'] = log_layer_ident
                    valid_input_gdfs.append(gdf)
                    processed_layer_names.append(log_layer_ident)

                    # Extract points
                    for geom in gdf.geometry:
                        if isinstance(geom, Point):
                            all_points_coords.append((geom.x, geom.y))
                        elif isinstance(geom, MultiPoint):
                            for p_geom in geom.geoms:
                                if isinstance(p_geom, Point):
                                    all_points_coords.append((p_geom.x, p_geom.y))
            except GeometryError:
                continue

        if not valid_input_gdfs:
            self._logger.warning(f"Connect Points Op: No valid source layers with points found. Returning empty GDF.")
            return self._create_empty_result()

        target_crs = self._get_common_crs_for_layers(valid_input_gdfs, self.operation_type)

        # Remove duplicate points and sort for consistent ordering
        unique_points_list = sorted(list(set(all_points_coords)))

        if not unique_points_list:
            self._logger.warning(f"Connect Points Op: No unique points found to connect. Layers processed: {', '.join(processed_layer_names)}.")
            return self._create_empty_result(target_crs)

        if len(unique_points_list) == 1:
            self._logger.warning(f"Connect Points Op: Only one unique point found. Cannot create connecting line.")
            return self._create_empty_result(target_crs)

        points_array = np.array(unique_points_list)
        lines = []

        try:
            if params.max_distance is not None:
                # Group points within max_distance and create lines for each group
                self._logger.info(f"Connect Points Op: Grouping points with max_distance: {params.max_distance}")
                groups_indices = self._group_points_by_distance(points_array, params.max_distance)

                for group_indices in groups_indices:
                    if len(group_indices) > 1:
                        group_points_coords = points_array[group_indices]
                        path_indices = self._create_nearest_neighbor_path(group_points_coords)
                        connected_points_coords = [tuple(coord) for coord in group_points_coords[path_indices]]
                        lines.append(LineString(connected_points_coords))
                    else:
                        self._logger.debug(f"Connect Points Op: Group with single point found. Skipping line creation for this group.")
            else:
                # Connect all points into a single line
                self._logger.info(f"Connect Points Op: Connecting all {len(points_array)} unique points into a single line.")
                path_indices = self._create_nearest_neighbor_path(points_array)
                connected_all_points_coords = [tuple(coord) for coord in points_array[path_indices]]
                lines.append(LineString(connected_all_points_coords))

        except Exception as e:
            self._logger.error(f"Error during point connection: {e}", exc_info=True)
            raise GeometryError(f"Error during point connection: {e}") from e

        if not lines:
            self._logger.warning(f"Connect Points Op: No lines were created. Layers processed: {', '.join(processed_layer_names)}.")
            return self._create_empty_result(target_crs)

        result_gdf = gpd.GeoDataFrame(geometry=lines, crs=target_crs)
        self._log_operation_success(self.operation_type, len(result_gdf), f"Created from {len(unique_points_list)} unique points")
        return result_gdf

    def _group_points_by_distance(self, points_array: np.ndarray, max_distance: float) -> List[List[int]]:
        """Group points by maximum distance following existing pattern."""
        groups_indices = []
        remaining_indices = list(range(len(points_array)))

        while remaining_indices:
            current_group_indices = [remaining_indices.pop(0)]

            # Iteratively add points to current group
            group_changed = True
            while group_changed:
                group_changed = False
                newly_added = []

                current_group_coords = points_array[current_group_indices]
                temp_remaining = []

                for rem_idx in remaining_indices:
                    point_coords = points_array[rem_idx].reshape(1, -1)
                    distances = cdist(point_coords, current_group_coords)

                    if np.min(distances) <= max_distance:
                        newly_added.append(rem_idx)
                        group_changed = True
                    else:
                        temp_remaining.append(rem_idx)

                if newly_added:
                    current_group_indices.extend(newly_added)
                remaining_indices = temp_remaining

            groups_indices.append(current_group_indices)

        return groups_indices

    def _create_nearest_neighbor_path(self, points_coords: np.ndarray) -> List[int]:
        """Create nearest neighbor path through points following existing pattern."""
        if len(points_coords) <= 1:
            return list(range(len(points_coords)))

        path_indices = [0]  # Start with first point
        remaining_indices = list(range(1, len(points_coords)))

        while remaining_indices:
            current_end_idx = path_indices[-1]
            current_end_coords = points_coords[current_end_idx].reshape(1, -1)

            remaining_coords = points_coords[remaining_indices]
            distances = cdist(current_end_coords, remaining_coords)[0]
            nearest_temp_idx = np.argmin(distances)

            actual_next_idx = remaining_indices.pop(nearest_temp_idx)
            path_indices.append(actual_next_idx)

        return path_indices
