"""Data processing operation handlers following existing patterns."""
from typing import Dict, Any, Union, List, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, Polygon

from ...domain.config_models import (
    CopyOpParams, MergeOpParams, SimplifyOpParams, DissolveOpParams,
    ExplodeMultipartOpParams, RemoveIslandsOpParams, SnapToGridOpParams,
    SmoothOpParams, DifferenceByPropertyOpParams
)
from ...domain.exceptions import GeometryError
from .base_operation_handler import BaseOperationHandler


class CopyHandler(BaseOperationHandler):
    """Handle copy operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "copy"

    def handle(
        self,
        params: CopyOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle copy operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Copy Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        # For now, copy the first available layer
        for layer_ident in params.layers:
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True
                )
                if not gdf.empty:
                    result = gdf.copy()
                    self._log_operation_success(self.operation_type, len(result))
                    return result
            except GeometryError:
                continue

        self._logger.warning(f"Copy Op: No valid source layers found. Returning empty GDF.")
        return self._create_empty_result()


class MergeHandler(BaseOperationHandler):
    """Handle merge operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "merge"

    def handle(
        self,
        params: MergeOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle merge operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Merge Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

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

        if len(valid_gdfs) == 1:
            result = valid_gdfs[0].copy()
            self._log_operation_success(self.operation_type, len(result))
            return result

        # Get common CRS and merge
        target_crs = self._get_common_crs_for_layers(valid_gdfs, self.operation_type)

        merged_layers = []
        for gdf in valid_gdfs:
            reprojected_gdf = self._reproject_to_common_crs(gdf, target_crs, "merge_layer", self.operation_type)
            merged_layers.append(reprojected_gdf)

        result = pd.concat(merged_layers, ignore_index=True)
        self._log_operation_success(self.operation_type, len(result))
        return result


class SimplifyHandler(BaseOperationHandler):
    """Handle simplify operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "simplify"

    def handle(
        self,
        params: SimplifyOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle simplify operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            result_gdf = gdf.copy()
            result_gdf.geometry = result_gdf.geometry.simplify(
                tolerance=params.tolerance,
                preserve_topology=params.preserve_topology
            )

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Tolerance: {params.tolerance}, preserve_topology: {params.preserve_topology}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during simplify operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during simplify operation on layer '{layer_name}': {e}") from e


class DissolveHandler(BaseOperationHandler):
    """Handle dissolve operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "dissolve"

    def handle(
        self,
        params: DissolveOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle dissolve operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            # Perform dissolve operation
            if params.by_column:
                result_gdf = gdf.dissolve(
                    by=params.by_column,
                    aggfunc=params.agg_func,
                    as_index=params.as_index
                )
            else:
                # Dissolve all features into one
                result_gdf = gdf.dissolve()

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Dissolved by: {params.by_column or 'all features'}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during dissolve operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during dissolve operation on layer '{layer_name}': {e}") from e


class ExplodeMultipartHandler(BaseOperationHandler):
    """Handle explode_multipart operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "explode_multipart"

    def handle(
        self,
        params: ExplodeMultipartOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle explode multipart operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            # Use GeoDataFrame.explode() to explode multipart geometries
            result_gdf = gdf.explode(ignore_index=params.ignore_index)

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Exploded from {len(gdf)} to {len(result_gdf)} features"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during explode operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during explode operation on layer '{layer_name}': {e}") from e


class RemoveIslandsHandler(BaseOperationHandler):
    """Handle remove_islands operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "remove_islands"

    def handle(
        self,
        params: RemoveIslandsOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle remove islands operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            result_gdf = gdf.copy()

            # Process each geometry to remove holes/islands
            for idx, geom in enumerate(result_gdf.geometry):
                if isinstance(geom, Polygon) and geom.interiors:
                    if not params.preserve_islands:
                        # Remove all holes (islands)
                        result_gdf.loc[idx, 'geometry'] = Polygon(geom.exterior)
                    # If preserve_islands is True, keep the geometry as-is

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Preserve islands: {params.preserve_islands}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during remove islands operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during remove islands operation on layer '{layer_name}': {e}") from e


class SnapToGridHandler(BaseOperationHandler):
    """Handle snap_to_grid operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "snap_to_grid"

    def handle(
        self,
        params: SnapToGridOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle snap to grid operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            from shapely.affinity import affine_transform
            import math

            result_gdf = gdf.copy()
            grid_size = params.grid_size

            def snap_coordinate(coord):
                """Snap a coordinate to the nearest grid point."""
                return round(coord / grid_size) * grid_size

            def snap_geometry(geom):
                """Snap geometry coordinates to grid."""
                if geom is None or geom.is_empty:
                    return geom

                # Get coordinates and snap them
                if hasattr(geom, 'coords'):
                    # Point, LineString
                    snapped_coords = [(snap_coordinate(x), snap_coordinate(y)) for x, y in geom.coords]
                    return type(geom)(snapped_coords)
                elif hasattr(geom, 'exterior'):
                    # Polygon
                    exterior_coords = [(snap_coordinate(x), snap_coordinate(y)) for x, y in geom.exterior.coords]
                    interior_coords = []
                    for interior in geom.interiors:
                        interior_coords.append([(snap_coordinate(x), snap_coordinate(y)) for x, y in interior.coords])
                    return Polygon(exterior_coords, interior_coords)
                else:
                    # MultiGeometry - not implemented
                    self._logger.warning(f"Snap to grid not implemented for geometry type: {type(geom)}")
                    return geom

            # Apply snapping to all geometries
            result_gdf.geometry = result_gdf.geometry.apply(snap_geometry)

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Grid size: {grid_size}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during snap to grid operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during snap to grid operation on layer '{layer_name}': {e}") from e


class SmoothHandler(BaseOperationHandler):
    """Handle smooth operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "smooth"

    def handle(
        self,
        params: SmoothOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle smooth operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            return self._create_empty_result(gdf.crs)

        try:
            result_gdf = gdf.copy()

            def smooth_geometry(geom):
                """Smooth a geometry using simplification and buffering."""
                if geom is None or geom.is_empty:
                    return geom

                try:
                    # Simplify the geometry first
                    smoothed = geom.simplify(params.strength, preserve_topology=True)

                    # Ensure the smoothed geometry does not expand beyond the original geometry
                    if not geom.contains(smoothed):
                        smoothed = geom.intersection(smoothed)

                    # Apply small buffer operations for smoother curves on polygons
                    if isinstance(smoothed, (Polygon, MultiPolygon)):
                        buffer_distance = params.strength * 0.01
                        smoothed = smoothed.buffer(buffer_distance).buffer(-buffer_distance)

                    # Final containment check
                    if smoothed and not geom.contains(smoothed):
                        smoothed = geom.intersection(smoothed)

                    return smoothed if smoothed and not smoothed.is_empty else geom

                except Exception as e:
                    self._logger.warning(f"Failed to smooth geometry: {e}")
                    return geom

            # Apply smoothing to all geometries
            result_gdf.geometry = result_gdf.geometry.apply(smooth_geometry)

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Strength: {params.strength}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during smooth operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during smooth operation on layer '{layer_name}': {e}") from e


class DifferenceByPropertyHandler(BaseOperationHandler):
    """Handle difference_by_property operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "difference_by_property"

    def handle(
        self,
        params: DifferenceByPropertyOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle difference by property operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            # Get main layer and difference layer
            main_gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
            diff_gdf = self._validate_and_get_source_layer(
                params.difference_layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if main_gdf.empty:
            return self._create_empty_result(main_gdf.crs)

        if diff_gdf.empty:
            self._logger.warning(f"Difference layer is empty, returning main layer unchanged")
            return main_gdf.copy()

        # Get common CRS and reproject
        target_crs = self._get_common_crs_for_layers([main_gdf, diff_gdf], self.operation_type)
        main_gdf = self._reproject_to_common_crs(main_gdf, target_crs, "main_layer", self.operation_type)
        diff_gdf = self._reproject_to_common_crs(diff_gdf, target_crs, "difference_layer", self.operation_type)

        # Check if required properties exist
        if params.main_layer_property not in main_gdf.columns:
            self._logger.error(f"Property '{params.main_layer_property}' not found in main layer")
            raise GeometryError(f"Property '{params.main_layer_property}' not found in main layer")

        if params.difference_layer_property not in diff_gdf.columns:
            self._logger.error(f"Property '{params.difference_layer_property}' not found in difference layer")
            raise GeometryError(f"Property '{params.difference_layer_property}' not found in difference layer")

        try:
            result_features = []

            for main_idx, main_row in main_gdf.iterrows():
                main_prop_value = main_row[params.main_layer_property]
                main_geom = main_row.geometry

                # Find matching difference features by property
                matching_diff_features = diff_gdf[
                    diff_gdf[params.difference_layer_property] == main_prop_value
                ]

                if matching_diff_features.empty:
                    # No matching difference features
                    if params.on_no_match_in_diff == "keep_main_feature":
                        result_features.append(main_row)
                    elif params.on_no_match_in_diff == "empty_main_geometry":
                        main_row_copy = main_row.copy()
                        main_row_copy.geometry = None
                        result_features.append(main_row_copy)
                    # "remove_main_feature" means we don't add it to results
                    continue

                # Perform difference operation with matching features
                try:
                    # Union all matching difference geometries
                    diff_union = matching_diff_features.geometry.unary_union

                    # Perform difference
                    result_geom = main_geom.difference(diff_union)

                    if result_geom.is_empty:
                        if params.on_difference_error == "keep_main_feature":
                            result_features.append(main_row)
                        elif params.on_difference_error == "empty_main_geometry":
                            main_row_copy = main_row.copy()
                            main_row_copy.geometry = None
                            result_features.append(main_row_copy)
                        # "remove_main_feature" means we don't add it
                    else:
                        # Successfully created difference geometry
                        main_row_copy = main_row.copy()
                        main_row_copy.geometry = result_geom
                        result_features.append(main_row_copy)

                except Exception as e:
                    self._logger.warning(f"Error performing difference for feature {main_idx}: {e}")

                    if params.on_difference_error == "keep_main_feature":
                        result_features.append(main_row)
                    elif params.on_difference_error == "empty_main_geometry":
                        main_row_copy = main_row.copy()
                        main_row_copy.geometry = None
                        result_features.append(main_row_copy)
                    # "remove_main_feature" means we don't add it

            if not result_features:
                return self._create_empty_result(target_crs)

            result_gdf = gpd.GeoDataFrame(result_features, crs=target_crs)
            # Remove features with None geometry
            result_gdf = result_gdf[result_gdf.geometry.notna()]

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Property-based difference: {params.main_layer_property} vs {params.difference_layer_property}"
            )
            return result_gdf

        except Exception as e:
            self._logger.error(f"Error during difference by property operation: {e}", exc_info=True)
            raise GeometryError(f"Error during difference by property operation: {e}") from e
