"""
Service for managing and resolving style configurations.
"""
from typing import Optional, Union, List, Dict, Any
from pydantic import BaseModel # Keep if StyleObjectConfig or others are directly returned/typed
from logging import Logger
# Removed: import re, TypeVar, Type, Generic
from ezdxf.document import Drawing

from dxfplanner.config.schemas import (
    ProjectConfig,
    LayerConfig,
    LabelPlacementOperationConfig,
)
from dxfplanner.config.style_schemas import (
    StyleObjectConfig,
    LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig,
    HatchPropertiesConfig,
    # StyleRuleConfig # No longer directly used here
)
from dxfplanner.domain.interfaces import IStyleService
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.core.exceptions import DXFPlannerBaseError
from dxfplanner.core.logging_config import get_logger

# Import new styling services
from dxfplanner.services.styling.preset_resolver_service import PresetResolverService
from dxfplanner.services.styling.rule_evaluator_service import RuleEvaluatorService
from dxfplanner.services.styling.dxf_style_definition_service import DxfStyleDefinitionService
# from dxfplanner.services.styling.font_provider_service import FontProviderService # REMOVED
from dxfplanner.services.styling.styling_utils import merge_style_components # For get_resolved_feature_style merge

logger = get_logger(__name__) # Keep logger instance for StyleService itself if it does any logging

class StyleServiceError(DXFPlannerBaseError):
    """Custom exception for StyleService errors."""
    pass

# Removed: TBaseModel = TypeVar('TBaseModel', bound=BaseModel)

class StyleService(IStyleService):
    """
    Acts as a facade to manage and resolve style configurations for layers and labels.
    Delegates specific tasks to specialized styling services.
    Handles presets, inline definitions, overrides, and feature-specific style rules.
    """

    def __init__(self, config: ProjectConfig, logger_instance: Logger): # Renamed logger to logger_instance to avoid conflict
        self._config = config # Keep ProjectConfig if needed by StyleService directly or for passing to sub-services
        self.logger = logger_instance # Use the passed logger

        # Instantiate new services
        # font_dirs = getattr(self._config, 'font_directories', []) # REMOVED
        # if not font_dirs and hasattr(self._config, 'general_settings') and hasattr(self._config.general_settings, 'font_dirs'): # REMOVED
        #     font_dirs = self._config.general_settings.font_dirs or [] # REMOVED

        self.preset_resolver_service = PresetResolverService(project_config=self._config, logger=self.logger)
        self.rule_evaluator_service = RuleEvaluatorService(logger=self.logger)
        self.dxf_style_definition_service = DxfStyleDefinitionService(logger=self.logger)
        # self.font_provider_service = FontProviderService(font_directories=font_dirs, logger=self.logger) # REMOVED

    # Removed: _evaluate_condition (moved to RuleEvaluatorService)
    # Removed: _merge_style_component (logic now in styling_utils.merge_style_components, used by PresetResolverService)

    def get_resolved_style_object(
        self,
        preset_name: Optional[str] = None,
        inline_definition: Optional[StyleObjectConfig] = None,
        override_definition: Optional[StyleObjectConfig] = None, # override_definition is not directly used by PresetResolverService's core resolve
                                                                 # it's typically for feature rules or direct layer overrides
        context_name: Optional[str] = None
    ) -> StyleObjectConfig:
        log_prefix = f"StyleService for '{context_name}': " if context_name else "StyleService: "
        self.logger.debug(f"{log_prefix}Resolving style object. Preset: '{preset_name}', Inline given: {bool(inline_definition)}, Override given: {bool(override_definition)}")

        # Step 1: Resolve base style from preset and/or inline definition
        base_style = self.preset_resolver_service.resolve_preset_and_inline(
            preset_name=preset_name,
            inline_definition=inline_definition,
            context_name=f"{context_name} (base/inline)"
        )
        self.logger.debug(f"{log_prefix}Base style (from preset/inline): {base_style.model_dump_json(indent=2)}")

        # Step 2: Apply override_definition if provided
        if override_definition:
            final_style = merge_style_components(
                model_cls=StyleObjectConfig,
                base=base_style,
                override=override_definition
            )
            self.logger.debug(f"{log_prefix}Applied override. Final style: {final_style.model_dump_json(indent=2)}")
            return final_style

        self.logger.debug(f"{log_prefix}No override. Final style: {base_style.model_dump_json(indent=2)}")
        return base_style

    def get_layer_display_properties(
        self,
        layer_config: LayerConfig
    ) -> LayerDisplayPropertiesConfig:
        resolved_object = self.get_resolved_style_object(
            preset_name=layer_config.style_preset_name,
            inline_definition=layer_config.style_inline_definition,
            override_definition=layer_config.style_override, # This is the layer-level override
            context_name=f"LayerConfig: {layer_config.name}"
        )
        return resolved_object.layer_props if resolved_object.layer_props is not None else LayerDisplayPropertiesConfig()

    def get_text_style_properties(
        self,
        style_reference: Optional[Union[str, StyleObjectConfig, TextStylePropertiesConfig]] = None,
        layer_config_fallback: Optional[LayerConfig] = None,
        preset_already_resolved: bool = False,
        _current_recursion_depth: int = 0,
        _original_context_for_recursion_log: Optional[str] = None
    ) -> TextStylePropertiesConfig:
        context_name = layer_config_fallback.name if layer_config_fallback else "text_style"
        log_prefix = f"StyleService.get_text_style_properties for '{context_name}': "
        self.logger.debug(f"{log_prefix}Input style_reference type: {type(style_reference)}")

        text_props_to_return: Optional[TextStylePropertiesConfig] = None

        # Path 1: Direct TextStylePropertiesConfig provided
        if isinstance(style_reference, TextStylePropertiesConfig):
            self.logger.debug(f"{log_prefix}Using provided TextStylePropertiesConfig directly.")
            text_props_to_return = style_reference.model_copy(deep=True) # Work on a copy

        # Path 2: Resolve from preset name (str) or inline StyleObjectConfig
        elif isinstance(style_reference, str) or isinstance(style_reference, StyleObjectConfig):
            preset_name_for_soc = style_reference if isinstance(style_reference, str) else None
            inline_soc_def = style_reference if isinstance(style_reference, StyleObjectConfig) else None

            resolved_soc_from_ref = self.preset_resolver_service.resolve_preset_and_inline(
                preset_name=preset_name_for_soc,
                inline_definition=inline_soc_def,
                context_name=f"{context_name} (from style_reference)"
            )
            if resolved_soc_from_ref and resolved_soc_from_ref.text_props:
                text_props_to_return = resolved_soc_from_ref.text_props.model_copy(deep=True)
            elif resolved_soc_from_ref: # resolved_soc_from_ref exists but .text_props is None
                self.logger.debug(f"{log_prefix}Resolved StyleObjectConfig from reference '{style_reference}' did not yield text_props.")
            # If resolved_soc_from_ref is None (preset not found and no inline), text_props_to_return remains None

        # Path 3: Fallback to layer_config_fallback if text_props_to_return is still None
        if text_props_to_return is None and layer_config_fallback:
            self.logger.debug(f"{log_prefix}Falling back to layer_config '{layer_config_fallback.name}'.")
            base_layer_soc = self.preset_resolver_service.resolve_preset_and_inline(
                preset_name=layer_config_fallback.style_preset_name,
                inline_definition=layer_config_fallback.style_inline_definition,
                context_name=f"{layer_config_fallback.name} (fallback base)"
            )
            # Apply layer_config's override to the resolved base
            final_layer_soc = merge_style_components(
                model_cls=StyleObjectConfig,
                base=base_layer_soc, # This can be None if preset/inline also not found
                override=layer_config_fallback.style_override
            )
            if final_layer_soc and final_layer_soc.text_props:
                text_props_to_return = final_layer_soc.text_props.model_copy(deep=True)
            else: # final_layer_soc is None or has no text_props
                self.logger.debug(f"{log_prefix}Layer fallback for '{layer_config_fallback.name}' did not yield text_props.")

        # If we have a TextStylePropertiesConfig by now
        if text_props_to_return:
            # New simplified logging
            if text_props_to_return.font_name_or_style_preset:
                self.logger.debug(f"{log_prefix}Font name/preset '{text_props_to_return.font_name_or_style_preset}' will be used directly by ezdxf.")
            else:
                self.logger.debug(f"{log_prefix}No font_name_or_style_preset specified; ezdxf will use default.")

            self.logger.debug(f"{log_prefix}Returning resolved: {text_props_to_return.model_dump_json(exclude_none=True, indent=2)}")
            return text_props_to_return

        self.logger.debug(f"{log_prefix}No specific text style found, returning default TextStylePropertiesConfig.")
        return TextStylePropertiesConfig()

    def get_hatch_properties(
        self,
        style_reference: Optional[Union[str, StyleObjectConfig, HatchPropertiesConfig]] = None,
        layer_config_fallback: Optional[LayerConfig] = None
    ) -> HatchPropertiesConfig:
        context_name = layer_config_fallback.name if layer_config_fallback else "hatch_style"
        log_prefix = f"StyleService.get_hatch_properties for '{context_name}': "

        if isinstance(style_reference, HatchPropertiesConfig):
            self.logger.debug(f"{log_prefix}Using provided HatchPropertiesConfig directly.")
            # Unlike text, hatch doesn't have a secondary resolution step like font files.
            return style_reference

        base_style_object_for_hatch: Optional[StyleObjectConfig] = None
        preset_name_for_hatch: Optional[str] = None

        if isinstance(style_reference, str): # Preset name for a StyleObjectConfig
            preset_name_for_hatch = style_reference
        elif isinstance(style_reference, StyleObjectConfig): # Inline StyleObjectConfig
            base_style_object_for_hatch = style_reference

        if preset_name_for_hatch or base_style_object_for_hatch:
            resolved_style_object = self.preset_resolver_service.resolve_preset_and_inline(
                preset_name=preset_name_for_hatch,
                inline_definition=base_style_object_for_hatch,
                context_name=f"{context_name} (from style_reference)"
            )
            if resolved_style_object.hatch_props:
                return resolved_style_object.hatch_props
            self.logger.debug(f"{log_prefix}Resolved StyleObjectConfig from reference did not yield hatch_props.")

        if layer_config_fallback:
            self.logger.debug(f"{log_prefix}Falling back to layer_config '{layer_config_fallback.name}'.")
            layer_style_object = self.get_resolved_style_object(
                preset_name=layer_config_fallback.style_preset_name,
                inline_definition=layer_config_fallback.style_inline_definition,
                override_definition=layer_config_fallback.style_override,
                context_name=f"{layer_config_fallback.name} (fallback)"
            )
            if layer_style_object.hatch_props:
                return layer_style_object.hatch_props
            self.logger.debug(f"{log_prefix}Layer fallback did not yield hatch_props.")

        self.logger.debug(f"{log_prefix}No specific hatch style found, returning default HatchPropertiesConfig.")
        return HatchPropertiesConfig()

    def get_resolved_style_for_label_operation(
        self, config: LabelPlacementOperationConfig
    ) -> TextStylePropertiesConfig:
        self.logger.debug(
            f"Resolving text style for LabelPlacementOperation: Output='{config.output_label_layer_name}', Source='{config.source_layer}'"
        )

        # preset_name_from_label: Optional[str] = None # No longer needed with get_text_style_properties
        inline_text_style_from_label_settings: Optional[TextStylePropertiesConfig] = None

        if config.label_settings and config.label_settings.text_style:
            self.logger.debug(
                f"Input text_style from LabelPlacementOperationConfig.label_settings: "
                f"{config.label_settings.text_style.model_dump_json(exclude_none=True, indent=2)}"
            )
            inline_text_style_from_label_settings = config.label_settings.text_style
            # preset_name_from_label = config.label_settings.text_style.font_name_or_style_preset # Not directly used like this

        # Call the corrected get_text_style_properties.
        # If inline_text_style_from_label_settings is None, get_text_style_properties will provide a default.
        resolved_text_props = self.get_text_style_properties(
            style_reference=inline_text_style_from_label_settings
            # layer_config_fallback is not passed here, as this method focuses on LabelOpConfig's own style.
            # context_name=f"LabelOp: {config.output_label_layer_name}" # Removed
        )
        self.logger.debug(f"StyleService.get_resolved_style_for_label_operation - resolved_text_props: {resolved_text_props.model_dump_json(indent=2)}")
        return resolved_text_props

    def get_resolved_feature_style(self, geo_feature: GeoFeature, layer_config: LayerConfig) -> StyleObjectConfig:
        context_name = f"Feature ID {geo_feature.id or 'N/A'} on layer {layer_config.name}" # context_name for this method's logging
        self.logger.debug(f"Resolving feature style for: {context_name}")

        # 1. Get base style for the layer using the main resolver
        current_style = self.get_resolved_style_object(
            preset_name=layer_config.style_preset_name,
            inline_definition=layer_config.style_inline_definition,
            override_definition=layer_config.style_override, # Layer-level override
            context_name=f"Base for layer {layer_config.name}"
        )
        self.logger.debug(f"Initial style for {context_name} (from layer defaults): {current_style.model_dump_json(indent=2)}")

        sorted_rules = sorted(layer_config.style_rules, key=lambda r: (r.priority, r.name or ""))

        if sorted_rules:
            self.logger.debug(f"Applying {len(sorted_rules)} style rules for {context_name}, sorted by priority: {[r.name or 'Unnamed' for r in sorted_rules]}")

        for rule in sorted_rules:
            rule_name = rule.name or f"Condition({rule.condition})"
            self.logger.debug(f"Evaluating rule '{rule_name}' (Priority: {rule.priority}) for {context_name}")

            if self.rule_evaluator_service.evaluate_condition(rule.condition, geo_feature.attributes):
                self.logger.info(f"Rule '{rule_name}' condition MET for {context_name}. Applying override: {rule.style_override.model_dump_json(indent=2)}")

                # Merge rule's style_override onto current_style
                # We use the utility function here directly as PresetResolverService handles preset/inline,
                # and here we are applying a specific override on an already resolved StyleObjectConfig.
                current_style = merge_style_components(
                    model_cls=StyleObjectConfig,
                    base=current_style,
                    override=rule.style_override
                )
                self.logger.debug(f"Style after applying rule '{rule_name}' for {context_name}: {current_style.model_dump_json(indent=2)}")

                if rule.terminate:
                    self.logger.info(f"Rule '{rule_name}' has terminate=True. No further style rules will be processed for {context_name}.")
                    break
            else:
                self.logger.debug(f"Rule '{rule_name}' condition NOT MET for {context_name}.")

        # Final resolution of text properties within the potentially modified current_style
        # This ensures that if a rule changed text_props (e.g. set a new font_name_or_style_preset),
        # the resolved_font_filename is correctly populated.
        if current_style.text_props:
            self.logger.debug(f"Post-rules, text_props before final re-resolution: {current_style.text_props.model_dump_json(indent=2)}")
            # Corrected call: Use the class's own get_text_style_properties method
            current_style.text_props = self.get_text_style_properties(
                style_reference=current_style.text_props, # Pass the existing text_props as reference
                layer_config_fallback=layer_config # Pass layer_config for context within get_text_style_properties
                # context_name=f"{context_name} (post-rules text finalization)" # Removed
            )
            self.logger.debug(f"Post-rules, text_props AFTER final re-resolution: {current_style.text_props.model_dump_json(indent=2)}")


        self.logger.debug(f"Final resolved style for {context_name}: {current_style.model_dump_json(indent=2)}")
        return current_style

    # Removed: _resolve_text_style_from_preset_and_inline (moved to PresetResolverService)

    def create_styles_in_dxf_doc(self, doc: Drawing, style_presets_config: Optional[Dict[str, StyleObjectConfig]]) -> None:
        """
        Populates the DXF STYLE table from the style presets defined in the configuration.
        Delegates to DxfStyleDefinitionService.
        """
        if not style_presets_config: # Or use self._config.style_presets
            self.logger.info("No style presets provided or found in config. Skipping STYLE table population from presets.")
            return

        presets_to_process = style_presets_config # Or self._config.style_presets

        self.logger.info(f"Populating STYLE table from {len(presets_to_process)} presets...")
        for preset_name, preset_obj_config in presets_to_process.items():
            if preset_obj_config.text_style:
                # We need fully resolved TextStylePropertiesConfig, especially resolved_font_filename
                # The preset_obj_config.text_style might just be a starting point or refer to another preset.
                # So, we use PresetResolverService to get the final TextStylePropertiesConfig for this preset.

                # If preset_name itself IS the font_name_or_style_preset for its own text_style component,
                # OR if the text_style component refers to another preset, resolve_text_style handles it.
                # We effectively treat the 'preset_name' as the primary key for the style to be created in DXF.
                # The text_style component *within* that preset_obj_config is what defines its properties.

                # Corrected call: Use the class's own get_text_style_properties method
                fully_resolved_text_props = self.get_text_style_properties(
                    style_reference=preset_obj_config.text_style, # Pass the TextStylePropertiesConfig component
                    # layer_config_fallback is not relevant here
                    # context_name=f"DXF Style Creation for Preset '{preset_name}'" # Removed
                )

                self.logger.debug(f"For DXF STYLE table, preset '{preset_name}', its text_style resolved to: {fully_resolved_text_props.model_dump_json(indent=2)}")

                # Changed condition: Attempt to create if we have any resolved text properties.
                # DxfStyleDefinitionService will handle if font filename is None.
                if fully_resolved_text_props:
                    self.dxf_style_definition_service.ensure_text_style_in_dxf(
                        doc=doc,
                        style_name=preset_name, # The DXF STYLE entry will use the original preset_name
                        text_props=fully_resolved_text_props
                    )
                else:
                    # This warning now means that even after trying to resolve, we got no text_props at all.
                    self.logger.warning(f"Preset '{preset_name}' text_style could not be resolved to TextStyleProperties. Skipping DXF STYLE creation for it.")
            else:
                self.logger.debug(f"Preset '{preset_name}' does not define a text_style. Skipping DXF STYLE creation for it.")

    # Removed: _create_and_add_text_style_to_doc_if_not_exists (logic moved to DxfStyleDefinitionService)

# Ensure all old private methods are removed if their logic is now fully in sub-services.
# e.g., _get_resolved_font_filename was part of the old _resolve_text_style_from_preset_and_inline,
# that logic is now encapsulated within PresetResolverService.resolve_text_style.
