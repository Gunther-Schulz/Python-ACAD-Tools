import logging
from typing import List, Optional, Any, Dict
from copy import deepcopy

from asteval import Interpreter as AstevalInterpreter # For evaluating expressions safely

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IAttributeMappingService
from dxfplanner.config.schemas import AttributeMappingServiceConfig, MappingRuleConfig, DxfWriterConfig
# Assuming a utility for ACI color conversion might exist or needs to be simple for now
# from dxfplanner.geometry.aci import convert_to_aci_color # Example import

logger = logging.getLogger(__name__)

class AttributeMappingService(IAttributeMappingService):
    def __init__(self, config: AttributeMappingServiceConfig, dxf_writer_config: DxfWriterConfig, logger_in: Optional[logging.Logger] = None):
        self.config = config
        self.dxf_writer_config = dxf_writer_config
        self.logger = logger_in or logger
        self.aeval = AstevalInterpreter()
        # Sort rules by priority once at initialization
        self.sorted_rules = sorted(self.config.mapping_rules, key=lambda r: r.priority)

    def _evaluate_expression(self, expression: str, feature_properties: Dict[str, Any]) -> Any:
        """Safely evaluates an expression using asteval with feature properties as context."""
        eval_context_properties = feature_properties or {}
        self.aeval.symtable.update({'properties': eval_context_properties})
        # Clear previous errors and stdout before new evaluation
        self.aeval.error = []
        self.aeval.stdout = ''

        success = self.aeval.eval(expression)
        if not success or self.aeval.error:
            # Log detailed asteval errors
            error_messages = [err.get_error()[1] for err in self.aeval.error]
            self.logger.warning(f"Expression evaluation failed for '{expression}'. Errors: {error_messages}")
            return None # Indicate failure
        if '_result' not in self.aeval.symtable:
             self.logger.warning(f"Expression '{expression}' did not yield a '_result' in asteval symtable.")
             return None
        return self.aeval.symtable['_result']


    def _cast_value(self, value: Any, target_type: Optional[str], rule: MappingRuleConfig) -> Any:
        """Casts the value to the target type. Handles ACI color conversion."""
        if target_type is None or value is None:
            return value

        try:
            if target_type == "str":
                return str(value)
            elif target_type == "int":
                return int(value)
            elif target_type == "float":
                return float(value)
            elif target_type == "bool":
                return bool(value)
            elif target_type == "aci_color":
                # Placeholder for ACI color conversion logic
                # This might involve checking if it's already an int, or converting from name/RGB
                if isinstance(value, str) and value.upper() == "BYLAYER":
                    return 256
                if isinstance(value, str) and value.upper() == "BYBLOCK":
                    return 0
                # Add more sophisticated ACI conversion here if needed
                # For now, assume if it's an int, it's an ACI color
                # Or a simple lookup for common names
                color_map = {"RED": 1, "YELLOW": 2, "GREEN": 3, "CYAN": 4, "BLUE": 5, "MAGENTA": 6, "WHITE": 7}
                if isinstance(value, str) and value.upper() in color_map:
                    return color_map[value.upper()]

                # Attempt to convert to int if it looks like a number string
                if isinstance(value, str) and value.isdigit():
                     val_int = int(value)
                     if 0 <= val_int <= 255: # Basic ACI range check
                         return val_int

                if isinstance(value, int) and (0 <= value <= 255 or value == 256): # 256 is ByLayer, 0 is ByBlock
                     return value

                self.logger.warning(f"Cannot convert '{value}' to ACI color for rule '{rule.dxf_property_name}'. Using on_error_value if defined, else skipping.")
                return rule.on_error_value # Or raise error/return specific marker
            else:
                self.logger.warning(f"Unsupported target_type: {target_type}")
                return rule.on_error_value
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Type casting to {target_type} failed for value '{value}' (Rule: '{rule.dxf_property_name}'). Error: {e}. Using on_error_value.")
            return rule.on_error_value

        # Fallback if no specific conversion happened but no error.
        return value


    def apply_mappings(self, features: List[GeoFeature]) -> List[GeoFeature]:
        processed_features: List[GeoFeature] = []
        if not self.dxf_writer_config.layer_mapping_by_attribute_value and not self.sorted_rules:
            self.logger.info("No attribute-value layer mappings and no mapping rules configured. Returning features as is, layer may be set by default later.")
            for original_feature in features:
                feature = deepcopy(original_feature)
                if feature.dxf_properties is None:
                    feature.dxf_properties = {}
                if "layer" not in feature.dxf_properties and self.config.default_dxf_layer_on_mapping_failure:
                    feature.dxf_properties["layer"] = self.config.default_dxf_layer_on_mapping_failure
                    self.logger.debug(f"Feature {feature.id or 'with no id'} (no rules path) assigned default layer: {self.config.default_dxf_layer_on_mapping_failure}")
                processed_features.append(feature)
            return processed_features

        for original_feature in features:
            feature = deepcopy(original_feature)
            if feature.dxf_properties is None:
                feature.dxf_properties = {}

            applied_dxf_properties_for_feature = set()

            provisional_layer_from_attr_map: Optional[str] = None
            if self.dxf_writer_config.layer_mapping_by_attribute_value:
                for attr_key_to_check, value_to_layer_map in self.dxf_writer_config.layer_mapping_by_attribute_value.items():
                    if feature.properties and attr_key_to_check in feature.properties:
                        actual_attr_value = str(feature.properties[attr_key_to_check])
                        if actual_attr_value in value_to_layer_map:
                            provisional_layer_from_attr_map = value_to_layer_map[actual_attr_value]
                            self.logger.debug(f"Feature {feature.id or 'with no id'}: layer '{provisional_layer_from_attr_map}' provisionally set by attribute '{attr_key_to_check}' (value '{actual_attr_value}') from layer_mapping_by_attribute_value.")
                            break

            if provisional_layer_from_attr_map:
                 feature.dxf_properties["layer"] = provisional_layer_from_attr_map

            for rule in self.sorted_rules:
                if rule.dxf_property_name in applied_dxf_properties_for_feature and rule.dxf_property_name != "layer":
                    continue
                elif rule.dxf_property_name in applied_dxf_properties_for_feature and rule.dxf_property_name == "layer":
                     pass

                apply_rule = True
                if rule.condition:
                    condition_result = self._evaluate_expression(rule.condition, feature.properties)
                    if condition_result is None or not bool(condition_result):
                        apply_rule = False

                if not apply_rule:
                    continue

                value = self._evaluate_expression(rule.source_expression, feature.properties)
                if value is None:
                    if rule.on_error_value is not None:
                        value = rule.on_error_value
                        self.logger.debug(f"Source expression for '{rule.dxf_property_name}' (Feature ID: {feature.id or 'N/A'}) evaluated to None or failed. Using on_error_value: '{value}'.")
                    else:
                        self.logger.debug(f"Source expression for '{rule.dxf_property_name}' (Feature ID: {feature.id or 'N/A'}) evaluated to None or failed, and no on_error_value. Skipping.")
                        continue

                casted_value = self._cast_value(value, rule.target_type, rule)

                if casted_value is not None:
                    if rule.dxf_property_name == "layer" and rule.dxf_property_name in applied_dxf_properties_for_feature:
                         self.logger.debug(f"Rule for 'layer' (Feature ID: {feature.id or 'N/A'}) is overwriting previously set layer with '{casted_value}'.")

                    feature.dxf_properties[rule.dxf_property_name] = casted_value
                    applied_dxf_properties_for_feature.add(rule.dxf_property_name)
                    self.logger.debug(f"Applied rule for '{rule.dxf_property_name}' (Feature ID: {feature.id or 'N/A'}): value '{casted_value}' from expression '{rule.source_expression}'.")
                elif rule.on_error_value is None and rule.target_type is not None:
                     self.logger.debug(f"Casting to '{rule.target_type}' failed for rule '{rule.dxf_property_name}' (Feature ID: {feature.id or 'N/A'}) and no on_error_value. Property not set.")

            if "layer" not in feature.dxf_properties and self.config.default_dxf_layer_on_mapping_failure:
                feature.dxf_properties["layer"] = self.config.default_dxf_layer_on_mapping_failure
                self.logger.debug(f"Feature {feature.id or 'with no id'} did not get a layer assigned by attribute map or rules. Using default: {self.config.default_dxf_layer_on_mapping_failure}")

            processed_features.append(feature)
        return processed_features
