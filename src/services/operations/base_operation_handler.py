"""Base operation handler class implementing common patterns for all geometry operations."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Union, List, Optional

import geopandas as gpd

from ...interfaces.logging_service_interface import ILoggingService
from ...interfaces.data_source_interface import IDataSource
from ...domain.config_models import BaseOperationParams
from ...domain.exceptions import GeometryError
from ...utils.geodataframe_utils import get_validated_source_gdf, reproject_gdf, get_common_crs, GdfValidationError


class BaseOperationHandler(ABC):
    """Base class for all operation handlers following the existing pattern."""

    def __init__(self, logger_service: ILoggingService, data_source_service: IDataSource):
        """Initialize with injected dependencies following existing pattern."""
        self._logger = logger_service.get_logger(self.__class__.__module__)
        self._data_source_service = data_source_service

    @property
    @abstractmethod
    def operation_type(self) -> str:
        """Return the operation type this handler processes."""
        pass

    @abstractmethod
    def handle(
        self,
        params: BaseOperationParams,
        source_layers: Dict[str, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """Handle the operation with the given parameters and source layers."""
        pass

    def _validate_and_get_source_layer(
        self,
        layer_identifier: Union[str, Dict[str, Any]],
        source_layers: Dict[str, gpd.GeoDataFrame],
        operation_name: str,
        allow_empty: bool = True,
        expected_geom_types: Optional[List[str]] = None
    ) -> gpd.GeoDataFrame:
        """Validate and retrieve a source layer following existing pattern."""
        try:
            return get_validated_source_gdf(
                layer_identifier=layer_identifier,
                source_layers=source_layers,
                allow_empty=allow_empty,
                expected_geom_types=expected_geom_types,
                context_message=f"{operation_name} source layer validation: {layer_identifier}"
            )
        except GdfValidationError as e:
            layer_name = layer_identifier if isinstance(layer_identifier, str) else layer_identifier.get('name', str(layer_identifier))
            self._logger.error(f"Failed to validate layer '{layer_name}' for {operation_name}: {e}")
            raise GeometryError(f"Layer validation failed for {operation_name} operation on layer '{layer_name}': {e}") from e

    def _get_common_crs_for_layers(
        self,
        gdfs: List[gpd.GeoDataFrame],
        operation_name: str
    ) -> Optional[Union[str, Any]]:
        """Get common CRS for multiple GeoDataFrames following existing pattern."""
        if not gdfs:
            return None

        target_crs = get_common_crs(gdfs, self._logger)
        if not target_crs and gdfs:
            # Try to get CRS from the first GDF that has one
            first_gdf_with_crs = next((gdf for gdf in gdfs if gdf.crs is not None), None)
            if first_gdf_with_crs:
                target_crs = first_gdf_with_crs.crs
                self._logger.info(f"{operation_name}: Using CRS of first valid layer with CRS: {target_crs}")
            else:
                self._logger.error(f"{operation_name}: Cannot determine a target CRS from input layers.")
                raise GeometryError(f"{operation_name} operation cannot determine a target CRS from input layers.")

        return target_crs

    def _reproject_to_common_crs(
        self,
        gdf: gpd.GeoDataFrame,
        target_crs: Union[str, Any],
        layer_name: str,
        operation_name: str
    ) -> gpd.GeoDataFrame:
        """Reproject GeoDataFrame to target CRS following existing pattern."""
        if gdf.crs and gdf.crs != target_crs:
            try:
                return reproject_gdf(
                    gdf,
                    target_crs,
                    context_message=f"{operation_name} reprojection of '{layer_name}'"
                )
            except Exception as e:
                self._logger.error(f"Failed to reproject layer '{layer_name}' to {target_crs} for {operation_name}: {e}")
                raise GeometryError(f"Failed to reproject layer '{layer_name}' for {operation_name}: {e}") from e
        elif not gdf.crs:
            gdf_copy = gdf.copy()
            gdf_copy.crs = target_crs
            self._logger.info(f"Assigned target CRS {str(target_crs)} to layer '{layer_name}' which lacked CRS.")
            return gdf_copy

        return gdf

    def _log_operation_start(self, operation_type: str, params: Any) -> None:
        """Log operation start with parameters following existing pattern."""
        self._logger.info(f"Starting {operation_type} operation")
        # Change detailed params to DEBUG level
        self._logger.debug(f"Handling {operation_type} operation with params: {params.model_dump_json(indent=2)}")

    def _log_operation_success(self, operation_type: str, feature_count: int, additional_info: str = "") -> None:
        """Log operation success following existing pattern."""
        msg = f"{operation_type.title()} operation successful. Generated {feature_count} features."
        if additional_info:
            msg += f" {additional_info}"
        # Change detailed success info to DEBUG level
        self._logger.debug(msg)

    def _create_empty_result(self, crs: Optional[Union[str, Any]] = None) -> gpd.GeoDataFrame:
        """Create empty result GeoDataFrame following existing pattern."""
        return gpd.GeoDataFrame(geometry=[], crs=crs)
