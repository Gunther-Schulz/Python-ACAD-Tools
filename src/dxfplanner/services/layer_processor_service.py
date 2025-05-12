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
        self.logger.info(f"Starting processing for layer: {layer_config.name}")

        if not layer_config.enabled:
            self.logger.info(f"Layer '{layer_config.name}' is disabled. Skipping.")
            return

        # Initialize structures for managing feature streams through operations
        intermediate_results: Dict[str, AsyncIterator[GeoFeature]] = {}
        # current_stream_key will track the key in intermediate_results for the output of the last processed step
        current_stream_key: Optional[str] = None
        initial_features_loaded = False

        if layer_config.source:
            source_conf: AnySourceConfig = layer_config.source
            self.logger.debug(f"Layer '{layer_config.name}' has source type: {source_conf.type} from path '{getattr(source_conf, "path", "N/A")}'") # getattr for safety
            try:
                reader = self.di_container.resolve_reader(source_conf.type)
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
        if layer_config.operations:
            self.logger.debug(f"Applying {len(layer_config.operations)} operations to layer '{layer_config.name}'...")
            for op_idx, op_config in enumerate(layer_config.operations):
                self.logger.info(f"Processing layer '{layer_config.name}', operation {op_idx + 1}/{len(layer_config.operations)}: Type '{op_config.type}'.")

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
                    operation_instance = self.di_container.resolve_operation(op_config.type)
                    self.logger.debug(f"  Executing operation '{op_config.type}' (source: '{resolved_source_key_for_log}').")
                    output_features_stream = operation_instance.execute(input_stream_for_this_op, op_config)
                except ConfigurationError as e_op_resolve:
                    self.logger.error(f"  Could not resolve operation type '{op_config.type}': {e_op_resolve}. Aborting layer '{layer_config.name}'.")
                    return
                except Exception as e_op_exec:
                    self.logger.error(f"  Error executing operation '{op_config.type}': {e_op_exec}. Aborting layer '{layer_config.name}'.", exc_info=True)
                    return

                # 3. Determine output key and store result
                is_last_operation = (op_idx == len(layer_config.operations) - 1)
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
        # This 'elif' handles the case where there was a source, but no operations.
        # current_stream_key would be layer_config.name from the source loading phase.
        elif not layer_config.operations and initial_features_loaded and layer_config.name in intermediate_results:
            final_features_stream_for_dxf = intermediate_results[layer_config.name]
            # current_stream_key should already be layer_config.name in this path if initial_features_loaded is true
            self.logger.info(f"No operations for layer '{layer_config.name}'. Using initial source features for DXF transformation from key '{layer_config.name}'.")
        else: # This case should ideally not be hit if logic above is correct and there's data to process.
            self.logger.warning(f"No feature stream available for DXF transformation for layer '{layer_config.name}'. Current stream key: '{current_stream_key}'. Available results: {list(intermediate_results.keys())}. No DXF entities will be generated.")
            return

        if final_features_stream_for_dxf is None:
            self.logger.error(f"Critical: final_features_stream_for_dxf is None before transformation for layer '{layer_config.name}'. This indicates a logic flaw or an earlier unhandled error in stream preparation. No DXF entities will be generated.")
            return

        # Transform to DXF entities
        self.logger.debug(f"Transforming features from stream '{current_stream_key}' to DXF entities for layer '{layer_config.name}'")
        entity_count = 0
        async for feature in final_features_stream_for_dxf:
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
