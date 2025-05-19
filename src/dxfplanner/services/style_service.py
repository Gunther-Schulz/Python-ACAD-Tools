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

MAX_RECURSION_DEPTH = 10 # ADDED CONSTANT

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

        # Path 1: style_reference is a preset name (string) for a StyleObjectConfig
        # or style_reference is a TextStylePropertiesConfig that might contain a preset name
        if isinstance(style_reference, str) or isinstance(style_reference, StyleObjectConfig):
            preset_name_for_soc = style_reference if isinstance(style_reference, str) else None
            inline_soc_def = style_reference if isinstance(style_reference, StyleObjectConfig) else None

            resolved_soc_from_ref = self.preset_resolver_service.resolve_preset_and_inline(
                preset_name=preset_name_for_soc,
                inline_definition=inline_soc_def,
                context_name=f"{context_name} (from style_reference)"
            )
            if resolved_soc_from_ref and resolved_soc_from_ref.text_props:
                text_props_to_return = resolved_soc_from_ref.text_props.model_copy(deep=True)
                # ADDED DEBUG LOG 1
                if text_props_to_return:
                    self.logger.debug(f"{log_prefix}After model_copy from SOC_ref.text_props: text_props_to_return.rotation_degrees = {text_props_to_return.rotation_degrees}")
                else:
                    self.logger.debug(f"{log_prefix}After model_copy, text_props_to_return is None - THIS IS UNEXPECTED.")

            elif resolved_soc_from_ref: # resolved_soc_from_ref exists but .text_props is None
                self.logger.debug(f"{log_prefix}Resolved StyleObjectConfig from reference '{style_reference}' did not yield text_props.")
            # If resolved_soc_from_ref is None (preset not found and no inline), text_props_to_return remains None

        # Path 2: style_reference is already a TextStylePropertiesConfig instance
        # This is the most common path from LabelPlacementOperationConfig or rule overrides.
        elif isinstance(style_reference, TextStylePropertiesConfig):
            self.logger.debug(f"{log_prefix}Using provided TextStylePropertiesConfig directly as base.")
            text_props_to_return = style_reference.model_copy(deep=True)

            # If this TextStylePropertiesConfig itself refers to a StyleObjectConfig preset (e.g. "StandardLegend"), resolve it
            font_preset_ref_in_tsprops = text_props_to_return.font_name_or_style_preset

            # ADDED/MODIFIED BLOCK START: Handle case where font_name_or_style_preset is None in the input TSP
            if font_preset_ref_in_tsprops is None:
                self.logger.debug(f"{log_prefix}Input TextStylePropertiesConfig has font_name_or_style_preset=None. Defaulting to DXF style 'Standard'.")
                text_props_to_return.font_name_or_style_preset = "Standard"
            # END ADDED/MODIFIED BLOCK

            # Check if the (potentially now "Standard" or originally present) font_preset_ref_in_tsprops
            # refers to a StyleObjectConfig preset in project_config.style_presets
            elif font_preset_ref_in_tsprops and font_preset_ref_in_tsprops in self.preset_resolver_service.project_config.style_presets:
                self.logger.debug(f"{log_prefix}TextStylePropertiesConfig refers to StyleObjectConfig preset '{font_preset_ref_in_tsprops}'. Resolving its text_props component.")
                soc_preset = self.preset_resolver_service.resolve_preset_and_inline(
                    preset_name=font_preset_ref_in_tsprops,
                    inline_definition=None, # We are resolving the preset referred to by name
                    context_name=f"{log_prefix} (resolving SOC preset '{font_preset_ref_in_tsprops}')"
                )

                if soc_preset and soc_preset.text_props:
                    # Get explicitly set fields from the original input style_reference
                    # style_reference is the input to get_text_style_properties, which is TextStylePropertiesConfig in this path
                    input_explicit_fields = style_reference.model_dump(exclude_unset=True)

                    # Handle font_name_or_style_preset from the resolved SOC preset first
                    nested_font_ref = soc_preset.text_props.font_name_or_style_preset
                    if nested_font_ref is None:
                        self.logger.debug(f"{log_prefix}SOC preset '{font_preset_ref_in_tsprops}' text_props has no nested font/style. Final DXF style name for this path will be 'Standard'.")
                        text_props_to_return.font_name_or_style_preset = "Standard"
                    else:
                        self.logger.debug(f"{log_prefix}SOC preset '{font_preset_ref_in_tsprops}' text_props specify nested font/style: '{nested_font_ref}'. Using this.")
                        text_props_to_return.font_name_or_style_preset = nested_font_ref

                    # Merge other properties: if explicitly set in input, keep input; otherwise, take from preset.
                    # Note: text_props_to_return started as a copy of style_reference.
                    if "height" not in input_explicit_fields:
                        text_props_to_return.height = soc_preset.text_props.height
                    if "width_factor" not in input_explicit_fields:
                        text_props_to_return.width_factor = soc_preset.text_props.width_factor
                    if "oblique_angle" not in input_explicit_fields:
                        text_props_to_return.oblique_angle = soc_preset.text_props.oblique_angle
                    if "rotation_degrees" not in input_explicit_fields:
                        text_props_to_return.rotation_degrees = soc_preset.text_props.rotation_degrees
                        self.logger.debug(f"{log_prefix}Rotation from preset '{font_preset_ref_in_tsprops}' ({soc_preset.text_props.rotation_degrees}) applied as input did not specify it.")
                    elif "rotation_degrees" in input_explicit_fields: # Log if input explicitly set it
                        self.logger.debug(f"{log_prefix}Rotation from input TextStylePropertiesConfig ({style_reference.rotation_degrees}) kept as it was explicitly set.")

                    if "color" not in input_explicit_fields:
                        text_props_to_return.color = soc_preset.text_props.color
                    if "mtext_width" not in input_explicit_fields:
                        text_props_to_return.mtext_width = soc_preset.text_props.mtext_width
                    if "halign" not in input_explicit_fields:
                        text_props_to_return.halign = soc_preset.text_props.halign
                    if "valign" not in input_explicit_fields:
                        text_props_to_return.valign = soc_preset.text_props.valign
                    if "attachment_point" not in input_explicit_fields:
                        text_props_to_return.attachment_point = soc_preset.text_props.attachment_point

                    if "paragraph_props" not in input_explicit_fields:
                        # Make a deep copy if taking from preset to avoid shared mutable objects
                        text_props_to_return.paragraph_props = soc_preset.text_props.paragraph_props.model_copy(deep=True) if soc_preset.text_props.paragraph_props else {}
                    # Ensure paragraph_props is not None (even if taken from preset or input)
                    if text_props_to_return.paragraph_props is None:
                         text_props_to_return.paragraph_props = {}

                else: # soc_preset not found or no text_props
                    self.logger.debug(f"{log_prefix}StyleObjectConfig preset '{font_preset_ref_in_tsprops}' not found or has no text_props. Font reference '{font_preset_ref_in_tsprops}' might be a direct DXF style name or error.")

            # Fallback for current_font_ref (potentially updated to "Standard" or from SOC preset)
            # This part is for daisy-chaining StyleObjectConfig presets, less critical for the "Standard" case if handled above.
            # It might be simplified or removed if the above logic correctly sets "Standard" when needed.
            # The recursive call to get_text_style_properties for current_font_ref if it's a SOC preset:
            current_font_ref = text_props_to_return.font_name_or_style_preset
            if current_font_ref and \
               current_font_ref != "Standard" and \
               not preset_already_resolved and \
               _current_recursion_depth < MAX_RECURSION_DEPTH and \
               current_font_ref in self.preset_resolver_service.project_config.style_presets:
                 self.logger.debug(f"{log_prefix}Current font_name_or_style_preset '{current_font_ref}' refers to another StyleObjectConfig preset. Resolving recursively.")
                 recursive_text_props = self.get_text_style_properties(
                     style_reference=current_font_ref, # This is the name of the SOC preset
                     layer_config_fallback=layer_config_fallback,
                     preset_already_resolved=False, # Allow further resolution
                     _current_recursion_depth=_current_recursion_depth + 1,
                     _original_context_for_recursion_log=_original_context_for_recursion_log # Propagate
                 )
                 # Merge the recursively resolved properties, text_props_to_return (which was the original input TSP) takes precedence for its defined fields
                 text_props_to_return.font_name_or_style_preset = recursive_text_props.font_name_or_style_preset if recursive_text_props.font_name_or_style_preset is not None else text_props_to_return.font_name_or_style_preset
                 # text_props_to_return will keep its original height, width_factor etc. unless they were None.
                 # The recursive call was primarily to ensure the font_name_or_style_preset from the *nested* SOC is correctly resolved.
                 # If the nested SOC ultimately resolves to 'Standard' or a direct font file, that's what we wanted.
                 # The attributes like height, etc., from the *outermost* TextStylePropertiesConfig (the original style_reference) should win.
                 # So, only update font_name_or_style_preset from the recursive call.
                 text_props_to_return.font_name_or_style_preset = recursive_text_props.font_name_or_style_preset

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

            # Ensure paragraph_props exists
            if text_props_to_return.paragraph_props is None:
                text_props_to_return.paragraph_props = {} # Initialize if None

            # ADDED DEBUG LOG
            self.logger.debug(f"{log_prefix}INSPECTING before dump: final_props.rotation_degrees = {text_props_to_return.rotation_degrees}, type = {type(text_props_to_return.rotation_degrees)}")

            # LOG THE FINAL PROPS before returning
            self.logger.debug(f"{log_prefix}Returning resolved: {text_props_to_return.model_dump(exclude_none=True)}") # exclude_none for cleaner logs
            return text_props_to_return

        # Fallback: If text_props_to_return is still None after Paths 1 & 2,
        # it means the reference was invalid or yielded no text_props.
        # We should then try the layer_config_fallback if available.

        # ADDED DEBUG LOG 2
        self.logger.debug(f"{log_prefix}Before final fallback check (line ~213): text_props_to_return is None = {text_props_to_return is None}. Rotation if not None: {text_props_to_return.rotation_degrees if text_props_to_return else 'N/A'}")

        if text_props_to_return is None:
            if layer_config_fallback and not preset_already_resolved: # Prevent infinite recursion if fallback is also a preset name
                self.logger.debug(f"{log_prefix}Falling back to layer_config '{layer_config_fallback.name}' for text style properties.")
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

            # Ensure paragraph_props exists
            if text_props_to_return.paragraph_props is None:
                text_props_to_return.paragraph_props = {} # Initialize if None

            # ADDED DEBUG LOG
            self.logger.debug(f"{log_prefix}INSPECTING before dump: final_props.rotation_degrees = {text_props_to_return.rotation_degrees}, type = {type(text_props_to_return.rotation_degrees)}")

            # LOG THE FINAL PROPS before returning
            self.logger.debug(f"{log_prefix}Returning resolved: {text_props_to_return.model_dump(exclude_none=True)}") # exclude_none for cleaner logs
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
        # ADDED DIAGNOSTIC LOG
        self.logger.debug(f"DIAGNOSTIC - StyleService.get_resolved_style_for_label_operation - FINAL RETURN props: {resolved_text_props.model_dump_json(indent=2, exclude_none=True)}")
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
        This method is now simplified. DXF STYLE table entries are primarily managed by
        DxfResourceSetupService based on DxfWriterConfig.text_styles and its internal
        logic to ensure "Standard" style and styles from font presets (if font_file is directly named).
        This method's original role of creating styles from style_presets is now largely redundant.
        It could be used for very specific post-processing or validation if needed, or removed.
        For now, let's make it a no-op or minimal logging to reflect its changed role.
        """
        self.logger.info("StyleService.create_styles_in_dxf_doc called. DXF STYLE table creation is now primarily handled by DxfResourceSetupService. This method currently performs no additional STYLE table modifications.")
        # Original logic iterating style_presets_config and calling
        # self.dxf_style_definition_service.ensure_text_style_in_dxf is REMOVED.
        # DxfResourceSetupService._create_text_styles_from_config and
        # DxfResourceSetupService._ensure_styles_for_font_presets cover these needs.
        return

    # Removed: _create_and_add_text_style_to_doc_if_not_exists (logic moved to DxfStyleDefinitionService)

# Ensure all old private methods are removed if their logic is now fully in sub-services.
# e.g., _get_resolved_font_filename was part of the old _resolve_text_style_from_preset_and_inline,
# that logic is now encapsulated within PresetResolverService.resolve_text_style.
