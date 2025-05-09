"""
General geometric utilities.
"""
import re
from typing import Tuple, Union, Optional, Any
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

def get_color_code(color: Any, name_to_aci: dict) -> Union[int, Tuple[int, int, int]]:
    """Converts various color inputs to an ACI code or an RGB tuple."""
    if color is None:
        return 7  # Default to 7 (white/black) if no color is specified
    if isinstance(color, int):
        return color  # Return ACI code as-is
    elif isinstance(color, str):
        if ',' in color:
            # It's an RGB string "r,g,b"
            try:
                rgb = tuple(map(int, color.split(',')))
                if len(rgb) == 3 and all(0 <= val <= 255 for val in rgb):
                    return rgb
                else:
                    logger.warning(f"Invalid RGB color string values: {color}")
                    return 7
            except ValueError:
                logger.warning(f"Invalid RGB color string format: {color}")
                return 7
        else:
            # It's a color name
            aci_code = name_to_aci.get(color.lower())
            if aci_code is None:
                logger.warning(f"Color name '{color}' not found in ACI color mapping. Defaulting to white (7).")
                return 7
            return aci_code
    elif isinstance(color, (list, tuple)) and len(color) == 3 and all(isinstance(val, int) and 0 <= val <= 255 for val in color):
        # It's already an RGB tuple
        return tuple(color)
    else:
        logger.warning(f"Invalid color type or format: {color}. Defaulting to white (7).")
        return 7

def convert_transparency(transparency: Any) -> Optional[float]:
    """Converts a transparency value to a float between 0.0 (opaque) and 1.0 (fully transparent)."""
    # ezdxf typically uses integer transparency 0x020000TT where TT is 00 (opaque) to FF (255, fully transparent)
    # This function aims for a 0.0 to 1.0 scale.
    val_to_convert = None
    if isinstance(transparency, (int, float)):
        val_to_convert = float(transparency)
    elif isinstance(transparency, str):
        try:
            val_to_convert = float(transparency)
        except ValueError:
            logger.warning(f"Invalid transparency value string: {transparency}")
            return None

    if val_to_convert is not None:
        # Clamp to 0.0 - 1.0 range, assuming direct input or already scaled.
        # More complex heuristics for 0-100 or 0-255 scales were removed for clarity;
        # this should be handled by the input provider or a more specific config.
        if 0.0 <= val_to_convert <= 1.0:
            return val_to_convert
        elif val_to_convert > 1.0: # If input is like 50 (for 50%), it will become 1.0
            logger.debug(f"Transparency {transparency} is > 1.0. Clamping to 1.0 (fully transparent). Input should ideally be 0.0-1.0.")
            return 1.0
        else: # val_to_convert < 0.0
            logger.debug(f"Transparency {transparency} is < 0.0. Clamping to 0.0 (opaque).")
            return 0.0
    return None

def sanitize_layer_name(name: str) -> str:
    """Sanitizes a layer name to be compliant with DXF/AutoCAD standards."""
    if not isinstance(name, str):
        logger.warning(f"Layer name input is not a string: {name}. Returning default name.")
        return "Default_Layer_Name"

    # Replace characters forbidden by AutoCAD in layer names
    # Forbidden characters: < > / \ " : ; ? * | = `
    forbidden_chars = r'[<>/\\":;?*|=`]' # Corrected regex
    sanitized = re.sub(forbidden_chars, '_', name)

    # DXF layer names also cannot have leading/trailing spaces (strictly).
    sanitized = sanitized.strip()

    if not sanitized: # If stripping makes the name empty, or it was empty to begin with.
        sanitized = "Empty_Layer_Name"

    # Truncate to 255 characters (common DXF limit for names)
    return sanitized[:255]
