"""Transformation operation handlers following existing patterns."""
from typing import Dict, Any, Union, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import Point
from shapely import affinity

from ...domain.config_models import TranslateOpParams, RotateOpParams, ScaleOpParams
from ...domain.exceptions import GeometryError
from .base_operation_handler import BaseOperationHandler


class TranslateHandler(BaseOperationHandler):
    """Handle translate operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "translate"

    def handle(
        self,
        params: TranslateOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle translate operation following existing implementation pattern."""
        self._log_operation_start(self.operation_type, params)

        if not params.layers:
            self._logger.warning(f"Translate Op: No source layers specified. Returning empty GDF.")
            return self._create_empty_result()

        current_gdf = None
        for layer_ident in params.layers:
            try:
                gdf = self._validate_and_get_source_layer(
                    layer_ident, source_layers, self.operation_type, allow_empty=True
                )
                if not gdf.empty:
                    current_gdf = gdf
                    break
            except GeometryError:
                # Continue to next layer if validation fails
                continue

        if current_gdf is None:
            self._logger.warning(f"Translate Op: No valid source layers found after validation. Returning empty GDF.")
            return self._create_empty_result()

        try:
            # Apply translation using the correct field names following existing pattern
            translated_gdf = current_gdf.copy()
            translated_gdf.geometry = translated_gdf.geometry.translate(xoff=params.dx, yoff=params.dy)

            self._log_operation_success(
                self.operation_type,
                len(translated_gdf),
                f"Translated by dx={params.dx}, dy={params.dy}"
            )
            return translated_gdf

        except Exception as e:
            layer_names = [str(l) for l in params.layers]
            self._logger.error(f"Error during translate operation on layers {layer_names}: {e}", exc_info=True)
            raise GeometryError(f"Error during translate operation on layers {layer_names}: {e}") from e


class RotateHandler(BaseOperationHandler):
    """Handle rotate operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "rotate"

    def handle(
        self,
        params: RotateOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle rotate operation using shapely.affinity.rotate following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            self._logger.warning(f"Rotate Op: Source layer is empty. Returning empty GDF.")
            return self._create_empty_result(gdf.crs)

        try:
            result_gdf = gdf.copy()

            # Determine rotation origin following existing pattern
            if params.origin_type == 'point':
                if not params.origin_coords:
                    raise GeometryError("origin_coords must be provided when origin_type is 'point'")
                origin = Point(params.origin_coords)
            elif params.origin_type == 'centroid':
                # Use centroid of all geometries
                total_bounds = gdf.total_bounds
                origin = Point((total_bounds[0] + total_bounds[2]) / 2, (total_bounds[1] + total_bounds[3]) / 2)
            else:  # 'center' - use center of bounding box
                total_bounds = gdf.total_bounds
                origin = Point((total_bounds[0] + total_bounds[2]) / 2, (total_bounds[1] + total_bounds[3]) / 2)

            # Apply rotation using shapely.affinity.rotate
            result_gdf.geometry = result_gdf.geometry.apply(
                lambda geom: affinity.rotate(geom, params.angle, origin=origin, use_radians=False)
            )

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Rotated by {params.angle}° around {params.origin_type}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during rotate operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during rotate operation on layer '{layer_name}': {e}") from e


class ScaleHandler(BaseOperationHandler):
    """Handle scale operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "scale"

    def handle(
        self,
        params: ScaleOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle scale operation using shapely.affinity.scale following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        if gdf.empty:
            self._logger.warning(f"Scale Op: Source layer is empty. Returning empty GDF.")
            return self._create_empty_result(gdf.crs)

        try:
            result_gdf = gdf.copy()

            # Determine scaling origin following existing pattern
            if params.origin_type == 'point':
                if not params.origin_coords:
                    raise GeometryError("origin_coords must be provided when origin_type is 'point'")
                origin = Point(params.origin_coords)
            elif params.origin_type == 'centroid':
                # Use centroid of all geometries
                total_bounds = gdf.total_bounds
                origin = Point((total_bounds[0] + total_bounds[2]) / 2, (total_bounds[1] + total_bounds[3]) / 2)
            else:  # 'center' - use center of bounding box
                total_bounds = gdf.total_bounds
                origin = Point((total_bounds[0] + total_bounds[2]) / 2, (total_bounds[1] + total_bounds[3]) / 2)

            # Apply scaling using shapely.affinity.scale
            result_gdf.geometry = result_gdf.geometry.apply(
                lambda geom: affinity.scale(
                    geom,
                    xfact=params.xfact,
                    yfact=params.yfact,
                    zfact=params.zfact,  # Will be ignored for 2D geometries
                    origin=origin
                )
            )

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Scaled by factors (x={params.xfact}, y={params.yfact}, z={params.zfact}) around {params.origin_type}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during scale operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during scale operation on layer '{layer_name}': {e}") from e
