"""
Service for managing and resolving style configurations.
"""
from typing import Optional, TypeVar, Type, Generic
from pydantic import BaseModel

from dxfplanner.config.schemas import (
    AppConfig,
    LayerConfig,
    StyleObjectConfig,
    LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig,
    TextParagraphPropertiesConfig,
    HatchPropertiesConfig,
    LabelingConfig,
)
from dxfplanner.core.exceptions import DXFPlannerBaseError
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class StyleServiceError(DXFPlannerBaseError):
    """Custom exception for StyleService errors."""
    pass

TBaseModel = TypeVar('TBaseModel', bound=BaseModel)

class StyleService:
    """
    Manages and resolves style configurations for layers and labels.
    Handles presets, inline definitions, and overrides from AppConfig.
    """

    def __init__(self, config: AppConfig):
        self._config = config

    def _merge_style_component(
        self,
        base: Optional[TBaseModel],
        override: Optional[TBaseModel],
        model_type: Type[TBaseModel],
    ) -> Optional[TBaseModel]:
        """
        Merges two style component Pydantic models (e.g., LayerDisplayPropertiesConfig).
        Override fields take precedence. Handles nested TextParagraphPropertiesConfig
        within TextStylePropertiesConfig.
        """
        if not base and not override:
            return None

        base_dict = base.model_dump() if base else {}
        override_dict = override.model_dump(exclude_unset=True) if override else {}

        # Initial shallow merge for most fields
        merged_data = {**base_dict, **override_dict}

        if model_type is TextStylePropertiesConfig:
            # Explicitly merge TextParagraphPropertiesConfig if present
            base_pp = base.paragraph_props if base and hasattr(base, 'paragraph_props') else None
            override_pp = override.paragraph_props if override and hasattr(override, 'paragraph_props') else None

            resolved_pp = self._merge_style_component(
                base_pp,
                override_pp,
                TextParagraphPropertiesConfig
            )
            if resolved_pp:
                merged_data['paragraph_props'] = resolved_pp.model_dump()
            elif 'paragraph_props' in merged_data: # if override explicitly set it to None
                 merged_data['paragraph_props'] = None


        return model_type(**merged_data) if merged_data else None


    def get_resolved_layer_style(self, layer_config: LayerConfig) -> StyleObjectConfig:
        """
        Resolves the final StyleObjectConfig for a layer based on its configuration,
        considering inline definitions, presets, and overrides.

        Precedence:
        1. Inline definition (`style_inline_definition`) is used as the base.
        2. If no inline definition, preset (`style_preset_name`) is used as the base.
        3. If neither, an empty StyleObjectConfig is the base.
        4. `style_override` is then merged on top of this determined base.
        """
        base_style_source = StyleObjectConfig() # Default empty base

        if layer_config.style_inline_definition:
            base_style_source = layer_config.style_inline_definition
            logger.debug(f"Layer '{layer_config.name}': Using inline style as base.")
        elif layer_config.style_preset_name:
            preset = self._config.style_presets.get(layer_config.style_preset_name)
            if preset:
                base_style_source = preset
                logger.debug(f"Layer '{layer_config.name}': Using preset '{layer_config.style_preset_name}' as base.")
            else:
                logger.warning(
                    f"Layer '{layer_config.name}': Style preset '{layer_config.style_preset_name}' not found. "
                    f"Using default empty style as base."
                )
        else:
            logger.debug(f"Layer '{layer_config.name}': No inline style or preset name. Using default empty style as base.")

        # Now, merge the override onto the determined base_style_source
        final_style = StyleObjectConfig()
        override_source = layer_config.style_override

        final_style.layer_props = self._merge_style_component(
            base_style_source.layer_props,
            override_source.layer_props if override_source else None,
            LayerDisplayPropertiesConfig,
        )
        final_style.text_props = self._merge_style_component(
            base_style_source.text_props,
            override_source.text_props if override_source else None,
            TextStylePropertiesConfig,
        )
        final_style.hatch_props = self._merge_style_component(
            base_style_source.hatch_props,
            override_source.hatch_props if override_source else None,
            HatchPropertiesConfig,
        )

        if override_source:
            logger.debug(f"Layer '{layer_config.name}': Applied style overrides.")

        return final_style

    def get_resolved_label_style(
        self, layer_config: LayerConfig
    ) -> Optional[TextStylePropertiesConfig]:
        """
        Resolves the TextStylePropertiesConfig for a layer's labels.
        Considers a text style preset and inline text style properties from LabelingConfig.
        Inline properties override preset properties.
        """
        if not layer_config.labeling:
            return None

        label_conf: LabelingConfig = layer_config.labeling
        base_text_style: Optional[TextStylePropertiesConfig] = TextStylePropertiesConfig() # Default empty

        if label_conf.text_style_preset_name:
            style_preset_obj = self._config.style_presets.get(label_conf.text_style_preset_name)
            if style_preset_obj and style_preset_obj.text_props:
                base_text_style = style_preset_obj.text_props
                logger.debug(
                    f"Layer '{layer_config.name}' labeling: "
                    f"Using text_props from preset '{label_conf.text_style_preset_name}'."
                )
            else:
                logger.warning(
                    f"Layer '{layer_config.name}' labeling: Text style preset "
                    f"'{label_conf.text_style_preset_name}' or its text_props not found. "
                    f"Using default empty text style as base for labeling."
                )

        # Merge inline definition over the (potentially preset-derived) base
        resolved_label_style = self._merge_style_component(
            base_text_style,
            label_conf.text_style_inline,
            TextStylePropertiesConfig
        )

        if label_conf.text_style_inline:
             logger.debug(f"Layer '{layer_config.name}' labeling: Applied inline text style properties.")

        # Ensure we return an instance if any styling was determined, or None if completely empty
        # If resolved_label_style contains any non-default values, return it.
        if resolved_label_style and resolved_label_style.model_dump(exclude_defaults=True):
            return resolved_label_style

        # If inline was not provided, and base_text_style (from preset) had non-default values.
        if not label_conf.text_style_inline and base_text_style and base_text_style.model_dump(exclude_defaults=True):
            return base_text_style

        return None # Effectively no specific label styling found or only defaults.
