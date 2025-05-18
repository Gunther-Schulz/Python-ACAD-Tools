"""
Service responsible for processing a single layer configuration.
This includes reading data, applying operations, and transforming to DXF entities.
"""
from typing import AsyncIterator, Optional, Dict, Any, TYPE_CHECKING, Callable, Mapping, Type, Tuple, List, TypeVar
from logging import Logger
from dependency_injector import providers
import asyncio

from dxfplanner.config.schemas import ProjectConfig, LayerConfig, AnySourceConfig, ShapefileSourceConfig, GeometryOperationType, DataSourceType, AnyOperationConfig
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IGeoDataReader, IOperation, IGeometryTransformer, ILayerProcessorService, IStyleService
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError

if TYPE_CHECKING:
    pass # If block becomes empty, it can be removed.

T = TypeVar('T') # For generic async iterator replication

# Moved helper outside class to be a free function, simpler.
async def _replicate_async_iterator_helper(logger: Logger, aiter: AsyncIterator[T], n: int, context_name: str = "Unknown") -> Tuple[AsyncIterator[T], ...]:
    logger.debug(f"Replicating async iterator '{context_name}' into {n} copies. This will consume the original.")
    materialized_items = []
    original_item_count = 0
    async for item in aiter:
        materialized_items.append(item)
        original_item_count += 1
    logger.debug(f"Original iterator '{context_name}' consumed, {original_item_count} items materialized for {n} replicas.")

    async def _generator_from_list(items_list: List[T], replica_id: int, parent_context_name: str) -> AsyncIterator[T]:
        item_count = 0
        # logger.debug(f"Replica #{replica_id} of '{parent_context_name}' starting to yield from {len(items_list)} materialized items.")
        for item in items_list:
            yield item
            item_count += 1
            await asyncio.sleep(0) # Allow event loop to switch, good practice
        logger.debug(f"Replica #{replica_id} of '{parent_context_name}' finished yielding {item_count} items.")

    return tuple(_generator_from_list(materialized_items, i + 1, context_name) for i in range(n))

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
                source_stream_from_reader = reader.read_features(**common_reader_args, **reader_kwargs)

                num_source_consumers = 1 # For direct output stream
                if effective_operations:
                    num_source_consumers += 1 # For ops pipeline input

                if num_source_consumers > 0: # Should always be true if source exists
                    replicated_source_streams = await _replicate_async_iterator_helper(
                        self.logger, source_stream_from_reader, num_source_consumers, f"source:{layer_config.name}"
                    )

                    output_geo_feature_streams_with_context[layer_config.name] = (layer_config, replicated_source_streams[0])
                    self.logger.info(f"Prepared direct output stream (Replica 1/{num_source_consumers}) for source layer '{layer_config.name}'.")

                    if effective_operations:
                        streams_for_ops_pipeline[layer_config.name] = replicated_source_streams[1]
                        current_op_input_key = layer_config.name
                        initial_features_loaded_for_ops = True
                        self.logger.info(f"Prepared source stream (Replica 2/{num_source_consumers}) for operations pipeline from layer '{layer_config.name}' under key '{current_op_input_key}'.")
                # No 'else' needed as num_source_consumers will be 1 even if no ops, and handled by replica 0.

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
                    output_features_stream_from_op_orig = operation_instance.execute(input_stream_for_this_op, op_config)
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

                stream_for_next_op_in_pipeline: AsyncIterator[GeoFeature]
                stream_for_final_output_if_named: Optional[AsyncIterator[GeoFeature]] = None

                is_final_named_output = not conceptual_output_name_for_op.startswith("__intermediate_")
                num_op_output_consumers = 1 # For streams_for_ops_pipeline (next op or just to hold the result)
                if is_final_named_output:
                    num_op_output_consumers += 1 # For output_geo_feature_streams_with_context

                if num_op_output_consumers > 1:
                    self.logger.debug(f"Replicating output of op '{op_config.type}' ('{conceptual_output_name_for_op}') for {num_op_output_consumers} consumers.")
                    replicated_op_streams = await _replicate_async_iterator_helper(
                        self.logger, output_features_stream_from_op_orig, num_op_output_consumers, f"op:{conceptual_output_name_for_op}"
                    )
                    stream_for_next_op_in_pipeline = replicated_op_streams[0]
                    if is_final_named_output:
                        stream_for_final_output_if_named = replicated_op_streams[1]
                else: # Only one consumer, no replication needed
                    stream_for_next_op_in_pipeline = output_features_stream_from_op_orig
                    if is_final_named_output:
                        stream_for_final_output_if_named = output_features_stream_from_op_orig # Same stream if only for final output

                streams_for_ops_pipeline[conceptual_output_name_for_op] = stream_for_next_op_in_pipeline
                current_op_input_key = conceptual_output_name_for_op

                if is_final_named_output and stream_for_final_output_if_named:
                    if conceptual_output_name_for_op in output_geo_feature_streams_with_context:
                         self.logger.warning(f"Operation output '{conceptual_output_name_for_op}' is overwriting an existing stream in final results (e.g. the original source stream if names clash). Styling context from LayerConfig '{layer_config.name}' will be used.")
                    output_geo_feature_streams_with_context[conceptual_output_name_for_op] = (layer_config, stream_for_final_output_if_named)
                    self.logger.info(f"  Operation '{op_config.type}' produced output stream '{conceptual_output_name_for_op}', added to final results (using replica if needed).")
        else:
            self.logger.debug(f"Layer '{layer_config.name}' has no operations defined.")
            if not layer_config.source:
                 self.logger.warning(f"Layer '{layer_config.name}' has no source and no operations. No GeoFeature streams will be produced.")

        if not output_geo_feature_streams_with_context:
             if layer_config.source or effective_operations:
                self.logger.warning(f"Layer '{layer_config.name}' processing completed, but no explicitly named GeoFeature streams were added to the final output dictionary. This might be an issue if output was expected.")

        self.logger.info(f"Finished GeoFeature stream collection for layer '{layer_config.name}'. Produced {len(output_geo_feature_streams_with_context)} named GeoFeature stream(s) for PipelineService: {list(output_geo_feature_streams_with_context.keys())}")
        return output_geo_feature_streams_with_context
