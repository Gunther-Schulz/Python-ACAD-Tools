"""Geometry utility functions for DXF export."""

import ezdxf
from ezdxf.lldxf import const
from ezdxf import colors
from src.utils import log_warning, log_info, log_error, log_debug
from .constants import SCRIPT_IDENTIFIER
from .entity_utils import attach_custom_data
from .style_utils import get_color_code, convert_transparency
from .style_defaults import (
    DEFAULT_HATCH_STYLE,
    DEFAULT_BLOCK_STYLE
)

def create_hatch(msp, paths, hatch_config, project_loader):
    """Create a hatch entity with the given paths and configuration."""
    try:
        # Get pattern from config or default
        pattern = hatch_config.get('pattern', DEFAULT_HATCH_STYLE['pattern'])
        
        # Create hatch with default color from style
        hatch = msp.add_hatch(color=get_color_code(DEFAULT_HATCH_STYLE['color'], project_loader.name_to_aci))
        
        # Set pattern
        if pattern != DEFAULT_HATCH_STYLE['pattern']:
            try:
                hatch.set_pattern_fill(pattern, scale=hatch_config.get('scale', DEFAULT_HATCH_STYLE['scale']))
            except Exception as e:
                log_warning(f"Failed to set pattern '{pattern}': {str(e)}")
                hatch.set_pattern_fill(DEFAULT_HATCH_STYLE['pattern'])
        
        # Add paths
        for path in paths:
            hatch.paths.add_polyline_path(path)
        
        # Set color if specified
        if 'color' in hatch_config and hatch_config['color'] not in (None, 'BYLAYER'):
            color = get_color_code(hatch_config['color'], project_loader.name_to_aci)
            if isinstance(color, tuple):
                hatch.rgb = color
            else:
                hatch.dxf.color = color
        
        return hatch
    except Exception as e:
        log_warning(f"Error creating hatch: {str(e)}")
        return None

def set_hatch_transparency(hatch, transparency):
    """Set the transparency of a hatch entity."""
    if transparency is not None:
        # Convert transparency to ezdxf format (0-1, where 1 is fully transparent)
        ezdxf_transparency = transparency
        # Set hatch transparency
        hatch.dxf.transparency = colors.float2transparency(ezdxf_transparency)

def get_available_blocks(doc):
    return set(block.name for block in doc.blocks if not block.name.startswith('*'))

def add_block_reference(msp, block_name, insert_point, layer_name, scale=None, rotation=None):
    """Add a block reference with proper defaults."""
    if block_name in msp.doc.blocks:
        block_ref = msp.add_blockref(block_name, insert_point)
        block_ref.dxf.layer = layer_name
        block_ref.dxf.xscale = scale if scale is not None else DEFAULT_BLOCK_STYLE['scale']
        block_ref.dxf.yscale = scale if scale is not None else DEFAULT_BLOCK_STYLE['scale']
        block_ref.dxf.rotation = rotation if rotation is not None else DEFAULT_BLOCK_STYLE['rotation']
        block_ref.dxf.color = get_color_code(DEFAULT_BLOCK_STYLE['color'], None)
        block_ref.dxf.linetype = DEFAULT_BLOCK_STYLE['linetype']
        attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
        return block_ref
    else:
        log_warning(f"Block '{block_name}' not found in the document")
        return None 