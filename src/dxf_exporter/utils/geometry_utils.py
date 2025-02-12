"""Utilities for handling geometry in DXF files."""

import ezdxf
from ezdxf.lldxf import const
from ezdxf import colors
from src.utils import log_warning
from .constants import SCRIPT_IDENTIFIER
from .entity_utils import attach_custom_data
from .style_utils import get_color_code, convert_transparency

def create_hatch(msp, boundary_paths, hatch_config, project_loader):
    hatch = msp.add_hatch()
    
    pattern = hatch_config.get('pattern', 'SOLID')
    pattern_scale = hatch_config.get('scale', 1)
    
    if pattern != 'SOLID':
        try:
            hatch.set_pattern_fill(pattern, scale=pattern_scale)
        except ezdxf.DXFValueError:
            log_warning(f"Invalid hatch pattern: {pattern}. Using SOLID instead.")
            hatch.set_pattern_fill("SOLID")
    else:
        hatch.set_solid_fill()

    # Add boundary paths
    if isinstance(boundary_paths, list):
        for path in boundary_paths:
            hatch.paths.add_polyline_path(path)
    else:
        # Single boundary case
        vertices = list(boundary_paths.exterior.coords)
        hatch.paths.add_polyline_path(vertices)

    # Apply color
    if 'color' in hatch_config and hatch_config['color'] not in (None, 'BYLAYER'):
        color = get_color_code(hatch_config['color'], project_loader.name_to_aci)
        if isinstance(color, tuple):
            hatch.rgb = color
        else:
            hatch.dxf.color = color
    else:
        hatch.dxf.color = ezdxf.const.BYLAYER

    # Apply lineweight
    if 'lineweight' in hatch_config:
        hatch.dxf.lineweight = hatch_config['lineweight']

    # Apply transparency
    if 'transparency' in hatch_config:
        transparency = convert_transparency(hatch_config['transparency'])
        if transparency is not None:
            set_hatch_transparency(hatch, transparency)
    
    return hatch

def set_hatch_transparency(hatch, transparency):
    """Set the transparency of a hatch entity."""
    if transparency is not None:
        # Convert transparency to ezdxf format (0-1, where 1 is fully transparent)
        ezdxf_transparency = transparency
        # Set hatch transparency
        hatch.dxf.transparency = colors.float2transparency(ezdxf_transparency)

def get_available_blocks(doc):
    return set(block.name for block in doc.blocks if not block.name.startswith('*'))

def add_block_reference(msp, block_name, insert_point, layer_name, scale=1.0, rotation=0.0):
    if block_name in msp.doc.blocks:
        block_ref = msp.add_blockref(block_name, insert_point)
        block_ref.dxf.layer = layer_name
        block_ref.dxf.xscale = scale
        block_ref.dxf.yscale = scale
        block_ref.dxf.rotation = rotation
        attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
        return block_ref
    else:
        log_warning(f"Block '{block_name}' not found in the document")
        return None 