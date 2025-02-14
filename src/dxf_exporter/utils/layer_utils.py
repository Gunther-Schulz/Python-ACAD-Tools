"""Utilities for handling DXF layers."""

import re
import ezdxf
from ezdxf.lldxf import const
from ezdxf.lldxf.const import (
    LINEWEIGHT_BYLAYER,
    LINEWEIGHT_BYBLOCK,
    LINEWEIGHT_DEFAULT
)
from src.core.utils import log_warning, log_info, log_error, log_debug
from .constants import SCRIPT_IDENTIFIER
from .style_utils import get_color_code, convert_transparency
from .style_defaults import DEFAULT_LAYER_STYLE

def ensure_layer_exists(doc, layer_name):
    """Ensure that a layer exists in the DXF document."""
    if not doc.layers.has_entry(layer_name):
        doc.layers.new(name=layer_name)
        log_debug(f"Created new layer: {layer_name}")
    else:
        log_debug(f"Layer already exists: {layer_name}")
    return doc.layers.get(layer_name)

def update_layer_properties(layer, layer_properties, name_to_aci):
    # Skip if no properties provided
    if not layer_properties:
        return
        
    if 'color' in layer_properties:
        color = get_color_code(layer_properties['color'], name_to_aci)
        if isinstance(color, tuple):
            layer.rgb = color  # Set RGB color directly
        elif isinstance(color, int):
            layer.color = color  # Set ACI color directly
        else:
            log_warning(f"Invalid color value: {color}")
    if 'linetype' in layer_properties:
        layer.dxf.linetype = layer_properties['linetype']
    if 'lineweight' in layer_properties:
        lineweight_value = layer_properties['lineweight']
        # Handle special values
        if isinstance(lineweight_value, str):
            upper_value = lineweight_value.upper()
            if upper_value == 'BYLAYER':
                layer.dxf.lineweight = LINEWEIGHT_BYLAYER
                log_debug("Set layer lineweight to: BYLAYER")
            elif upper_value == 'BYBLOCK':
                layer.dxf.lineweight = LINEWEIGHT_BYBLOCK
                log_debug("Set layer lineweight to: BYBLOCK")
            elif upper_value == 'DEFAULT':
                layer.dxf.lineweight = LINEWEIGHT_DEFAULT
                log_debug("Set layer lineweight to: DEFAULT")
            else:
                try:
                    # Try to convert string to integer for numeric values
                    layer.dxf.lineweight = int(lineweight_value)
                    log_debug(f"Set layer lineweight to: {lineweight_value}")
                except (ValueError, TypeError):
                    log_warning(f"Invalid lineweight value: {lineweight_value}, using default")
                    layer.dxf.lineweight = LINEWEIGHT_DEFAULT
        else:
            # Handle numeric values directly
            try:
                layer.dxf.lineweight = int(lineweight_value)
                log_debug(f"Set layer lineweight to: {lineweight_value}")
            except (ValueError, TypeError):
                log_warning(f"Invalid lineweight value: {lineweight_value}, using default")
                layer.dxf.lineweight = LINEWEIGHT_DEFAULT
    if 'transparency' in layer_properties:
        transparency = convert_transparency(layer_properties['transparency'])
        if transparency is not None:
            layer.transparency = transparency
    if 'plot' in layer_properties:
        layer.dxf.plot = layer_properties['plot']
    if 'lock' in layer_properties:
        layer.lock() if layer_properties['lock'] else layer.unlock()
    if 'frozen' in layer_properties:
        layer.freeze() if layer_properties['frozen'] else layer.thaw()
    if 'is_on' in layer_properties:
        layer.on = layer_properties['is_on']

def sanitize_layer_name(name):
    # Define a set of allowed characters, including German-specific ones, space, dash, and underscore
    allowed_chars = r'a-zA-Z0-9_\-öüäßÖÜÄ '
    
    # Replace disallowed characters with underscores
    sanitized = re.sub(f'[^{allowed_chars}]', '_', name)
    
    # Ensure the name starts with a letter, underscore, or allowed special character (excluding space)
    if not re.match(f'^[{allowed_chars.replace(" ", "")}]', sanitized):
        sanitized = '_' + sanitized
    
    # Remove any leading spaces
    sanitized = sanitized.lstrip()
    
    # Truncate to 255 characters (AutoCAD limit)
    return sanitized[:255] 