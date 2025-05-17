"""
Layer-related utility functions for DXFPlanner.
"""
import re
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

def sanitize_layer_name(name: str) -> str:
    """Sanitizes a layer name to be compliant with DXF/AutoCAD standards."""
    if not isinstance(name, str):
        logger.warning(f"Layer name input is not a string: {name}. Returning default name.")
        return "Default_Layer_Name"

    # Replace characters forbidden by AutoCAD in layer names
    # Forbidden characters: < > / \\ " : ; ? * | = `
    forbidden_chars = r'[<>/\\\\":;?*|=`]' # Escaped for Python string literal and regex
    sanitized = re.sub(forbidden_chars, '_', name)

    # DXF layer names also cannot have leading/trailing spaces (strictly).
    sanitized = sanitized.strip()

    if not sanitized: # If stripping makes the name empty, or it was empty to begin with.
        sanitized = "Empty_Layer_Name"

    # Truncate to 255 characters (common DXF limit for names)
    return sanitized[:255]
