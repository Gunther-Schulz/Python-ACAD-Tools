"""
Service for managing and resolving style configurations.
"""
from typing import Optional, TypeVar, Type, Generic, Union, List, Dict, Any
from pydantic import BaseModel
from logging import Logger
import re

from dxfplanner.config.schemas import (
    ProjectConfig,
    LayerConfig,
    LabelPlacementOperationConfig,
)
from dxfplanner.config.style_schemas import (
    StyleObjectConfig,
    LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig,
    TextParagraphPropertiesConfig,
    HatchPropertiesConfig,
    StyleRuleConfig
)
from dxfplanner.domain.interfaces import IStyleService
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.core.exceptions import DXFPlannerBaseError
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class StyleServiceError(DXFPlannerBaseError):
    """Custom exception for StyleService errors."""
    pass

TBaseModel = TypeVar('TBaseModel', bound=BaseModel)

class StyleService(IStyleService):
    """
    Manages and resolves style configurations for layers and labels.
    Handles presets, inline definitions, and overrides from AppConfig.
    Also processes feature-specific style rules.
    """

    def __init__(self, config: ProjectConfig, logger: Logger):
        self._config = config
        self.logger = logger

    def _evaluate_condition(self, condition_str: str, attributes: Dict[str, Any]) -> bool:
        """
        Evaluates a condition string against feature attributes.
        Supported formats:
        - "key==value" (or key=value)
        - "key!=value"
        - "key>value"
        - "key<value"
        - "key>=value"
        - "key<=value"
        - "key CONTAINS value"
        - "key NOT_CONTAINS value"
        - "key IN value1,value2,value3"
        - "key NOT_IN value1,value2,value3"
        - "key EXISTS"
        - "key NOT_EXISTS"
        Coerces 'value' to str, int, float, bool (True, False, true, false) for comparison.
        Case-insensitive for EXISTS, NOT_EXISTS, CONTAINS, NOT_CONTAINS, IN, NOT_IN operators.
        """
        condition_str = condition_str.strip()
        self.logger.debug(f"Evaluating condition: '{condition_str}' against attributes: {list(attributes.keys())}")

        # Regex to parse various conditions
        # 1. key OPERATOR value (e.g. key==value, key > value, key CONTAINS value)
        # Operator list: !=, ==, =, >=, <=, >, <, CONTAINS, NOT CONTAINS, IN, NOT IN (case insensitive for word operators)
        # Key can contain word characters, '.', '-'
        # Value can be anything until the end of the string
        match_op_val = re.match(r"^\s*([\w.-]+)\s*(!=|==|=|>=|<=|>|<|CONTAINS|NOT CONTAINS|IN|NOT IN)\s*(.+)$", condition_str, re.IGNORECASE)
        # 2. key EXISTS (e.g. key EXISTS)
        match_exists = re.match(r"^\s*([\w.-]+)\s*(EXISTS|NOT EXISTS)$", condition_str, re.IGNORECASE) # Combined NOT_EXISTS for simpler regex

        key: Optional[str] = None
        operator_str: Optional[str] = None
        value_str: Optional[str] = None

        actual_value: Any = None

        if match_op_val:
            key = match_op_val.group(1).strip()
            operator_str = match_op_val.group(2).upper().replace(" ", "_") # e.g. "NOT CONTAINS" -> "NOT_CONTAINS"
            value_str = match_op_val.group(3).strip()
            actual_value = attributes.get(key)
        elif match_exists:
            key = match_exists.group(1).strip()
            operator_str = match_exists.group(2).upper().replace(" ", "_") # e.g. "NOT EXISTS" -> "NOT_EXISTS"
            actual_value = attributes.get(key)
        else:
            self.logger.warning(f"Unparseable style rule condition: '{condition_str}'. Defaulting to False.")
            return False

        # Handle EXISTS / NOT_EXISTS first
        if operator_str == "EXISTS":
            result = key in attributes and actual_value is not None
            self.logger.debug(f"Condition '{condition_str}': Key '{key}' exists and not None. Result: {result}.")
            return result
        elif operator_str == "NOT_EXISTS":
            result = not (key in attributes and actual_value is not None)
            self.logger.debug(f"Condition '{condition_str}': Key '{key}' not exists or is None. Result: {result}.")
            return result

        if actual_value is None: # For all other operators, if actual_value is None
            # If operator is !=, None != "some_value" is true.
            # If operator is NOT_CONTAINS or NOT_IN, None NOT_CONTAINS "val" or None NOT_IN "val" is true.
            if operator_str == "!=" or operator_str == "NOT_CONTAINS" or operator_str == "NOT_IN":
                 self.logger.debug(f"Condition '{condition_str}': Key '{key}' is None. For '{operator_str}', result is True.")
                 return True
            self.logger.debug(f"Condition '{condition_str}': Key '{key}' is None. Result: False for operator '{operator_str}'.")
            return False

        expected_value_typed: Any
        if value_str is not None: # Should always be not None if not EXISTS/NOT_EXISTS
            # Handle boolean coercion first
            val_lower = value_str.lower()
            if val_lower == "true": expected_value_typed = True
            elif val_lower == "false": expected_value_typed = False
            else:
                # Attempt numeric coercion (float then int)
                try:
                    if '.' in value_str or 'e' in val_lower: # Scientific notation
                        expected_value_typed = float(value_str)
                    else:
                        expected_value_typed = int(value_str)
                except ValueError:
                    # If not bool or numeric, it's a string. Remove quotes if present.
                    if (value_str.startswith("'") and value_str.endswith("'")) or \
                       (value_str.startswith('"') and value_str.endswith('"')):
                        expected_value_typed = value_str[1:-1]
                    else:
                        expected_value_typed = value_str
        else: # Should be unreachable due to logic sequence
             self.logger.error(f"Internal error: value_str is None for operator '{operator_str}'. This should not happen.")
             return False

        # Perform comparison
        try:
            # Numeric comparisons
            if operator_str in (">", "<", ">=", "<="):
                return eval(f"float(actual_value) {operator_str} float(expected_value_typed)") # Safe eval with known structure

            # Equality based comparisons (handle type nuances)
            elif operator_str in ("==", "="):
                if type(actual_value) == type(expected_value_typed): return actual_value == expected_value_typed
                if isinstance(actual_value, (int, float)) and isinstance(expected_value_typed, (int, float)): return float(actual_value) == float(expected_value_typed)
                if isinstance(expected_value_typed, bool): # if expected is bool, try to make actual bool
                    try: actual_bool = str(actual_value).lower() == 'true' if str(actual_value).lower() in ['true', 'false'] else bool(int(actual_value))
                    except: actual_bool = str(actual_value).lower() == 'true' # fallback
                    return actual_bool == expected_value_typed
                return str(actual_value).lower() == str(expected_value_typed).lower()

            elif operator_str == "!=":
                if type(actual_value) == type(expected_value_typed): return actual_value != expected_value_typed
                if isinstance(actual_value, (int, float)) and isinstance(expected_value_typed, (int, float)): return float(actual_value) != float(expected_value_typed)
                if isinstance(expected_value_typed, bool):
                    try: actual_bool = str(actual_value).lower() == 'true' if str(actual_value).lower() in ['true', 'false'] else bool(int(actual_value))
                    except: actual_bool = str(actual_value).lower() == 'true'
                    return actual_bool != expected_value_typed
                return str(actual_value).lower() != str(expected_value_typed).lower()

            # String operations
            elif operator_str == "CONTAINS":
                return str(expected_value_typed).lower() in str(actual_value).lower()
            elif operator_str == "NOT_CONTAINS":
                return str(expected_value_typed).lower() not in str(actual_value).lower()

            # List operations
            elif operator_str == "IN":
                value_list = [v.strip().lower() for v in str(expected_value_typed).split(',')]
                return str(actual_value).lower() in value_list
            elif operator_str == "NOT_IN":
                value_list = [v.strip().lower() for v in str(expected_value_typed).split(',')]
                return str(actual_value).lower() not in value_list

            else: # Should be unreachable if regex is comprehensive
                self.logger.warning(f"Unhandled parsed operator: '{operator_str}' in condition '{condition_str}'. Defaulting to False.")
                return False

        except Exception as e: # Catch any error during comparison or coercion
            self.logger.debug(f"Error during comparison for condition '{condition_str}': {e}. Actual: '{actual_value}' ({type(actual_value)}), Expected: '{expected_value_typed}' ({type(expected_value_typed)}), Operator: {operator_str}. Defaulting to False.")
            return False

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

    def get_resolved_style_for_label_operation(
        self, config: LabelPlacementOperationConfig
    ) -> TextStylePropertiesConfig:
        """
        Resolves the TextStylePropertiesConfig for a label placement operation.
        Primarily uses the inline text_style defined in the operation's label_settings.
        """
        self.logger.debug(
            f"Resolving text style for LabelPlacementOperation: "
            f"Output='{config.output_label_layer_name}', Source='{config.source_layer}'"
        )

        # LabelingConfig is where the specific text_style for labels is defined.
        labeling_config = config.label_settings  # This is LabelingConfig

        if labeling_config and labeling_config.text_style:
            # If an inline text_style is defined in LabelingConfig, use it directly.
            self.logger.debug(
                f"Using inline text_style from LabelingConfig: "
                f"{labeling_config.text_style.model_dump_json(exclude_none=True, indent=2)}"
            )
            # TextStylePropertiesConfig fields have defaults, so an instance is generally usable.
            return labeling_config.text_style
        else:
            # No specific text style defined in the label operation's config.
            # Return a default TextStylePropertiesConfig.
            self.logger.debug(
                "No inline text_style in LabelingConfig. Returning default TextStylePropertiesConfig."
            )
            return TextStylePropertiesConfig()

    def get_resolved_hatch_style(
        self, layer_config: LayerConfig
    ) -> Optional[HatchPropertiesConfig]:
        resolved_object = self.get_resolved_style_object(
            preset_name=layer_config.style_preset_name,
            inline_definition=layer_config.style_inline_definition,
            override_definition=layer_config.style_override,
            context_name=layer_config.name
        )
        # The resolved_object.hatch_props should be non-null due to get_resolved_style_object's logic
        return resolved_object.hatch_props if resolved_object.hatch_props is not None else HatchPropertiesConfig()

    def get_resolved_feature_style(self, geo_feature: GeoFeature, layer_config: LayerConfig) -> StyleObjectConfig:
        """
        Resolves the StyleObjectConfig for a given GeoFeature based on the LayerConfig,
        applying feature-specific style rules.
        """
        context_name = f"Feature ID {geo_feature.id or 'N/A'} on layer {layer_config.name}"
        self.logger.debug(f"Resolving feature style for: {context_name}")

        # 1. Get base style for the layer
        current_style = self.get_resolved_style_object(
            preset_name=layer_config.style_preset_name,
            inline_definition=layer_config.style_inline_definition,
            override_definition=layer_config.style_override,
            context_name=f"Base for layer {layer_config.name}"
        )
        self.logger.debug(f"Initial style for {context_name} (from layer defaults): {current_style.model_dump_json(indent=2)}")


        # 2. Sort and apply feature-specific style rules
        # Sort by priority (ascending), then by name for stable sort if priorities are equal (name is optional so handle None)
        # Higher priority numbers should apply later, so we want to sort by priority such that
        # rules with the same priority are applied in defined order, and then higher priorities overwrite.
        # A simple sort by priority (ascending) means lower priority rules merge first.
        sorted_rules = sorted(layer_config.style_rules, key=lambda r: (r.priority, r.name or ""))

        if sorted_rules:
            self.logger.debug(f"Applying {len(sorted_rules)} style rules for {context_name}, sorted by priority: {[r.name or 'Unnamed' for r in sorted_rules]}")

        for rule in sorted_rules:
            rule_name = rule.name or f"Condition({rule.condition})"
            self.logger.debug(f"Evaluating rule '{rule_name}' (Priority: {rule.priority}) for {context_name}")

            if self._evaluate_condition(rule.condition, geo_feature.attributes):
                self.logger.info(f"Rule '{rule_name}' condition MET for {context_name}. Applying override: {rule.style_override.model_dump_json(indent=2)}")

                # Merge rule's style_override onto current_style
                current_style.layer_props = self._merge_style_component(
                    current_style.layer_props,
                    rule.style_override.layer_props,
                    LayerDisplayPropertiesConfig
                ) or current_style.layer_props # Ensure it's not None

                current_style.text_props = self._merge_style_component(
                    current_style.text_props,
                    rule.style_override.text_props,
                    TextStylePropertiesConfig
                ) or current_style.text_props

                current_style.hatch_props = self._merge_style_component(
                    current_style.hatch_props,
                    rule.style_override.hatch_props,
                    HatchPropertiesConfig
                ) or current_style.hatch_props

                self.logger.debug(f"Style after applying rule '{rule_name}' for {context_name}: {current_style.model_dump_json(indent=2)}")

                if rule.terminate:
                    self.logger.info(f"Rule '{rule_name}' has terminate=True. No further style rules will be processed for {context_name}.")
                    break
            else:
                self.logger.debug(f"Rule '{rule_name}' condition NOT MET for {context_name}.")

        # Ensure all components exist, even if default, after rule processing
        if current_style.layer_props is None: current_style.layer_props = LayerDisplayPropertiesConfig()
        if current_style.text_props is None: current_style.text_props = TextStylePropertiesConfig()
        if current_style.hatch_props is None: current_style.hatch_props = HatchPropertiesConfig()

        self.logger.debug(f"Final resolved style for {context_name}: {current_style.model_dump_json(indent=2)}")
        return current_style
