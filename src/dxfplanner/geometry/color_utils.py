"""
Color and transparency utility functions for DXFPlanner geometry processing.
"""
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
        if 0.0 <= val_to_convert <= 1.0:
            return val_to_convert
        elif val_to_convert > 1.0:
            logger.debug(f"Transparency {transparency} is > 1.0. Clamping to 1.0 (fully transparent). Input should ideally be 0.0-1.0.")
            return 1.0
        else: # val_to_convert < 0.0
            logger.debug(f"Transparency {transparency} is < 0.0. Clamping to 0.0 (opaque).")
            return 0.0
    return None
