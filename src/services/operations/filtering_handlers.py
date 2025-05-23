"""Filtering operation handlers following existing patterns."""
from typing import Dict, Any, Union, List, Optional

import geopandas as gpd
import pandas as pd

from ...domain.config_models import (
    FilterByAttributeOpParams, FilterByIntersectionOpParams,
    FilterByGeometryPropertiesOpParams, CalculateOpParams
)
from ...domain.exceptions import GeometryError
from .base_operation_handler import BaseOperationHandler


class FilterByAttributeHandler(BaseOperationHandler):
    """Handle filter_by_attribute operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "filter_by_attribute"

    def handle(
        self,
        params: FilterByAttributeOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle filter by attribute operation following existing patterns."""
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

            # Apply attribute filter
            if params.column and params.column in result_gdf.columns:
                if params.keep_matching:
                    # Keep rows where column value is in the values list
                    filter_mask = result_gdf[params.column].isin(params.values)
                else:
                    # Keep rows where column value is NOT in the values list
                    filter_mask = ~result_gdf[params.column].isin(params.values)

                result_gdf = result_gdf[filter_mask].reset_index(drop=True)
            else:
                self._logger.warning(f"Column '{params.column}' not found in layer. No filtering applied.")

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Filtered by {params.column}, keep_matching: {params.keep_matching}"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during filter by attribute operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during filter by attribute operation on layer '{layer_name}': {e}") from e


class FilterByGeometryPropertiesHandler(BaseOperationHandler):
    """Handle filter_by_geometry_properties operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "filter_by_geometry_properties"

    def handle(
        self,
        params: FilterByGeometryPropertiesOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle filter by geometry properties operation following existing patterns."""
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
            filter_mask = pd.Series([True] * len(result_gdf))

            # Apply area filters
            if params.min_area is not None:
                area_mask = result_gdf.geometry.area >= params.min_area
                filter_mask = filter_mask & area_mask

            if params.max_area is not None:
                area_mask = result_gdf.geometry.area <= params.max_area
                filter_mask = filter_mask & area_mask

            # Apply geometry type filters
            if params.geometry_types:
                type_mask = pd.Series([False] * len(result_gdf))
                for geom_type in params.geometry_types:
                    if geom_type == 'polygon':
                        type_mask = type_mask | (result_gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon']))
                    elif geom_type == 'line':
                        type_mask = type_mask | (result_gdf.geometry.geom_type.isin(['LineString', 'MultiLineString']))
                    elif geom_type == 'point':
                        type_mask = type_mask | (result_gdf.geometry.geom_type.isin(['Point', 'MultiPoint']))

                filter_mask = filter_mask & type_mask

            # Apply width filters (simplified - using bounds)
            if params.min_width is not None or params.max_width is not None:
                bounds = result_gdf.bounds
                widths = bounds['maxx'] - bounds['minx']

                if params.min_width is not None:
                    width_mask = widths >= params.min_width
                    filter_mask = filter_mask & width_mask

                if params.max_width is not None:
                    width_mask = widths <= params.max_width
                    filter_mask = filter_mask & width_mask

            result_gdf = result_gdf[filter_mask].reset_index(drop=True)

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Applied geometry property filters"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during filter by geometry properties operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during filter by geometry properties operation on layer '{layer_name}': {e}") from e


class CalculateHandler(BaseOperationHandler):
    """Handle calculate operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "calculate"

    def handle(
        self,
        params: CalculateOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle calculate operation following existing patterns."""
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

            # Simple expression evaluation - for security, only allow basic operations
            # In a production system, you'd want a more sophisticated expression parser
            try:
                # Create a namespace with safe functions and the GeoDataFrame
                namespace = {
                    'gdf': result_gdf,
                    'len': len,
                    'abs': abs,
                    'round': round,
                    'min': min,
                    'max': max,
                    'sum': sum,
                }

                # Evaluate the expression
                calculated_values = eval(params.expression, {"__builtins__": {}}, namespace)

                # Add the new field
                result_gdf[params.new_field_name] = calculated_values

            except Exception as e_expr:
                self._logger.error(f"Error evaluating expression '{params.expression}': {e_expr}")
                raise GeometryError(f"Error evaluating expression '{params.expression}': {e_expr}") from e_expr

            self._log_operation_success(
                self.operation_type,
                len(result_gdf),
                f"Added field '{params.new_field_name}' with expression '{params.expression}'"
            )
            return result_gdf

        except Exception as e:
            layer_name = params.layer if isinstance(params.layer, str) else params.layer.get('name', str(params.layer))
            self._logger.error(f"Error during calculate operation on layer '{layer_name}': {e}", exc_info=True)
            raise GeometryError(f"Error during calculate operation on layer '{layer_name}': {e}") from e


# Placeholder for complex operations that need more implementation
class FilterByIntersectionHandler(BaseOperationHandler):
    """Handle filter_by_intersection operation following existing pattern."""

    @property
    def operation_type(self) -> str:
        return "filter_by_intersection"

    def handle(
        self,
        params: FilterByIntersectionOpParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle filter by intersection operation following existing patterns."""
        self._log_operation_start(self.operation_type, params)

        # This is a complex operation that needs full implementation
        self._logger.warning(f"Filter by intersection operation not fully implemented yet.")

        try:
            gdf = self._validate_and_get_source_layer(
                params.layer, source_layers, self.operation_type, allow_empty=False
            )
        except GeometryError:
            return self._create_empty_result()

        # For now, return the input layer unchanged
        result = gdf.copy() if not gdf.empty else self._create_empty_result(gdf.crs if not gdf.empty else None)
        self._log_operation_success(self.operation_type, len(result), "Placeholder implementation")
        return result
