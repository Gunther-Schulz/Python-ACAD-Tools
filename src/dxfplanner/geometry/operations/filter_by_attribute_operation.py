from typing import AsyncIterator, Any, Optional, List
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import FilterByAttributeOperationConfig, FilterOperator, LogicalOperator
from dxfplanner.core.logging_config import get_logger # Main logger
from logging import Logger # For type hint if needed

# Use the module-level logger directly if this class doesn't need a uniquely named one.
logger = get_logger(__name__)

class FilterByAttributeOperation(IOperation[FilterByAttributeOperationConfig]):
    """Filters features based on attribute values matching specified criteria."""

    # If a specific logger instance is desired, pass it in. Otherwise, use module logger.
    def __init__(self, logger_param: Optional[Logger] = None):
        self.logger = logger_param if logger_param else logger

    def _evaluate_condition(self, feature_value: Any, condition_value: Any, operator: FilterOperator) -> bool:
        if operator == FilterOperator.IS_NULL: return feature_value is None
        if operator == FilterOperator.IS_NOT_NULL: return feature_value is not None
        if feature_value is None: return False # For other ops, if feat_val is None, no match

        try:
            if operator in [FilterOperator.GREATER_THAN, FilterOperator.LESS_THAN, FilterOperator.GREATER_THAN_OR_EQUAL, FilterOperator.LESS_THAN_OR_EQUAL]:
                try:
                    num_feat_val, num_cond_val = float(feature_value), float(condition_value)
                    if operator == FilterOperator.GREATER_THAN: return num_feat_val > num_cond_val
                    if operator == FilterOperator.LESS_THAN: return num_feat_val < num_cond_val
                    if operator == FilterOperator.GREATER_THAN_OR_EQUAL: return num_feat_val >= num_cond_val
                    if operator == FilterOperator.LESS_THAN_OR_EQUAL: return num_feat_val <= num_cond_val
                except (ValueError, TypeError): self.logger.debug(f"Numeric conversion failed for {operator}"); return False

            str_feat_val, str_cond_val = str(feature_value), str(condition_value)
            if operator == FilterOperator.EQUALS: return str_feat_val == str_cond_val
            if operator == FilterOperator.NOT_EQUALS: return str_feat_val != str_cond_val
            if operator == FilterOperator.CONTAINS: return str_cond_val in str_feat_val
            if operator == FilterOperator.NOT_CONTAINS: return str_cond_val not in str_feat_val
            if operator == FilterOperator.STARTS_WITH: return str_feat_val.startswith(str_cond_val)
            if operator == FilterOperator.ENDS_WITH: return str_feat_val.endswith(str_cond_val)

            if operator in [FilterOperator.IN, FilterOperator.NOT_IN]:
                if not isinstance(condition_value, list): self.logger.warning(f"{operator} needs list val"); return False
                str_cond_list = [str(v) for v in condition_value]
                if operator == FilterOperator.IN: return str_feat_val in str_cond_list
                if operator == FilterOperator.NOT_IN: return str_feat_val not in str_cond_list
        except Exception as e: self.logger.debug(f"Comparison error: {e}"); return False
        self.logger.warning(f"Unhandled operator: {operator}"); return False

    async def execute(self, features: AsyncIterator[GeoFeature], config: FilterByAttributeOperationConfig) -> AsyncIterator[GeoFeature]:
        log_prefix = f"FilterByAttribute (output: '{config.output_layer_name}')" # Assuming output_layer_name is on BaseOperationConfig
        self.logger.info(f"{log_prefix}: {len(config.conditions)} conditions, op '{config.logical_operator}'.")
        if not config.conditions:
            self.logger.warning(f"{log_prefix}: No filter conditions provided. Yielding all features.")
            async for feature_no_cond in features: # Corrected variable name
                yield feature_no_cond
            self.logger.info(f"{log_prefix}: Completed (no conditions, all features yielded).") # Added logging
            return

        async for feature in features:
            current_properties = feature.properties or {}
            results = [self._evaluate_condition(current_properties.get(c.attribute), c.value, c.operator) for c in config.conditions]

            final_match = all(results) if config.logical_operator == LogicalOperator.AND else any(results)
            if final_match: yield feature
        self.logger.info(f"{log_prefix}: Completed.")
