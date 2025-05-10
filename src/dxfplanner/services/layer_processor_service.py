"""
Service responsible for processing a single layer configuration.
This includes reading data, applying operations, and transforming to DXF entities.
"""
from typing import AsyncIterator, Optional, Dict, Any
from logging import Logger

from dxfplanner.config import AppConfig, LayerConfig, AnySourceConfig, ShapefileSourceConfig # Add other source configs as needed
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IGeoDataReader, IOperation, IGeometryTransformer
from dxfplanner.core.di import DIContainer # For resolving dependencies
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError

class LayerProcessorService:
    """Processes a single layer from configuration to an async stream of DXF entities."""

    def __init__(
        self,
        app_config: AppConfig,
        di_container: DIContainer,
        geometry_transformer: IGeometryTransformer,
        logger: Logger
    ):
        self.app_config = app_config
        self.di_container = di_container
        self.geometry_transformer = geometry_transformer
        self.logger = logger
        self.logger.info("LayerProcessorService initialized.")

    async def process_layer(
        self,
        layer_config: LayerConfig,
        # global_target_crs: Optional[str] # This might be better handled by ensuring a ReprojectOperation is in the stack if needed
    ) -> AsyncIterator[AnyDxfEntity]:
        """
        Processes a single layer configuration.

        Args:
            layer_config: The configuration for the layer to process.
            # global_target_crs: The overall target CRS for the DXF document, used for final validation/transformation if necessary.

        Yields:
            AnyDxfEntity: An asynchronous iterator of DXF entities generated for this layer.
        """
        self.logger.info(f"Processing layer: {layer_config.name}")

        if not layer_config.enabled:
            self.logger.info(f"Layer '{layer_config.name}' is disabled. Skipping.")
            return

        features_stream: Optional[AsyncIterator[GeoFeature]] = None

        if layer_config.source:
            source_conf: AnySourceConfig = layer_config.source
            self.logger.debug(f"Layer '{layer_config.name}' has source type: {source_conf.type}")
            try:
                reader = self.di_container.resolve_reader(source_conf.type)
            except ConfigurationError as e:
                self.logger.error(f"Could not resolve reader for source type '{source_conf.type}' in layer '{layer_config.name}': {e}")
                # Optionally re-raise or simply yield nothing for this layer
                return

            reader_kwargs: Dict[str, Any] = {}
            # Extract reader-specific kwargs from the source_conf
            # This needs to be robust to different source_conf types
            if isinstance(source_conf, ShapefileSourceConfig):
                if source_conf.encoding:
                    reader_kwargs['encoding'] = source_conf.encoding
                # source_conf.crs is passed as source_crs directly to read_features
                # source_conf.path is passed as source_path directly to read_features
            # Add elif for CsvWktSourceConfig, GeoJsonSourceConfig etc. to extract their specific kwargs
            # e.g., elif isinstance(source_conf, CsvWktSourceConfig): reader_kwargs['wkt_column'] = source_conf.wkt_column ...

            try:
                features_stream = reader.read_features(
                    source_path=source_conf.path,
                    source_crs=getattr(source_conf, 'crs', None), # Common field, but might not exist on all
                    target_crs=None, # Initial read does not force reprojection; operations handle it
                    **reader_kwargs
                )
            except GeoDataReadError as e:
                self.logger.error(f"Error reading data for layer '{layer_config.name}' from source '{source_conf.path}': {e}")
                return # Stop processing this layer if data read fails
            except Exception as e_read_generic:
                self.logger.error(f"Unexpected error during data read for layer '{layer_config.name}': {e_read_generic}", exc_info=True)
                return
        else:
            self.logger.info(f"Layer '{layer_config.name}' has no data source defined. Operations (if any) will not run.")
            # If there were generative operations, they could start here with an empty stream or specific init.
            # For now, if no source, no features are processed further for DXF conversion.
            return

        if features_stream is None: # Should be caught by previous returns, but as a safeguard
            self.logger.error(f"Feature stream is None for layer '{layer_config.name}' before applying operations. This should not happen.")
            return

        # Apply operations
        processed_features_stream = features_stream
        if layer_config.operations:
            self.logger.debug(f"Applying {len(layer_config.operations)} operations to layer '{layer_config.name}'")
            for op_idx, op_config in enumerate(layer_config.operations):
                try:
                    operation_instance = self.di_container.resolve_operation(op_config.type)
                    self.logger.debug(f"  Op {op_idx + 1}: {op_config.type}")
                    processed_features_stream = operation_instance.execute(processed_features_stream, op_config)
                except ConfigurationError as e_op_resolve:
                    self.logger.error(f"Could not resolve operation type '{op_config.type}' for layer '{layer_config.name}': {e_op_resolve}. Skipping remaining operations for this layer.")
                    return
                except Exception as e_op_exec:
                    self.logger.error(f"Error executing operation '{op_config.type}' for layer '{layer_config.name}': {e_op_exec}", exc_info=True)
                    return # Stop processing this layer if an operation fails critically
        else:
            self.logger.debug(f"Layer '{layer_config.name}' has no operations defined.")

        # Transform to DXF entities
        self.logger.debug(f"Transforming features to DXF entities for layer '{layer_config.name}'")
        entity_count = 0
        async for feature in processed_features_stream:
            try:
                # CRS consistency check/final transform - deferred for now, assume ops handled it
                # if global_target_crs and feature.crs and feature.crs.lower() != global_target_crs.lower():
                # logger.warning(f"Feature CRS {feature.crs} differs from global target {global_target_crs} for layer {layer_config.name}. Consider ReprojectOperation.")
                # Potentially reproject here if a strict final CRS is enforced by LayerProcessor itself.

                async for dxf_entity in self.geometry_transformer.transform_feature_to_dxf_entities(feature):
                    entity_count += 1
                    yield dxf_entity
            except Exception as e_transform:
                self.logger.error(f"Error transforming feature to DXF for layer '{layer_config.name}': {e_transform}. Feature ID: {feature.id if feature.id else 'N/A'}", exc_info=True)
                # Continue to next feature or stop layer?

        self.logger.info(f"Finished processing layer: {layer_config.name}. Generated {entity_count} DXF entities.")
