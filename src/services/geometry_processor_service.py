"""Refactored GeometryProcessorService following Single Responsibility Principle."""
import os
from typing import List, Optional, Any, Dict, Union

import geopandas as gpd

from ..interfaces.geometry_processor_interface import IGeometryProcessor
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.data_source_interface import IDataSource
from ..domain.config_models import (
    AllOperationParams,
    GeomLayerDefinition,
    StyleConfig
)
from ..domain.exceptions import GeometryError, DXFProcessingError
from .operations.operation_registry import OperationRegistry
from .resource_manager_service import ResourceManagerService

# Attempt ezdxf import
try:
    import ezdxf
    from ezdxf.document import Drawing
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None)
    EZDXF_AVAILABLE = False


class GeometryProcessorService(IGeometryProcessor):
    """
    Refactored GeometryProcessorService following Single Responsibility Principle.

    Responsibilities:
    - Coordinate operation execution via registry
    - Manage layer creation and merging
    - Handle CRS transformations
    - Provide interface implementation
    """

    def __init__(self, logger_service: ILoggingService, data_source_service: IDataSource):
        """Initialize with injected dependencies following existing pattern."""
        self._logger = logger_service.get_logger(__name__)
        self._data_source_service = data_source_service

        # Initialize operation registry and resource manager
        self._operation_registry = OperationRegistry(logger_service, data_source_service)
        self._resource_manager = ResourceManagerService(logger_service)

        self._logger.info("GeometryProcessorService initialized with operation registry and resource management")

    def apply_operation(
        self,
        operation_params: AllOperationParams,
        source_layers: Dict[str, gpd.GeoDataFrame],
    ) -> gpd.GeoDataFrame:
        """Apply operation using the operation registry following existing pattern."""
        operation_type = operation_params.type
        self._logger.debug(f"Applying operation: {operation_type}")

        with self._resource_manager.memory_managed_operation(f"operation_{operation_type}"):
            try:
                # Execute operation via registry
                result_gdf = self._operation_registry.execute_operation(
                    operation_type, operation_params, source_layers
                )

                if result_gdf is not None:
                    # Register result for memory tracking and optimize
                    result_gdf = self._resource_manager.register_geodataframe(result_gdf)
                    result_gdf = self._resource_manager.optimize_geodataframe_memory(result_gdf)

                return result_gdf

            except Exception as e:
                self._logger.error(f"Failed to apply operation {operation_type}: {e}", exc_info=True)
                raise GeometryError(f"Failed to apply operation {operation_type}: {e}") from e

    def create_layer_from_definition(
        self,
        layer_def: GeomLayerDefinition,
        dxf_drawing: Optional[Drawing],
        style_config: StyleConfig,
        base_crs: str,
        project_root: Optional[str] = None
    ) -> Optional[gpd.GeoDataFrame]:
        """Create layer from definition with proper resource management following existing pattern."""
        self._logger.debug(f"Creating layer '{layer_def.name}' from definition")

        with self._resource_manager.memory_managed_operation(f"create_layer_{layer_def.name}"):
            try:
                base_gdf = None

                # Handle GeoJSON file source
                if layer_def.geojson_file:
                    geojson_path = layer_def.geojson_file

                    # Resolve path relative to project directory if project_root is provided
                    if project_root and not os.path.isabs(geojson_path):
                        geojson_path = os.path.join(project_root, geojson_path)
                        geojson_path = os.path.normpath(geojson_path)

                    self._logger.debug(f"Loading GeoJSON file: {geojson_path}")
                    base_gdf = self._data_source_service.load_geojson_file(geojson_path)

                    # Apply selectByProperties filtering if specified
                    if layer_def.select_by_properties:
                        base_gdf = self._apply_property_filter(base_gdf, layer_def.select_by_properties, layer_def.name)

                # Handle DXF layer extraction (placeholder - would need full implementation)
                elif layer_def.dxf_layer and dxf_drawing:
                    self._logger.warning(f"DXF layer extraction not fully implemented for layer '{layer_def.name}'")
                    base_gdf = gpd.GeoDataFrame(geometry=[], crs=base_crs)

                # Handle shapefile source (placeholder)
                elif layer_def.shape_file:
                    self._logger.warning(f"Shapefile loading not implemented for layer '{layer_def.name}'")
                    base_gdf = gpd.GeoDataFrame(geometry=[], crs=base_crs)

                # Check if we have operations to process (including operations-only layers)
                if layer_def.operations:
                    # If we have a base GDF from a data source, use it; otherwise None indicates operations-only layer
                    result_gdf = base_gdf  # This could be None for operations-only layers

                    for operation_params in layer_def.operations:
                        self._logger.debug(f"Processing operation '{operation_params.type}' for layer '{layer_def.name}'")

                        # For operations-only layers, the source_layers dict needs to be populated from previous operations
                        # This will be handled by the orchestrator service that maintains all processed layers
                        # For now, we'll return None to indicate this layer needs operation processing
                        if base_gdf is None:
                            self._logger.debug(f"Layer '{layer_def.name}' is operations-only - will be processed by orchestrator")
                            return None

                        # If we have a base GDF, we would process operations here in a full implementation
                        # For now, just use the base GDF
                        result_gdf = base_gdf

                    # Set CRS and register the result
                    if result_gdf is not None:
                        result_gdf = self._ensure_layer_crs(result_gdf, base_crs, layer_def.name)
                        result_gdf = self._resource_manager.register_geodataframe(result_gdf)
                        result_gdf = self._resource_manager.optimize_geodataframe_memory(result_gdf)

                    return result_gdf

                # If we have a base GDF but no operations, just return the base
                elif base_gdf is not None:
                    # Set CRS if not present
                    base_gdf = self._ensure_layer_crs(base_gdf, base_crs, layer_def.name)

                    # Register and optimize the result
                    base_gdf = self._resource_manager.register_geodataframe(base_gdf)
                    base_gdf = self._resource_manager.optimize_geodataframe_memory(base_gdf)

                    return base_gdf

                else:
                    self._logger.warning(f"No valid data source or operations found for layer '{layer_def.name}'")
                    return None

            except Exception as e:
                self._logger.error(f"Failed to create layer '{layer_def.name}': {e}", exc_info=True)
                raise GeometryError(f"Failed to create layer '{layer_def.name}': {e}") from e

    def merge_layers(
        self,
        layers_to_merge: List[gpd.GeoDataFrame],
        target_crs: Optional[str] = None
    ) -> gpd.GeoDataFrame:
        """Merge layers with proper resource management following existing pattern."""
        if not layers_to_merge:
            return gpd.GeoDataFrame(geometry=[])

        if len(layers_to_merge) == 1:
            result = self._resource_manager.copy_geodataframe_safely(layers_to_merge[0], "merge_single_layer")
            return self._resource_manager.optimize_geodataframe_memory(result)

        with self._resource_manager.memory_managed_operation("merge_layers"):
            try:
                # Use first layer's CRS if target_crs not specified
                if target_crs is None:
                    target_crs = str(layers_to_merge[0].crs)

                merged_layers = []
                for i, gdf in enumerate(layers_to_merge):
                    # Create safe copy
                    gdf_copy = self._resource_manager.copy_geodataframe_safely(gdf, f"merge_layer_{i}")

                    # Reproject if necessary
                    if gdf_copy.crs and str(gdf_copy.crs) != target_crs:
                        gdf_copy = gdf_copy.to_crs(target_crs)

                    merged_layers.append(gdf_copy)

                # Concatenate all layers
                result = gpd.concat(merged_layers, ignore_index=True)

                # Register and optimize result
                result = self._resource_manager.register_geodataframe(result)
                result = self._resource_manager.optimize_geodataframe_memory(result)

                return result

            except Exception as e:
                self._logger.error(f"Failed to merge layers: {e}", exc_info=True)
                raise GeometryError(f"Failed to merge layers: {e}") from e

    def reproject_layer(self, layer: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        """Reproject layer with proper resource management following existing pattern."""
        with self._resource_manager.memory_managed_operation("reproject_layer"):
            try:
                if layer.crs and str(layer.crs) != target_crs:
                    # Create safe copy before reprojection
                    layer_copy = self._resource_manager.copy_geodataframe_safely(layer, "reproject")
                    result = layer_copy.to_crs(target_crs)

                    # Register and optimize result
                    result = self._resource_manager.register_geodataframe(result)
                    result = self._resource_manager.optimize_geodataframe_memory(result)

                    return result
                else:
                    # No reprojection needed, return safe copy
                    result = self._resource_manager.copy_geodataframe_safely(layer, "reproject_no_change")
                    return self._resource_manager.optimize_geodataframe_memory(result)

            except Exception as e:
                self._logger.error(f"Failed to reproject layer: {e}", exc_info=True)
                raise GeometryError(f"Failed to reproject layer: {e}") from e

    def get_supported_operations(self) -> List[str]:
        """Get list of supported operations from registry following existing pattern."""
        return self._operation_registry.get_supported_operations()

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get memory usage statistics following existing pattern."""
        return self._resource_manager.get_memory_statistics()

    def cleanup_resources(self) -> None:
        """Clean up all managed resources following existing pattern."""
        self._resource_manager.cleanup_all_resources()

    def _apply_property_filter(
        self,
        gdf: gpd.GeoDataFrame,
        filter_properties: Dict[str, Any],
        layer_name: str
    ) -> gpd.GeoDataFrame:
        """Apply property-based filtering following existing pattern."""
        self._logger.debug(f"Applying selectByProperties filter: {filter_properties}")
        original_count = len(gdf)

        # Create filter mask based on all property conditions
        import pandas as pd
        filter_mask = pd.Series([True] * len(gdf))

        for prop_name, prop_value in filter_properties.items():
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
        filtered_gdf = gdf[filter_mask].reset_index(drop=True)
        filtered_count = len(filtered_gdf)

        self._logger.info(f"Filtered layer '{layer_name}': {original_count} -> {filtered_count} features")

        if filtered_count == 0:
            self._logger.warning(f"No features match the selectByProperties filter for layer '{layer_name}'")

        return filtered_gdf

    def _ensure_layer_crs(self, gdf: gpd.GeoDataFrame, base_crs: str, layer_name: str) -> gpd.GeoDataFrame:
        """Ensure layer has proper CRS following existing pattern."""
        if gdf.crs is None:
            gdf.crs = base_crs
            self._logger.debug(f"Assigned base CRS {base_crs} to layer '{layer_name}'")
        elif str(gdf.crs) != base_crs:
            self._logger.debug(f"Reprojecting layer '{layer_name}' from {gdf.crs} to {base_crs}")
            gdf = gdf.to_crs(base_crs)

        return gdf

    def __del__(self):
        """Ensure cleanup on destruction following existing pattern."""
        try:
            self.cleanup_resources()
        except:
            pass  # Suppress errors in destructor
