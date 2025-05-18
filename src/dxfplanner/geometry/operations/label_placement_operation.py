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
        text_style_props_for_service_call: Optional[TextStylePropertiesConfig] = None

        if not label_settings:
            self.logger.warning(f"{log_prefix}: label_settings is None. Labels might not be generated or use defaults.")
            # Depending on ILabelPlacementService behavior, might need to yield original features or empty stream.
            # For now, assume service handles None label_settings gracefully.
            # If it MUST have label_settings, then:
            # self.logger.error(f"{log_prefix}: label_settings is None, cannot proceed.")
            # return # or raise error

        try:
            text_style_props_for_service_call = self.style_service.get_resolved_style_for_label_operation(config=config)
            self.logger.debug(f"{log_prefix}: Resolved text style: {text_style_props_for_service_call.model_dump_json(indent=2, exclude_unset=True) if text_style_props_for_service_call else 'None'}")
        except Exception as e_style_resolve:
            self.logger.error(f"{log_prefix}: Error resolving text style: {e_style_resolve}", exc_info=True)
            text_style_props_for_service_call = TextStylePropertiesConfig() # Fallback default

        # Ensure label_settings is not None before passing to service if service requires it.
        # If service can handle None, this check is optional but good for clarity.
        if label_settings is None:
            self.logger.info(f"{log_prefix}: No label_settings provided, label placement might be skipped by service or use defaults.")
            # If the service MUST have LabelingConfig, then we should not proceed or provide a default.
            # For now, we'll pass it as None and let the service decide.

        placed_label_data_stream = self.label_placement_service.place_labels_for_features(
            features=features,
            layer_name=contextual_layer_name_for_service,
            config=label_settings, # Pass Optional[LabelingConfig]
            text_style_properties=text_style_props_for_service_call
        )

        async for placed_label in placed_label_data_stream: # placed_label is PlacedLabel model
            label_geometry = PointGeo(coordinates=placed_label.position)
            label_properties: Dict[str, Any] = {
                "__geometry_type__": "LABEL",
                "label_text": placed_label.text,
                "label_rotation": placed_label.rotation,
                "text_style_properties": text_style_props_for_service_call.model_dump(exclude_unset=True) if text_style_props_for_service_call else {}
            }
            yield GeoFeature(geometry=label_geometry, properties=label_properties, crs=None) # Changed 'attributes' to 'properties'
        self.logger.info(f"{log_prefix}: Completed.")
