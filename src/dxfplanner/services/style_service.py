"""
Service for managing and resolving style configurations.
"""
from typing import Optional, TypeVar, Type, Generic, Union, List
from pydantic import BaseModel
from logging import Logger

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
from dxfplanner.domain.interfaces import IStyleService
from dxfplanner.core.exceptions import DXFPlannerBaseError

logger = get_logger(__name__)

class StyleServiceError(DXFPlannerBaseError):
    """Custom exception for StyleService errors."""
    pass

TBaseModel = TypeVar('TBaseModel', bound=BaseModel)

class StyleService(IStyleService):
    """
    Manages and resolves style configurations for layers and labels.
    Handles presets, inline definitions, and overrides from AppConfig.
    """

    def __init__(self, config: AppConfig, logger: Logger):
        self._config = config
        self.logger = logger

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

        # Ensure the model_type is not None before instantiation to prevent errors with Optional[TBaseModel]
        if merged_data and model_type is not None:
            return model_type(**merged_data)
        return None

    def get_resolved_style_object(
        self,
        preset_name: Optional[str] = None,
        inline_definition: Optional[StyleObjectConfig] = None,
        override_definition: Optional[StyleObjectConfig] = None,
        context_name: Optional[str] = None
    ) -> StyleObjectConfig:
        base_style_source = StyleObjectConfig() # Default empty base
        log_prefix = f"Style for '{context_name}': " if context_name else "Style: "

        if inline_definition:
            base_style_source = inline_definition
            self.logger.debug(f"{log_prefix}Using inline style as base.")
        elif preset_name:
            preset = self._config.style_presets.get(preset_name)
            if preset:
                base_style_source = preset
                self.logger.debug(f"{log_prefix}Using preset '{preset_name}' as base.")
            else:
                self.logger.warning(
                    f"{log_prefix}Style preset '{preset_name}' not found. "
                    f"Using default empty style as base."
                )
        else:
            self.logger.debug(f"{log_prefix}No inline style or preset name. Using default empty style as base.")

        # Now, merge the override onto the determined base_style_source
        final_style = StyleObjectConfig(
            layer_props=LayerDisplayPropertiesConfig(),
            text_props=TextStylePropertiesConfig(),
            hatch_props=HatchPropertiesConfig()
        )

        final_style.layer_props = self._merge_style_component(
            base_style_source.layer_props,
            override_definition.layer_props if override_definition else None,
            LayerDisplayPropertiesConfig,
        ) or LayerDisplayPropertiesConfig()

        final_style.text_props = self._merge_style_component(
            base_style_source.text_props,
            override_definition.text_props if override_definition else None,
            TextStylePropertiesConfig,
        ) or TextStylePropertiesConfig()

        final_style.hatch_props = self._merge_style_component(
            base_style_source.hatch_props,
            override_definition.hatch_props if override_definition else None,
            HatchPropertiesConfig,
        ) or HatchPropertiesConfig()

        if override_definition:
            self.logger.debug(f"{log_prefix}Applied style overrides.")

        # Ensure all components exist, even if default
        if final_style.layer_props is None: final_style.layer_props = LayerDisplayPropertiesConfig()
        if final_style.text_props is None: final_style.text_props = TextStylePropertiesConfig()
        if final_style.hatch_props is None: final_style.hatch_props = HatchPropertiesConfig()

        return final_style

    def get_layer_display_properties(
        self,
        layer_config: LayerConfig
    ) -> LayerDisplayPropertiesConfig:
        resolved_object = self.get_resolved_style_object(
            preset_name=layer_config.style_preset_name,
            inline_definition=layer_config.style_inline_definition,
            override_definition=layer_config.style_override,
            context_name=layer_config.name
        )
        # The resolved_object.layer_props should be non-null due to get_resolved_style_object's logic
        return resolved_object.layer_props if resolved_object.layer_props is not None else LayerDisplayPropertiesConfig()

    def get_text_style_properties(
        self,
        style_reference: Optional[Union[str, StyleObjectConfig, TextStylePropertiesConfig]] = None,
        layer_config_fallback: Optional[LayerConfig] = None
    ) -> TextStylePropertiesConfig:
        context_name = layer_config_fallback.name if layer_config_fallback else "text_style"
        log_prefix = f"Style for '{context_name}': "

        if isinstance(style_reference, TextStylePropertiesConfig):
            self.logger.debug(f"{log_prefix}Using provided TextStylePropertiesConfig directly.")
            return style_reference

        if isinstance(style_reference, str): # Preset name
            self.logger.debug(f"{log_prefix}Resolving from preset name '{style_reference}'.")
            resolved_object = self.get_resolved_style_object(preset_name=style_reference, context_name=context_name)
            if resolved_object.text_props:
                return resolved_object.text_props
            self.logger.warning(f"{log_prefix}Preset '{style_reference}' did not yield text properties.")

        elif isinstance(style_reference, StyleObjectConfig): # Inline StyleObjectConfig
            self.logger.debug(f"{log_prefix}Resolving from provided StyleObjectConfig.")
            # We treat this StyleObjectConfig as a complete definition, not needing presets or overrides from elsewhere here.
            resolved_object = self.get_resolved_style_object(inline_definition=style_reference, context_name=context_name)
            if resolved_object.text_props:
                return resolved_object.text_props
            self.logger.debug(f"{log_prefix}Provided StyleObjectConfig did not yield text properties.")

        # Fallback to layer_config_fallback
        if layer_config_fallback:
            self.logger.debug(f"{log_prefix}Falling back to layer_config '{layer_config_fallback.name}' for text properties.")
            layer_style_object = self.get_resolved_style_object(
                preset_name=layer_config_fallback.style_preset_name,
                inline_definition=layer_config_fallback.style_inline_definition,
                override_definition=layer_config_fallback.style_override,
                context_name=layer_config_fallback.name
            )
            if layer_style_object.text_props:
                return layer_style_object.text_props

        self.logger.debug(f"{log_prefix}No specific text style found, returning default TextStylePropertiesConfig.")
        return TextStylePropertiesConfig()

    def get_hatch_properties(
        self,
        style_reference: Optional[Union[str, StyleObjectConfig, HatchPropertiesConfig]] = None,
        layer_config_fallback: Optional[LayerConfig] = None
    ) -> HatchPropertiesConfig:
        context_name = layer_config_fallback.name if layer_config_fallback else "hatch_style"
        log_prefix = f"Style for '{context_name}': "

        if isinstance(style_reference, HatchPropertiesConfig):
            self.logger.debug(f"{log_prefix}Using provided HatchPropertiesConfig directly.")
            return style_reference

        if isinstance(style_reference, str): # Preset name
            self.logger.debug(f"{log_prefix}Resolving from preset name '{style_reference}'.")
            resolved_object = self.get_resolved_style_object(preset_name=style_reference, context_name=context_name)
            if resolved_object.hatch_props:
                return resolved_object.hatch_props
            self.logger.warning(f"{log_prefix}Preset '{style_reference}' did not yield hatch properties.")

        elif isinstance(style_reference, StyleObjectConfig): # Inline StyleObjectConfig
            self.logger.debug(f"{log_prefix}Resolving from provided StyleObjectConfig.")
            resolved_object = self.get_resolved_style_object(inline_definition=style_reference, context_name=context_name)
            if resolved_object.hatch_props:
                return resolved_object.hatch_props
            self.logger.debug(f"{log_prefix}Provided StyleObjectConfig did not yield hatch properties.")

        # Fallback to layer_config_fallback
        if layer_config_fallback:
            self.logger.debug(f"{log_prefix}Falling back to layer_config '{layer_config_fallback.name}' for hatch properties.")
            layer_style_object = self.get_resolved_style_object(
                preset_name=layer_config_fallback.style_preset_name,
                inline_definition=layer_config_fallback.style_inline_definition,
                override_definition=layer_config_fallback.style_override,
                context_name=layer_config_fallback.name
            )
            if layer_style_object.hatch_props:
                return layer_style_object.hatch_props

        self.logger.debug(f"{log_prefix}No specific hatch style found, returning default HatchPropertiesConfig.")
        return HatchPropertiesConfig()

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
