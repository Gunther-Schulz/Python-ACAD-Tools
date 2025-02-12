"""Utilities for handling styles and colors in DXF files."""

from src.utils import log_warning

def get_color_code(color, name_to_aci):
    if color is None:
        return 7  # Default to 7 (white) if no color is specified
    if isinstance(color, int):
        return color  # Return ACI code as-is
    elif isinstance(color, str):
        if ',' in color:
            # It's an RGB string
            try:
                return tuple(map(int, color.split(',')))
            except ValueError:
                log_warning(f"Invalid RGB color string: {color}")
                return 7  # Default to white if invalid
        else:
            # It's a color name
            aci_code = name_to_aci.get(color.lower())
            if aci_code is None:
                log_warning(f"Color name '{color}' not found in ACI color mapping. Defaulting to white (7).")
                return 7
            return aci_code
    elif isinstance(color, (list, tuple)) and len(color) == 3:
        # It's already an RGB tuple
        return tuple(color)
    else:
        return 7  # Default to 7 (white) for any other type

def convert_transparency(transparency):
    if isinstance(transparency, (int, float)):
        return min(max(transparency, 0), 1)  # Ensure value is between 0 and 1
    elif isinstance(transparency, str):
        try:
            return float(transparency)
        except ValueError:
            log_warning(f"Invalid transparency value: {transparency}")
    return None

def deep_merge(dict1, dict2):
    """Deep merge two dictionaries."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result 