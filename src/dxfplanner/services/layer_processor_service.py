"""
Service responsible for processing a single layer configuration.
This includes reading data, applying operations, and transforming to DXF entities.
"""
from typing import AsyncIterator, Optional, Dict, Any, List
from logging import Logger

from dxfplanner.config import AppConfig, LayerConfig, AnySourceConfig, ShapefileSourceConfig, LabelSettings, TextStylePropertiesConfig # Added LabelSettings, TextStylePropertiesConfig
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import (
    IGeoDataReader, IOperation, IGeometryTransformer,
    ILabelPlacementService, IStyleService # Added
)
from dxfplanner.core.di import DIContainer # For resolving dependencies
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError

class LayerProcessorService:
    """Processes a single layer from configuration to an async stream of DXF entities."""

    def __init__(
        self,
        app_config: AppConfig,
        di_container: DIContainer,
        geometry_transformer: IGeometryTransformer,
        label_placement_service: ILabelPlacementService, # Added
        style_service: IStyleService, # Added
        logger: Logger
    ):
        self.app_config = app_config
        self.di_container = di_container
        self.geometry_transformer = geometry_transformer
        self.label_placement_service = label_placement_service # Added
        self.style_service = style_service # Added
        self.logger = logger
        self.logger.info("LayerProcessorService initialized with LabelPlacementService and StyleService.")

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
        elif not layer_config.operations and initial_features_loaded and layer_config.name in intermediate_results:
            final_features_stream_for_dxf = intermediate_results[layer_config.name]
            self.logger.info(f"No operations for layer '{layer_config.name}'. Using initial source features for DXF transformation from key '{layer_config.name}'.")
        else:
            self.logger.warning(f"No feature stream available for DXF transformation for layer '{layer_config.name}'. Current stream key: '{current_stream_key}'. Available results: {list(intermediate_results.keys())}. No DXF entities will be generated.")
            return

        if final_features_stream_for_dxf is None:
            self.logger.error(f"Critical: final_features_stream_for_dxf is None before transformation for layer '{layer_config.name}'. Logic flaw or earlier error. No DXF entities generated.")
            return

        # --- Modified section: Collect features, transform, handle labels ---
        self.logger.debug(f"Collecting features from stream '{current_stream_key}' for layer '{layer_config.name}' before transformation and labeling.")

        final_features_list: List[GeoFeature] = []
        original_entity_count = 0
        try:
             async for feature in final_features_stream_for_dxf:
                 final_features_list.append(feature)
             original_entity_count = len(final_features_list)
             if original_entity_count > 10000: # Arbitrary threshold
                 self.logger.warning(f"Collected {original_entity_count} features for layer '{layer_config.name}' into memory for labeling. High feature counts may consume significant memory.")
             self.logger.debug(f"Collected {original_entity_count} features.")
        except Exception as e_collect:
             self.logger.error(f"Error collecting final features for layer '{layer_config.name}': {e_collect}", exc_info=True)
             # Cannot proceed without the collected features
             return

        # 1. Transform original features to DXF entities
        transformed_dxf_entities: List[AnyDxfEntity] = []
        transform_errors = 0
        self.logger.debug(f"Transforming {original_entity_count} collected features to DXF entities...")
        for feature in final_features_list:
            try:
                async for dxf_entity in self.geometry_transformer.transform_feature_to_dxf_entities(feature):
                    transformed_dxf_entities.append(dxf_entity)
            except Exception as e_transform:
                transform_errors += 1
                self.logger.error(f"Error transforming feature to DXF for layer '{layer_config.name}': {e_transform}. Feature ID: {feature.id if feature.id else 'N/A'}", exc_info=False) # Keep log cleaner

        if transform_errors > 0:
             self.logger.warning(f"Encountered {transform_errors} errors during feature transformation for layer '{layer_config.name}'.")
        self.logger.debug(f"Generated {len(transformed_dxf_entities)} DXF entities from original features.")

        # 2. Handle Labeling if configured
        label_dxf_entities: List[AnyDxfEntity] = []
        if layer_config.labeling:
            self.logger.info(f"Labeling enabled for layer '{layer_config.name}'. Processing labels.")
            label_conf: LabelSettings = layer_config.labeling.label_settings # Access nested settings

            # Re-create async iterator from list for label placement service
            # This avoids modifying the ILabelPlacementService interface for now
            async def feature_list_iterator(features: List[GeoFeature]) -> AsyncIterator[GeoFeature]:
                 for f in features:
                      yield f

            label_text_style: Optional[TextStylePropertiesConfig] = None
            try:
                # Resolve the text style for labels using the StyleService
                # Pass LabelingConfig itself for context if needed, or specific style references from it.
                label_text_style = self.style_service.get_text_style_properties(
                    style_reference=layer_config.labeling.text_style_preset_name or layer_config.labeling.text_style_inline,
                    layer_config_fallback=None # Don't fallback to layer style, use labeling specific style
                )
                self.logger.debug(f"Resolved text style for labels on layer '{layer_config.name}'. Font: {label_text_style.font}, Height: {label_text_style.height}")
            except Exception as e_style:
                self.logger.error(f"Could not resolve text style for labeling on layer '{layer_config.name}': {e_style}. Skipping labeling.", exc_info=True)
                # Skip labeling if style resolution fails

            if label_text_style: # Only proceed if style was resolved
                placed_labels_count = 0
                label_transform_errors = 0
                try:
                    async for placed_label in self.label_placement_service.place_labels_for_features(
                        feature_list_iterator(final_features_list),
                        layer_config.name,
                        label_conf # Pass the LabelSettings part
                    ):
                        placed_labels_count += 1
                        try:
                            # Transform the PlacedLabel using the resolved style
                            label_dxf_entity = await self.geometry_transformer.transform_placed_label_to_dxf_entity(
                                placed_label,
                                label_text_style # Pass the resolved style
                            )
                            if label_dxf_entity:
                                # Assign the correct layer based on LabelPlacementOperationConfig if specified, else default/style?
                                # For now, assume transform_placed_label_to_dxf_entity sets a default layer ("0").
                                # A better approach would be to get the target label layer from config here.
                                label_output_layer = getattr(layer_config.labeling, 'output_label_layer_name', None) or layer_config.name
                                if hasattr(label_dxf_entity, 'layer'):
                                     label_dxf_entity.layer = label_output_layer # Override layer if possible

                                label_dxf_entities.append(label_dxf_entity)

                        except Exception as e_label_transform:
                            label_transform_errors += 1
                            self.logger.error(f"Error transforming placed label '{placed_label.text}' to DXF for layer '{layer_config.name}': {e_label_transform}", exc_info=False)

                    self.logger.info(f"Label placement service processed {placed_labels_count} potential labels for layer '{layer_config.name}'.")
                    if label_transform_errors > 0:
                         self.logger.warning(f"Encountered {label_transform_errors} errors during label transformation for layer '{layer_config.name}'.")

                except Exception as e_placement:
                    self.logger.error(f"Error during label placement for layer '{layer_config.name}': {e_placement}", exc_info=True)
                    # Continue without labels if placement fails

        # 3. Yield all generated entities (original features + labels)
        total_yielded_count = 0
        for entity in transformed_dxf_entities:
            yield entity
            total_yielded_count += 1
        for label_entity in label_dxf_entities:
            yield label_entity
            total_yielded_count += 1

        self.logger.info(f"Finished processing layer: {layer_config.name}. Yielded {total_yielded_count} DXF entities ({len(transformed_dxf_entities)} from features, {len(label_dxf_entities)} from labels).")
