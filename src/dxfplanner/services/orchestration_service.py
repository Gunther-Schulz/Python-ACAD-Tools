import re # For parsing EPSG code
from typing import Optional, Any, Dict, List, Tuple, AsyncIterator
from pathlib import Path

from dxfplanner.config.schemas import AppConfig, LayerConfig, ShapefileSourceConfig, GeoJsonSourceConfig, DataSourceType # Added DataSourceType, GeoJsonSourceConfig
from dxfplanner.domain.interfaces import (
    IDxfGenerationService,
    IGeoDataReader,
    IDxfWriter,
    IGeometryTransformer,
    IValidationService,
    # ICoordinateService, # No longer directly used for default CRS in the same way
    # IAttributeMapper # Not directly used here
)
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.core.exceptions import DxfGenerationError, ConfigurationError, GeometryTransformError, DxfWriteError
from dxfplanner.domain.interfaces import AnyStrPath
from dxfplanner.services.style_service import StyleService
from dxfplanner.services.operation_service import OperationService
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

def _parse_crs_to_epsg(crs_string: Optional[str]) -> Optional[int]:
    """Parses a CRS string (e.g., 'EPSG:4326') to an integer EPSG code."""
    if not crs_string:
        return None
    match = re.match(r"^EPSG:(\d+)$", crs_string, re.IGNORECASE)
    if match:
        return int(match.group(1))
    logger.warning(f"Could not parse EPSG code from CRS string: {crs_string}")
    return None

class DxfGenerationService(IDxfGenerationService):
    """Main service orchestrating the DXF generation workflow."""

    def __init__(
        self,
        app_config: AppConfig,
        geo_data_readers: Dict[DataSourceType, IGeoDataReader], # Updated parameter
        geometry_transformer: IGeometryTransformer,
        dxf_writer: IDxfWriter,
        style_service: StyleService,
        operation_service: OperationService,
        validation_service: Optional[IValidationService] = None,
    ):
        self._app_config = app_config
        self._geo_data_readers = geo_data_readers # Storing the map
        self.geometry_transformer = geometry_transformer
        self.dxf_writer = dxf_writer
        self.style_service = style_service
        self.operation_service = operation_service
        self.validation_service = validation_service
        logger.info("DxfGenerationService initialized with reader map.")

    async def _transform_features_for_layer(
        self,
        features_iterator: AsyncIterator[GeoFeature],
        layer_name: str,
        # target_crs: Optional[str] # Changed to target_crs_epsg in IGeometryTransformer if needed, or handled by it
    ) -> AsyncIterator[AnyDxfEntity]:
        """Helper async generator to transform features and assign layer name to entities."""
        # The geometry_transformer.transform_feature_to_dxf_entities now handles CRS transformation
        # based on its own configuration or the target_crs it might receive from AppConfig if we pass it.
        # For now, assuming IGeometryTransformer is configured with a target CRS or can infer it.
        # If not, its signature might need `target_crs_epsg: int`.
        async for feature in features_iterator:
            if self.validation_service:
                # Simplified validation call if validate_geofeature is straightforward
                # validation_errors = await self.validation_service.validate_geofeature(feature)
                pass # Placeholder for re-evaluating validation service integration
            try:
                async for dxf_entity in self.geometry_transformer.transform_feature_to_dxf_entities(
                    feature=feature,
                    # target_crs=target_crs # This parameter was removed from IGeometryTransformer in a previous step, review if needed.
                                        # If the transformer needs a target CRS per call, it must be provided.
                                        # For now, assuming it uses a globally configured target CRS from its own config or AppConfig.
                ):
                    dxf_entity.layer = layer_name
                    yield dxf_entity
            except GeometryTransformError as e:
                logger.error(f"Error transforming feature in layer '{layer_name}' (ID: {getattr(feature, 'id', '(unknown)')}): {e}. Skipping.")
            except Exception as e:
                logger.error(f"Unexpected error transforming feature in '{layer_name}' (ID: {getattr(feature, 'id', '(unknown)')}): {e}. Skipping.", exc_info=True)

    async def generate_dxf_from_source(
        self,
        output_dxf_path: AnyStrPath,
        target_crs_override_str: Optional[str] = None, # Allow overriding the default target CRS
        **kwargs: Any
    ) -> None:
        logger.info(f"Starting DXF generation to '{output_dxf_path}'.")
        if not self._app_config.layers:
            logger.warning("No layers defined in AppConfig.layers. Output DXF will be empty.")

        # Determine the final target CRS for readers (must be an EPSG int)
        final_target_crs_str = target_crs_override_str or self._app_config.services.coordinate.default_target_crs
        if not final_target_crs_str:
            msg = "No default_target_crs configured in AppConfig.services.coordinate and no override provided. Cannot proceed without a target CRS for readers."
            logger.error(msg)
            raise ConfigurationError(msg)

        final_target_crs_epsg = _parse_crs_to_epsg(final_target_crs_str)
        if final_target_crs_epsg is None:
            msg = f"Could not parse a valid EPSG code from the target CRS string: '{final_target_crs_str}'. Readers require an integer EPSG code."
            logger.error(msg)
            raise ConfigurationError(msg)

        logger.info(f"Targeting EPSG:{final_target_crs_epsg} for all readers.")

        entities_for_dxf_writer: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]] = {}
        active_layers = [layer for layer in self._app_config.layers if layer.enabled]

        if not active_layers:
            logger.info("No active layers found in configuration. DXF will likely be empty.")

        for layer_cfg in active_layers:
            logger.debug(f"Processing layer: {layer_cfg.name}")
            if not layer_cfg.source:
                logger.info(f"Layer '{layer_cfg.name}' has no source defined. Skipping data reading.")
                async def empty_iterator_no_source() -> AsyncIterator[AnyDxfEntity]:
                    if False: yield
                entities_for_dxf_writer[layer_cfg.name] = (layer_cfg, empty_iterator_no_source())
                continue

            source_type = layer_cfg.source.type
            reader = self._geo_data_readers.get(source_type)

            if not reader:
                logger.warning(f"Layer '{layer_cfg.name}' has source type '{source_type}' but no reader is configured for it. Skipping.")
                async def empty_iterator_no_reader() -> AsyncIterator[AnyDxfEntity]:
                    if False: yield
                entities_for_dxf_writer[layer_cfg.name] = (layer_cfg, empty_iterator_no_reader())
                continue

            logger.debug(f"Using {type(reader).__name__} for layer '{layer_cfg.name}'.")
            features_iterator: Optional[AsyncIterator[GeoFeature]] = None
            try:
                # Note: source_config.crs is now available due to schema update
                # Readers are responsible for using it or a global default if it's None.
                features_iterator = reader.read_features(
                    source_config=layer_cfg.source,
                    target_crs_epsg=final_target_crs_epsg
                )

                # Apply operations if any are defined for the layer
                if layer_cfg.operations and features_iterator:
                    logger.debug(f"Layer '{layer_cfg.name}': Applying {len(layer_cfg.operations)} operation(s).")
                    processed_features_for_layer = self.operation_service.process_features(
                        features=features_iterator,
                        operation_configs=layer_cfg.operations
                    )
                elif features_iterator:
                    logger.debug(f"Layer '{layer_cfg.name}': No operations to apply.")
                    processed_features_for_layer = features_iterator
                else: # Should not happen if reader call was successful
                    async def empty_iterator_internal_err() -> AsyncIterator[GeoFeature]:
                        if False: yield
                    processed_features_for_layer = empty_iterator_internal_err()

            except Exception as e:
                logger.error(f"Failed to read or process source for layer '{layer_cfg.name}' from {layer_cfg.source.path if hasattr(layer_cfg.source, 'path') else 'unknown path'}: {e}", exc_info=True)
                async def empty_iterator_failed_processing() -> AsyncIterator[AnyDxfEntity]:
                    if False: yield
                entities_for_dxf_writer[layer_cfg.name] = (layer_cfg, empty_iterator_failed_processing())
                continue

            # The _transform_features_for_layer no longer takes target_crs directly.
            # It relies on the IGeometryTransformer being configured correctly.
            transformed_entities_iterator = self._transform_features_for_layer(
                features_iterator=processed_features_for_layer,
                layer_name=layer_cfg.name
            )
            entities_for_dxf_writer[layer_cfg.name] = (layer_cfg, transformed_entities_iterator)

        try:
            logger.debug(f"Passing {len(entities_for_dxf_writer)} layer groups to DxfWriter.")
            await self.dxf_writer.write_drawing(
                file_path=output_dxf_path,
                entities_by_layer_config=entities_for_dxf_writer,
            )
            logger.info(f"Successfully generated DXF file: {output_dxf_path}")
        except DxfWriteError as e:
            logger.error(f"Failed to write DXF file {output_dxf_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during DXF writing process for {output_dxf_path}: {e}", exc_info=True)
            raise DxfGenerationError(f"DXF generation failed due to an unexpected error: {e}")
