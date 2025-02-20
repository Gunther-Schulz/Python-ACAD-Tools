"""Color configuration module."""

import yaml
import os
from pathlib import Path
from typing import Dict, Optional, Union, Tuple, List

# Default location for color mapping file
DEFAULT_COLOR_FILE = Path(__file__).parent / "aci_colors.yaml"

# Type hints for color values
ColorInfo = Dict[str, Union[int, Tuple[int, int, int]]]

def load_color_mapping(color_yaml_path: Optional[Path] = None) -> Dict[str, ColorInfo]:
    """Load color mapping from YAML file.
    
    Args:
        color_yaml_path: Path to color mapping YAML file. If None, uses default location
        
    Returns:
        Dictionary mapping color names to color info containing:
        - 'aci': ACI code (int)
        - 'rgb': RGB values (tuple of 3 ints)
    """
    # Default color mapping as fallback
    DEFAULT_COLOR_MAPPING = {
        'white': {'aci': 7, 'rgb': (255, 255, 255)},
        'red': {'aci': 1, 'rgb': (255, 0, 0)},
        'yellow': {'aci': 2, 'rgb': (255, 255, 0)},
        'green': {'aci': 3, 'rgb': (0, 255, 0)},
        'cyan': {'aci': 4, 'rgb': (0, 255, 255)},
        'blue': {'aci': 5, 'rgb': (0, 0, 255)},
        'magenta': {'aci': 6, 'rgb': (255, 0, 255)},
        'black': {'aci': 0, 'rgb': (0, 0, 0)},
        'gray': {'aci': 8, 'rgb': (128, 128, 128)},
        'light-grey': {'aci': 9, 'rgb': (192, 192, 192)},
        'dark-grey': {'aci': 250, 'rgb': (84, 84, 84)},
        'bylayer': {'aci': 256, 'rgb': None},
        'byblock': {'aci': 0, 'rgb': None}
    }
    
    # If no path provided, use default location
    if color_yaml_path is None:
        color_yaml_path = DEFAULT_COLOR_FILE
    
    if not color_yaml_path.exists():
        return DEFAULT_COLOR_MAPPING
        
    try:
        with open(color_yaml_path, 'r') as f:
            colors = yaml.safe_load(f)
            # Convert the YAML structure to our mapping format
            mapping = {}
            for color in colors:
                name = color['name'].lower()
                mapping[name] = {
                    'aci': color['aciCode'],
                    'rgb': tuple(color['rgb']) if 'rgb' in color else None
                }
            return mapping
    except Exception as e:
        print(f"Error loading color mapping: {e}")
        return DEFAULT_COLOR_MAPPING 