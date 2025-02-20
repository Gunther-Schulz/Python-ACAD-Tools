"""DXF color handling."""

from typing import Union, Tuple, Dict, Optional
from pathlib import Path
from src.config.color_config import load_color_mapping

# DXF color constants
BYLAYER = 256
BYBLOCK = 0
DEFAULT_COLOR = 7  # White

ColorType = Union[str, int, Tuple[int, int, int]]
ColorInfo = Dict[str, Union[int, Tuple[int, int, int]]]

class DXFColorConverter:
    """Handles color conversion for DXF format."""
    
    def __init__(self, color_mapping: Optional[Dict[str, ColorInfo]] = None, color_yaml_path: Optional[Path] = None):
        """Initialize with optional custom color mapping.
        
        Args:
            color_mapping: Optional custom color name to color info mapping
            color_yaml_path: Optional path to color mapping YAML file
        """
        if color_mapping is not None:
            self.color_mapping = color_mapping
        else:
            self.color_mapping = load_color_mapping(color_yaml_path)
    
    def get_color_code(self, color: ColorType) -> Union[int, Tuple[int, int, int]]:
        """Convert color specification to DXF color code.
        
        Args:
            color: Color specification (name, ACI code, or RGB tuple)
            
        Returns:
            DXF color code or RGB tuple
        """
        if color is None:
            return DEFAULT_COLOR
        
        # Handle special values
        if isinstance(color, str):
            color_upper = color.upper()
            if color_upper == 'BYLAYER':
                return BYLAYER
            elif color_upper == 'BYBLOCK':
                return BYBLOCK
            
            # Try color name mapping
            color_lower = color.lower()
            if color_lower in self.color_mapping:
                color_info = self.color_mapping[color_lower]
                return color_info['aci']
        
        # Handle RGB tuples
        if isinstance(color, (list, tuple)) and len(color) == 3:
            return tuple(max(0, min(255, c)) for c in color)
        
        # Handle ACI codes
        if isinstance(color, int):
            return max(0, min(255, color))
        
        # Default to white if color format not recognized
        return DEFAULT_COLOR
    
    def get_rgb(self, color: ColorType) -> Optional[Tuple[int, int, int]]:
        """Get RGB values for a color if available.
        
        Args:
            color: Color specification (name, ACI code, or RGB tuple)
            
        Returns:
            RGB tuple if available, None otherwise
        """
        if isinstance(color, str) and color.lower() in self.color_mapping:
            color_info = self.color_mapping[color.lower()]
            return color_info['rgb']
        elif isinstance(color, (list, tuple)) and len(color) == 3:
            return tuple(max(0, min(255, c)) for c in color)
        return None
    
    def is_valid_color(self, color: ColorType) -> bool:
        """Check if color specification is valid for DXF.
        
        Args:
            color: Color specification to validate
            
        Returns:
            True if valid
        """
        try:
            if isinstance(color, str):
                color_upper = color.upper()
                if color_upper in {'BYLAYER', 'BYBLOCK'}:
                    return True
                return color.lower() in self.color_mapping
            
            if isinstance(color, (list, tuple)):
                return len(color) == 3 and all(0 <= c <= 255 for c in color)
            
            if isinstance(color, int):
                return 0 <= color <= 256
            
            return False
            
        except Exception:
            return False 