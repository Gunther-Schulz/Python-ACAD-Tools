"""
Service responsible for processing a single layer configuration.
This includes reading data, applying operations, and transforming to DXF entities.
"""
from typing import AsyncIterator, Optional, Dict, Any, TYPE_CHECKING, Callable, Mapping, Type, Tuple
from logging import Logger
from dependency_injector import providers

from dxfplanner.config.schemas import ProjectConfig, LayerConfig, AnySourceConfig, ShapefileSourceConfig, GeometryOperationType, DataSourceType, AnyOperationConfig
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IGeoDataReader, IOperation, IGeometryTransformer, ILayerProcessorService, IStyleService
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError

if TYPE_CHECKING:
    pass # If block becomes empty, it can be removed.

class LayerProcessorService(ILayerProcessorService):
    """Processes a single layer from configuration to an async stream of DXF entities."""

    def __init__(
        self,
        project_config: ProjectConfig,
        geo_data_reader_factories_map: Mapping[DataSourceType, providers.Factory[IGeoDataReader]],
        operations_map: Mapping[GeometryOperationType, providers.Factory[IOperation]],
        geometry_transformer: IGeometryTransformer,
        style_service: IStyleService,
        logger: Logger
    ):
        self.project_config = project_config
        self.geo_data_reader_factories_map = geo_data_reader_factories_map
        self.operations_map = operations_map
        self.geometry_transformer = geometry_transformer
        self.style_service = style_service
        self.logger = logger
        self.logger.info("LayerProcessorService initialized.")

    def _resolve_operation_instance(self, op_type: GeometryOperationType, op_config: AnyOperationConfig) -> IOperation:
        """Resolves and instantiates an operation based on its type and config."""
        self.logger.debug(f"Resolving operation: Type='{op_type}', Config='{op_config.model_dump_json(exclude_none=True)}'")

        op_factory_provider = self.operations_map.get(op_type)
        if not op_factory_provider:
            self.logger.error(f"No operation factory configured for type: {op_type}")
            raise ConfigurationError(f"No operation configured for type: {op_type}")

        try:
            operation_instance = op_factory_provider
            self.logger.debug(f"Successfully resolved operation instance for type: {op_type}. Instance type: {type(operation_instance)}")
            return operation_instance
        except Exception as e:
            self.logger.error(f"Error resolving/instantiating operation for type '{op_type}': {e}", exc_info=True)
            raise ConfigurationError(f"Error resolving/instantiating operation {op_type}: {e}")

    async def process_layer(
        self,
        layer_config: LayerConfig,
    ) -> Dict[str, Tuple[LayerConfig, AsyncIterator[GeoFeature]]]:
        """
        Processes a single layer configuration, applying operations and collecting
        all named GeoFeature streams.
        """
        self.logger.info(f"Starting GeoFeature stream collection for layer: {layer_config.name}")

        if not layer_config.enabled:
            self.logger.info(f"Layer '{layer_config.name}' is disabled. Skipping.")
            return {}

        output_geo_feature_streams_with_context: Dict[str, Tuple[LayerConfig, AsyncIterator[GeoFeature]]] = {}

        streams_for_ops_pipeline: Dict[str, AsyncIterator[GeoFeature]] = {}

        current_op_input_key: Optional[str] = None
        initial_features_loaded_for_ops = False

        effective_operations = list(layer_config.operations) if layer_config.operations is not None else []

        if layer_config.source:
            source_conf: AnySourceConfig = layer_config.source
            path_value = getattr(source_conf, "path", "N/A")
            self.logger.debug(f"Layer '{layer_config.name}' source: type={source_conf.type}, path='{path_value}'")
            reader_factory_provider = self.geo_data_reader_factories_map.get(source_conf.type)

            if not reader_factory_provider:
                self.logger.error(f"Could not find reader factory provider for source type '{source_conf.type}' in layer '{layer_config.name}'. Aborting layer processing.")
                return {}

            try:
                reader: IGeoDataReader = reader_factory_provider(config=source_conf, logger=self.logger)
            except Exception as e_resolve:
                self.logger.error(f"Could not instantiate reader for source type '{source_conf.type}' in layer '{layer_config.name}': {e_resolve}. Aborting layer processing.", exc_info=True)
                return {}

            reader_kwargs: Dict[str, Any] = {}
            if isinstance(source_conf, ShapefileSourceConfig) and source_conf.encoding:
                reader_kwargs['encoding'] = source_conf.encoding

            common_reader_args = {
                "source_path": getattr(source_conf, 'path', None),
                "source_crs": getattr(source_conf, 'crs', None),
                "target_crs": None,
            }

            try:
                direct_output_source_stream = reader.read_features(**common_reader_args, **reader_kwargs)
                output_geo_feature_streams_with_context[layer_config.name] = (layer_config, direct_output_source_stream)
                self.logger.info(f"Prepared direct output stream for source layer '{layer_config.name}'.")

                if effective_operations:
                    ops_pipeline_source_stream = reader.read_features(**common_reader_args, **reader_kwargs)
                    streams_for_ops_pipeline[layer_config.name] = ops_pipeline_source_stream
                    current_op_input_key = layer_config.name
                    initial_features_loaded_for_ops = True
                    self.logger.info(f"Prepared source stream for operations pipeline from layer '{layer_config.name}' under key '{current_op_input_key}'.")
                elif not effective_operations:
                    self.logger.info(f"Layer '{layer_config.name}' has source but no operations. Direct output stream is ready.")

            except GeoDataReadError as e:
                self.logger.error(f"Error reading data for layer '{layer_config.name}': {e}. Aborting layer processing.")
                return {}
            except Exception as e_read_generic:
                self.logger.error(f"Unexpected error during data read for layer '{layer_config.name}': {e_read_generic}. Aborting layer processing.", exc_info=True)
                return {}
        else:
            self.logger.info(f"Layer '{layer_config.name}' has no data source defined. Operations will proceed if they are generative or explicitly source other named results.")

        if effective_operations:
            self.logger.debug(f"Applying {len(effective_operations)} operations to layer '{layer_config.name}'...")
            for op_idx, op_config in enumerate(effective_operations):
                self.logger.info(f"Processing layer '{layer_config.name}', operation {op_idx + 1}/{len(effective_operations)}: Type '{op_config.type}'.")

                input_stream_for_this_op: Optional[AsyncIterator[GeoFeature]] = None
                resolved_source_key_for_log: str = "None (generative or error)"

                op_explicit_source_name = getattr(op_config, 'source_layer', None)

                if op_explicit_source_name:
                    resolved_source_key_for_log = op_explicit_source_name
                    if op_explicit_source_name not in streams_for_ops_pipeline:
                        self.logger.error(f"  Explicit source_layer '{op_explicit_source_name}' for operation '{op_config.type}' not found in available ops pipeline streams. Available: {list(streams_for_ops_pipeline.keys())}. Aborting layer '{layer_config.name}'.")
                        return {}
                    input_stream_for_this_op = streams_for_ops_pipeline[op_explicit_source_name]
                elif current_op_input_key and current_op_input_key in streams_for_ops_pipeline:
                    resolved_source_key_for_log = current_op_input_key
                    input_stream_for_this_op = streams_for_ops_pipeline[current_op_input_key]
                elif not initial_features_loaded_for_ops and not op_explicit_source_name :
                     self.logger.info(f"  Operation '{op_config.type}' has no implicit chained input and no explicit source_layer. Assuming generative operation or one that handles absent input.")
                     resolved_source_key_for_log = "None (generative)"
                else:
                    self.logger.error(f"  Cannot determine input stream for operation '{op_config.type}'. Current op input key: '{current_op_input_key}', Initial features for ops: {initial_features_loaded_for_ops}. Aborting layer '{layer_config.name}'.")
                    return {}

                try:
                    operation_instance = self._resolve_operation_instance(op_type=op_config.type, op_config=op_config)
                    self.logger.debug(f"  Executing operation '{op_config.type}' (consuming from: '{resolved_source_key_for_log}').")
                    output_features_stream_from_op = operation_instance.execute(input_stream_for_this_op, op_config)
                except ConfigurationError as e_op_resolve:
                    self.logger.error(f"  Could not resolve operation type '{op_config.type}': {e_op_resolve}. Aborting layer '{layer_config.name}'.")
                    return {}
                except Exception as e_op_exec:
                    self.logger.error(f"  Error executing operation '{op_config.type}': {e_op_exec}. Aborting layer '{layer_config.name}'.", exc_info=True)
                    return {}

                op_output_name_attr = getattr(op_config, 'output_layer_name', None) or \
                                      getattr(op_config, 'output_label_layer_name', None)

                conceptual_output_name_for_op: str
                if op_output_name_attr:
                    conceptual_output_name_for_op = op_output_name_attr
                else:
                    conceptual_output_name_for_op = f"__intermediate_{layer_config.name}_op{op_idx}_{op_config.type.value}__"

                if conceptual_output_name_for_op in streams_for_ops_pipeline and conceptual_output_name_for_op != resolved_source_key_for_log:
                    self.logger.warning(f"  Output key '{conceptual_output_name_for_op}' for operation '{op_config.type}' overwrites an existing stream in the ops pipeline. This might be intended if chaining operations that refine the same conceptual layer.")

                streams_for_ops_pipeline[conceptual_output_name_for_op] = output_features_stream_from_op
                current_op_input_key = conceptual_output_name_for_op

                if not conceptual_output_name_for_op.startswith("__intermediate_"):
                    if conceptual_output_name_for_op in output_geo_feature_streams_with_context:
                         self.logger.warning(f"Operation output '{conceptual_output_name_for_op}' is overwriting an existing stream in final outputs (e.g. the original source stream if names clash). Styling context from LayerConfig '{layer_config.name}' will be used.")
                    output_geo_feature_streams_with_context[conceptual_output_name_for_op] = (layer_config, output_features_stream_from_op)
                    self.logger.info(f"  Operation '{op_config.type}' produced output stream '{conceptual_output_name_for_op}', added to final results.")

        else:
            self.logger.debug(f"Layer '{layer_config.name}' has no operations defined.")
            if not layer_config.source:
                 self.logger.warning(f"Layer '{layer_config.name}' has no source and no operations. No GeoFeature streams will be produced.")

        if not output_geo_feature_streams_with_context:
             if layer_config.source or effective_operations:
                self.logger.warning(f"Layer '{layer_config.name}' processing completed, but no explicitly named GeoFeature streams were added to the final output dictionary. This might be an issue if output was expected.")

        self.logger.info(f"Finished GeoFeature stream collection for layer '{layer_config.name}'. Produced {len(output_geo_feature_streams_with_context)} named GeoFeature stream(s) for PipelineService: {list(output_geo_feature_streams_with_context.keys())}")
        return output_geo_feature_streams_with_context
