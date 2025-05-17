"""
Service responsible for processing a single layer configuration.
This includes reading data, applying operations, and transforming to DXF entities.
"""
from typing import AsyncIterator, Optional, Dict, Any, TYPE_CHECKING, Callable
from logging import Logger

from dxfplanner.config.schemas import ProjectConfig, LayerConfig, AnySourceConfig, ShapefileSourceConfig, GeometryOperationType, DataSourceType # ADDED DataSourceType
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IGeoDataReader, IOperation, IGeometryTransformer, ILayerProcessorService
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError

if TYPE_CHECKING:
    from dxfplanner.core.di import DIContainer # Import for type hinting only

class LayerProcessorService(ILayerProcessorService):
    """Processes a single layer from configuration to an async stream of DXF entities."""

    def __init__(
        self,
        project_config: ProjectConfig,
        reader_resolver_provider: Callable[[DataSourceType], IGeoDataReader], # CHANGED
        operation_resolver_provider: Callable[[GeometryOperationType], IOperation], # CHANGED
        geometry_transformer: IGeometryTransformer,
        logger: Logger
    ):
        self.project_config = project_config
        self.reader_resolver = reader_resolver_provider # CHANGED
        self.operation_resolver = operation_resolver_provider # CHANGED
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
        self.logger.info(f"Starting processing for layer: {layer_config.name}")

        if not layer_config.enabled:
            self.logger.info(f"Layer '{layer_config.name}' is disabled. Skipping.")
            return

        # Initialize structures for managing feature streams through operations
        intermediate_results: Dict[str, AsyncIterator[GeoFeature]] = {}
        # current_stream_key will track the key in intermediate_results for the output of the last processed step
        current_stream_key: Optional[str] = None
        initial_features_loaded = False

        # Operations list from config
        effective_operations = list(layer_config.operations) if layer_config.operations is not None else [] # Ensure it's a list, handles None

        if layer_config.source:
            source_conf: AnySourceConfig = layer_config.source
            self.logger.debug(f"Layer '{layer_config.name}' has source type: {source_conf.type} from path '{getattr(source_conf, "path", "N/A")}'")
            self.logger.debug(f"DEBUG: About to call reader_resolver with source_conf.type: {source_conf.type} (type: {type(source_conf.type)})")
            try:
                reader = self.reader_resolver(source_conf.type)
            except ConfigurationError as e:
                self.logger.error(f"Could not resolve reader for source type '{source_conf.type}' in layer '{layer_config.name}': {e}. Aborting layer processing.")
                return

            reader_kwargs: Dict[str, Any] = {}
            if isinstance(source_conf, ShapefileSourceConfig):
                if source_conf.encoding:
                    reader_kwargs['encoding'] = source_conf.encoding
            # Add elif for other source types (CsvWktSourceConfig, GeoJsonSourceConfig) to extract their specific kwargs

            try:
                source_features_stream = reader.read_features(
                    source_path=getattr(source_conf, 'path', None), # getattr for safety, though path is usually mandatory
                    source_crs=getattr(source_conf, 'crs', None),
                    target_crs=None, # Reprojection handled by operations if needed
                    **reader_kwargs
                )
                # Store the initial stream using the layer_config.name as its key
                intermediate_results[layer_config.name] = source_features_stream
                current_stream_key = layer_config.name
                initial_features_loaded = True
                self.logger.info(f"Successfully loaded initial features for layer '{layer_config.name}' under key '{current_stream_key}'.")
            except GeoDataReadError as e:
                self.logger.error(f"Error reading data for layer '{layer_config.name}' from source '{getattr(source_conf, "path", "N/A")}': {e}. Aborting layer processing.")
                return
            except Exception as e_read_generic:
                self.logger.error(f"Unexpected error during data read for layer '{layer_config.name}': {e_read_generic}. Aborting layer processing.", exc_info=True)
                return
        else:
            self.logger.info(f"Layer '{layer_config.name}' has no data source defined. Operations will proceed if they are generative or explicitly source other named results.")
            # current_stream_key remains None; operations must handle this or have an explicit source.

        # Apply operations
        if effective_operations: # Use the effective_operations list
            self.logger.debug(f"Applying {len(effective_operations)} effective operations to layer '{layer_config.name}'...")
            for op_idx, op_config in enumerate(effective_operations): # Use the effective_operations list
                self.logger.info(f"Processing layer '{layer_config.name}', operation {op_idx + 1}/{len(effective_operations)}: Type '{op_config.type}'.")

                input_stream_for_this_op: Optional[AsyncIterator[GeoFeature]] = None
                resolved_source_key_for_log: str = "None (generative or error)"


                # 1. Determine input stream for the current operation
                # hasattr check is important as not all op_config types will have 'source_layer'
                op_source_layer_attr = getattr(op_config, 'source_layer', None)

                if op_source_layer_attr:
                    resolved_source_key_for_log = op_source_layer_attr
                    if op_source_layer_attr not in intermediate_results:
                        self.logger.error(f"  Explicit source_layer '{op_source_layer_attr}' for operation '{op_config.type}' not found in intermediate results. Available: {list(intermediate_results.keys())}. Aborting layer '{layer_config.name}'.")
                        return
                    input_stream_for_this_op = intermediate_results[op_source_layer_attr]
                    self.logger.debug(f"  Using explicit source_layer '{op_source_layer_attr}' for operation '{op_config.type}'.")
                elif current_stream_key and current_stream_key in intermediate_results:
                    resolved_source_key_for_log = current_stream_key
                    input_stream_for_this_op = intermediate_results[current_stream_key]
                    self.logger.debug(f"  Using implicit source (output of previous step '{current_stream_key}') for operation '{op_config.type}'.")
                elif op_idx == 0 and not initial_features_loaded: # First op, no layer source, no explicit op source
                     self.logger.info(f"  Operation '{op_config.type}' is first, layer '{layer_config.name}' had no source, and no explicit source_layer given. Assuming generative operation or one that handles absent input stream.")
                     resolved_source_key_for_log = "None (generative first op)"
                     # input_stream_for_this_op remains None, operation must handle it
                else: # If current_stream_key is None but it's not a generative first op case
                    self.logger.error(f"  Cannot determine input stream for operation '{op_config.type}'. Current stream key: '{current_stream_key}', Initial features loaded: {initial_features_loaded}. Aborting layer '{layer_config.name}'.")
                    return

                # 2. Execute the operation
                try:
                    operation_instance = self.operation_resolver(op_config.type)
                    self.logger.debug(f"  Executing operation '{op_config.type}' (source: '{resolved_source_key_for_log}').")
                    output_features_stream = operation_instance.execute(input_stream_for_this_op, op_config)
                except ConfigurationError as e_op_resolve:
                    self.logger.error(f"  Could not resolve operation type '{op_config.type}': {e_op_resolve}. Aborting layer '{layer_config.name}'.")
                    return
                except Exception as e_op_exec:
                    self.logger.error(f"  Error executing operation '{op_config.type}': {e_op_exec}. Aborting layer '{layer_config.name}'.", exc_info=True)
                    return

                # 3. Determine output key and store result
                is_last_operation = (op_idx == len(effective_operations) - 1) # Use effective_operations
                output_key_for_this_op: str

                # Prioritize specific output name attributes if they exist (e.g. output_label_layer_name)
                # then fall back to generic output_layer_name
                op_output_name = None
                if hasattr(op_config, 'output_label_layer_name') and getattr(op_config, 'output_label_layer_name'): # Specific for LabelPlacement
                    op_output_name = getattr(op_config, 'output_label_layer_name')
                elif hasattr(op_config, 'output_layer_name') and getattr(op_config, 'output_layer_name'): # Generic
                    op_output_name = getattr(op_config, 'output_layer_name')


                if op_output_name:
                    output_key_for_this_op = op_output_name
                    self.logger.debug(f"  Operation '{op_config.type}' output explicitly named as '{output_key_for_this_op}'.")
                elif is_last_operation:
                    output_key_for_this_op = layer_config.name
                    self.logger.debug(f"  Operation '{op_config.type}' (last op) output will be associated with LayerConfig name '{output_key_for_this_op}'.")
                else: # Intermediate operation with no explicit output name
                    output_key_for_this_op = f"__intermediate_{layer_config.name}_op{op_idx}_{op_config.type}__"
                    self.logger.debug(f"  Operation '{op_config.type}' output implicitly named '{output_key_for_this_op}'.")

                if output_key_for_this_op in intermediate_results and output_key_for_this_op != resolved_source_key_for_log :
                    self.logger.warning(f"  Output key '{output_key_for_this_op}' for operation '{op_config.type}' overwrites an existing intermediate result. This might be intended if an explicit output_layer_name matches a previous one, or if multiple ops output to the same named layer.")

                intermediate_results[output_key_for_this_op] = output_features_stream
                current_stream_key = output_key_for_this_op # Update for the next iteration
        else: # No operations defined for this layer_config
            self.logger.debug(f"Layer '{layer_config.name}' has no operations defined.")
            if not initial_features_loaded: # No source and no operations
                 self.logger.warning(f"Layer '{layer_config.name}' has no source and no operations. No DXF entities will be generated.")
                 return
            # If initial_features_loaded is true, current_stream_key would be layer_config.name from the source loading step.


        # Determine the final feature stream for DXF transformation
        final_features_stream_for_dxf: Optional[AsyncIterator[GeoFeature]] = None
        if current_stream_key and current_stream_key in intermediate_results:
            final_features_stream_for_dxf = intermediate_results[current_stream_key]
            self.logger.info(f"Final feature stream for DXF transformation for layer '{layer_config.name}' is from '{current_stream_key}'.")
        elif not effective_operations and initial_features_loaded: # Source loaded, no ops
            final_features_stream_for_dxf = intermediate_results[layer_config.name]
            self.logger.info(f"Final feature stream for DXF transformation for layer '{layer_config.name}' is directly from source (no operations).")


        if final_features_stream_for_dxf:
            self.logger.info(f"Transforming final GeoFeatures to DxfEntities for layer: {layer_config.name}")
            # Correctly use the geometry_transformer's existing method
            async for geo_feature in final_features_stream_for_dxf:
                # The transform_feature_to_dxf_entities method on GeometryTransformerImpl
                # already handles StyleService interaction and layer_config.
                async for dxf_entity in self.geometry_transformer.transform_feature_to_dxf_entities(
                    geo_feature, layer_config=layer_config # Pass layer_config as required by the method
                ):
                    yield dxf_entity
            self.logger.info(f"Finished transforming GeoFeatures to DxfEntities for layer: {layer_config.name}")
        else:
            self.logger.warning(f"No final feature stream determined for layer '{layer_config.name}'. No DXF entities will be generated for this layer.")
            # An async def function that doesn't yield anything implicitly returns an empty async generator.
            return
