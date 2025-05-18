import re
from typing import Optional, Dict, Any
from logging import Logger

class RuleEvaluatorServiceError(Exception):
    """Custom exception for RuleEvaluatorService errors."""
    pass

class RuleEvaluatorService:
    """
    Service for evaluating style rule conditions against feature attributes.
    """

    def __init__(self, logger: Logger):
        """
        Initializes the RuleEvaluatorService.

        Args:
            logger: An instance of Logger.
        """
        self.logger = logger

    def evaluate_condition(self, condition_str: str, attributes: Dict[str, Any]) -> bool:
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
        # Note: Debug log attributes keys only for brevity if attributes dict is large.
        # Consider logging actual attribute value if key exists for deeper debugging.
        self.logger.debug(f"Evaluating condition: '{condition_str}' against attribute keys: {list(attributes.keys())}")

        match_op_val = re.match(r"^\s*([\w.-]+)\s*(!=|==|=|>=|<=|>|<|CONTAINS|NOT CONTAINS|IN|NOT IN)\s*(.+)$", condition_str, re.IGNORECASE)
        match_exists = re.match(r"^\s*([\w.-]+)\s*(EXISTS|NOT EXISTS)$", condition_str, re.IGNORECASE)

        key: Optional[str] = None
        operator_str: Optional[str] = None
        value_str: Optional[str] = None
        actual_value: Any = None

        if match_op_val:
            key = match_op_val.group(1).strip()
            operator_str = match_op_val.group(2).upper().replace(" ", "_")
            value_str = match_op_val.group(3).strip()
            actual_value = attributes.get(key)
            self.logger.debug(f"Parsed condition: key='{key}', operator='{operator_str}', value_str='{value_str}', actual_attribute_value={actual_value if key in attributes else '[KEY NOT FOUND]'}")
        elif match_exists:
            key = match_exists.group(1).strip()
            operator_str = match_exists.group(2).upper().replace(" ", "_")
            actual_value = attributes.get(key) # Will be None if key not present
            self.logger.debug(f"Parsed condition: key='{key}', operator='{operator_str}', actual_attribute_value={actual_value if key in attributes else '[KEY NOT FOUND]'}")
        else:
            self.logger.warning(f"Unparseable style rule condition: '{condition_str}'. Defaulting to False.")
            return False

        if operator_str == "EXISTS":
            result = key in attributes and actual_value is not None
            self.logger.debug(f"Condition '{condition_str}': Key '{key}' exists and not None. Result: {result}.")
            return result
        elif operator_str == "NOT_EXISTS":
            result = not (key in attributes and actual_value is not None)
            self.logger.debug(f"Condition '{condition_str}': Key '{key}' not exists or is None. Result: {result}.")
            return result

        if actual_value is None:
            if operator_str == "!=" or operator_str == "NOT_CONTAINS" or operator_str == "NOT_IN":
                 self.logger.debug(f"Condition '{condition_str}': Key '{key}' is None. For '{operator_str}', result is True.")
                 return True
            self.logger.debug(f"Condition '{condition_str}': Key '{key}' is None. Result: False for operator '{operator_str}'.")
            return False

        expected_value_typed: Any
        if value_str is not None:
            val_lower = value_str.lower()
            if val_lower == "true": expected_value_typed = True
            elif val_lower == "false": expected_value_typed = False
            else:
                try:
                    if '.' in value_str or 'e' in val_lower:
                        expected_value_typed = float(value_str)
                    else:
                        expected_value_typed = int(value_str)
                except ValueError:
                    if (value_str.startswith("'") and value_str.endswith("'")) or \
                       (value_str.startswith('"') and value_str.endswith('"')):
                        expected_value_typed = value_str[1:-1]
                    else:
                        expected_value_typed = value_str
        else:
             self.logger.error(f"Internal error: value_str is None for operator '{operator_str}'. This should not happen.")
             return False

        try:
            if operator_str in (">", "<", ">=", "<="):
                return eval(f"float(actual_value) {operator_str} float(expected_value_typed)")
            elif operator_str in ("==", "="):
                if type(actual_value) == type(expected_value_typed): return actual_value == expected_value_typed
                if isinstance(actual_value, (int, float)) and isinstance(expected_value_typed, (int, float)): return float(actual_value) == float(expected_value_typed)
                if isinstance(expected_value_typed, bool):
                    try: actual_bool = str(actual_value).lower() == 'true' if str(actual_value).lower() in ['true', 'false'] else bool(int(actual_value))
                    except: actual_bool = str(actual_value).lower() == 'true'
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
            elif operator_str == "CONTAINS":
                return str(expected_value_typed).lower() in str(actual_value).lower()
            elif operator_str == "NOT_CONTAINS":
                return str(expected_value_typed).lower() not in str(actual_value).lower()
            elif operator_str == "IN":
                list_string = str(expected_value_typed)
                value_list_raw = list_string.split(',')
                value_list = []
                for v_raw in value_list_raw:
                    v_stripped = v_raw.strip()
                    # Strip potential quotes from individual items
                    if (v_stripped.startswith("'") and v_stripped.endswith("'")) or \
                       (v_stripped.startswith('"') and v_stripped.endswith('"')):
                        v_final = v_stripped[1:-1]
                    else:
                        v_final = v_stripped
                    value_list.append(v_final.lower())
                self.logger.debug(f"Condition '{condition_str}': IN check. Actual: '{str(actual_value).lower()}', Target List: {value_list}")
                return str(actual_value).lower() in value_list
            elif operator_str == "NOT_IN":
                list_string = str(expected_value_typed)
                value_list_raw = list_string.split(',')
                value_list = []
                for v_raw in value_list_raw:
                    v_stripped = v_raw.strip()
                    if (v_stripped.startswith("'") and v_stripped.endswith("'")) or \
                       (v_stripped.startswith('"') and v_stripped.endswith('"')):
                        v_final = v_stripped[1:-1]
                    else:
                        v_final = v_stripped
                    value_list.append(v_final.lower())
                self.logger.debug(f"Condition '{condition_str}': NOT_IN check. Actual: '{str(actual_value).lower()}', Target List: {value_list}")
                return str(actual_value).lower() not in value_list
            else:
                self.logger.warning(f"Unhandled parsed operator: '{operator_str}' in condition '{condition_str}'. Defaulting to False.")
                return False
        except Exception as e:
            self.logger.debug(f"Error during comparison for condition '{condition_str}': {e}. Actual: '{actual_value}' ({type(actual_value)}), Expected: '{expected_value_typed}' ({type(expected_value_typed)}), Operator: {operator_str}. Defaulting to False.")
            return False
