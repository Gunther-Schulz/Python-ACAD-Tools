from typing import AsyncIterator, Any, Optional, Dict
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo # PointGeo for label geometry
from dxfplanner.domain.interfaces import IOperation, ILabelPlacementService, IStyleService, PlacedLabel # PlacedLabel for service output
from dxfplanner.config.operation_schemas import LabelPlacementOperationConfig
from dxfplanner.config.style_schemas import LabelingConfig, TextStylePropertiesConfig # For type hints
from dxfplanner.core.logging_config import get_logger # Main logger
from logging import Logger # For type hint

logger = get_logger(__name__)

class LabelPlacementOperation(IOperation[LabelPlacementOperationConfig]):
    """Performs label placement by utilizing an ILabelPlacementService."""

    def __init__(self, label_placement_service: ILabelPlacementService, style_service: IStyleService, logger_param: Optional[Logger] = None):
        self.label_placement_service = label_placement_service
        self.style_service = style_service
        self.logger = logger_param if logger_param else logger

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: LabelPlacementOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        log_prefix = f"LabelPlacementOperation (source: '{config.source_layer}', output: '{config.output_label_layer_name or config.output_layer_name}')"
        self.logger.info(f"{log_prefix}: Delegating to LabelPlacementService.")

        contextual_layer_name_for_service = config.source_layer or config.output_label_layer_name or "unknown_source_for_labeling"
        label_settings: Optional[LabelingConfig] = config.label_settings
        text_style_props_for_service: Optional[TextStylePropertiesConfig] = None

        if not label_settings:
            self.logger.warning(f"{log_prefix}: label_settings is None in operation config. Labels might not be generated or use defaults.")
        else: # DEBUG LOGGING START
            self.logger.debug(f"{log_prefix}: Configured label_settings: {label_settings.model_dump_json(exclude_none=True, indent=2)}") # INFO to DEBUG
        # DEBUG LOGGING END

        try:
            # Fetch the original style properties
            original_text_style_props = self.style_service.get_resolved_style_for_label_operation(config=config)

            # Immediately make a defensive copy to be used by the service
            text_style_props_for_service = original_text_style_props.model_copy(deep=True) if original_text_style_props else None

        except Exception as e_style_resolve:
            self.logger.error(f"{log_prefix}: Error resolving text style: {e_style_resolve}", exc_info=True)
            # Ensure they are assigned even in exception to avoid NameError later
            if 'original_text_style_props' not in locals():
                 original_text_style_props = TextStylePropertiesConfig()
            if 'text_style_props_for_service' not in locals():
                 text_style_props_for_service = TextStylePropertiesConfig()

        # Accessing label_settings here is known to mutate original_text_style_props
        if label_settings is None:
            self.logger.info(f"{log_prefix}: No label_settings provided (or resolved to None), label placement service might skip or use defaults.")

        self.logger.debug(f"{log_prefix}: Calling label_placement_service.place_labels_for_features with layer_name='{contextual_layer_name_for_service}'.")

        placed_label_data_stream = self.label_placement_service.place_labels_for_features(
            features=features,
            layer_name=contextual_layer_name_for_service,
            config=label_settings,
            text_style_properties=text_style_props_for_service # Use the safe, copied version
        )

        placed_labels_received_count = 0 # DEBUG LOGGING
        geo_features_yielded_count = 0 # DEBUG LOGGING
        self.logger.debug(f"{log_prefix}: Starting to iterate PlacedLabel stream from service.") # INFO to DEBUG

        async for placed_label in placed_label_data_stream:
            placed_labels_received_count += 1 # DEBUG LOGGING
            self.logger.debug(f"{log_prefix}: Received PlacedLabel #{placed_labels_received_count}: Text='{placed_label.text}', Pos={placed_label.position}") # INFO to DEBUG
            label_geometry = PointGeo(coordinates=placed_label.position)
            label_properties: Dict[str, Any] = {
                "__geometry_type__": "LABEL",
                "label_text": placed_label.text,
                "label_rotation": placed_label.rotation,
                "text_style_properties": text_style_props_for_service.model_dump(exclude_unset=True) if text_style_props_for_service else {}
            }
            yield GeoFeature(geometry=label_geometry, properties=label_properties, crs=None)
            geo_features_yielded_count +=1 # DEBUG LOGGING

        self.logger.debug(f"{log_prefix}: Finished iterating PlacedLabel stream. Received: {placed_labels_received_count}, Yielded GeoFeatures: {geo_features_yielded_count}.") # INFO to DEBUG
        self.logger.info(f"{log_prefix}: Completed.")
