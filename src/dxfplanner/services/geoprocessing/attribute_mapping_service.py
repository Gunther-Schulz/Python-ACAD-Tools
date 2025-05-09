from typing import Dict, Any, Optional

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IAttributeMapper
from dxfplanner.config.schemas import AttributeMappingServiceConfig # For config injection
from dxfplanner.geometry.utils import sanitize_layer_name # For layer name sanitization
from dxfplanner.core.logging_config import get_logger # If logging is needed

logger = get_logger(__name__)

class AttributeMappingService(IAttributeMapper):
    """Service for mapping GeoFeature attributes to DXF entity properties based on simple config."""

    def __init__(self, config: AttributeMappingServiceConfig):
        self.config = config

    def get_dxf_layer_for_feature(self, feature: GeoFeature) -> str:
        """
        Determines the DXF layer name for a given GeoFeature based on its attributes
        and mapping rules defined in the configuration.
        """
        layer_name_candidate: Optional[str] = None
        if self.config.attribute_for_layer and self.config.attribute_for_layer in feature.properties:
            attr_val = feature.properties[self.config.attribute_for_layer]
            if attr_val is not None: # Ensure attribute value is not None
                raw_name = str(attr_val)
                if raw_name.strip(): # Ensure not empty or just whitespace
                    layer_name_candidate = sanitize_layer_name(raw_name)
                else:
                    logger.debug(f"Attribute '{self.config.attribute_for_layer}' for layer name is empty or whitespace. Feature ID: {feature.id if feature.id is not None else 'N/A'}")
            else:
                logger.debug(f"Attribute '{self.config.attribute_for_layer}' for layer name is None. Feature ID: {feature.id if feature.id is not None else 'N/A'}")

        if layer_name_candidate:
            return layer_name_candidate
        else:
            logger.debug(f"Falling back to default layer name '{self.config.default_dxf_layer_on_mapping_failure}' for feature ID: {feature.id if feature.id is not None else 'N/A'}")
            return self.config.default_dxf_layer_on_mapping_failure

    def get_dxf_properties_for_feature(self, feature: GeoFeature) -> Dict[str, Any]:
        """
        Determines DXF visual properties (e.g., color, text content/style)
        for a GeoFeature based on its attributes and mapping rules.
        Output keys should match DxfEntity model fields where possible (e.g., 'color', 'text_content', 'height').
        """
        dxf_props: Dict[str, Any] = {}

        # Use feature.properties as per GeoFeature model definition
        # Color mapping (expects ACI int from attribute)
        if self.config.attribute_for_color and self.config.attribute_for_color in feature.properties:
            color_val = feature.properties[self.config.attribute_for_color]
            if isinstance(color_val, int):
                dxf_props['color'] = color_val  # ACI color index
            elif color_val is not None: # Handles non-int, non-None values. RGB tuple case removed for simplicity here based on previous logging.
                logger.warning(
                    f"Attribute '{self.config.attribute_for_color}' for color has value '{color_val}' (type: {type(color_val)}), "
                    f"but an ACI integer was expected. Skipping color mapping. Feature ID: {feature.id if feature.id is not None else 'N/A'}"
                )

        # Text content mapping
        if self.config.attribute_for_text_content and self.config.attribute_for_text_content in feature.properties:
            text_val = feature.properties[self.config.attribute_for_text_content]
            if text_val is not None:
                dxf_props['text_content'] = str(text_val)
            else:
                logger.debug(f"Attribute '{self.config.attribute_for_text_content}' for text_content is None. Feature ID: {feature.id if feature.id is not None else 'N/A'}")

        # Text height mapping
        if self.config.attribute_for_text_height and self.config.attribute_for_text_height in feature.properties:
            height_attr_val = feature.properties[self.config.attribute_for_text_height]
            try:
                height_val = float(height_attr_val)
                if height_val > 0:
                    dxf_props['height'] = height_val
                else:
                    logger.warning(
                        f"Attribute '{self.config.attribute_for_text_height}' for text height has non-positive value {height_val}. "
                        f"Skipping height mapping. Feature ID: {feature.id if feature.id is not None else 'N/A'}"
                    )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Could not parse text height from attribute '{self.config.attribute_for_text_height}' (value: '{height_attr_val}'): {e}. "
                    f"Skipping height mapping. Feature ID: {feature.id if feature.id is not None else 'N/A'}"
                )

        return dxf_props
