"""Utilities for handling text in DXF files."""

import traceback
import ezdxf
from ezdxf.enums import TextEntityAlignment
from src.core.utils import log_warning, log_info, log_error, log_debug
from .constants import SCRIPT_IDENTIFIER
from .entity_utils import attach_custom_data
from .style_utils import get_color_code

def _apply_text_style_properties(entity, text_style, name_to_aci=None):
    """Apply common text style properties to a text entity (MTEXT or TEXT)."""
    if not text_style:
        return

    # Basic properties
    if 'height' in text_style:
        entity.dxf.char_height = text_style['height']
    if 'font' in text_style:
        entity.dxf.style = text_style['font']
    
    # Color
    if 'color' in text_style:
        color = get_color_code(text_style['color'], name_to_aci)
        if isinstance(color, tuple):
            entity.rgb = color
        else:
            entity.dxf.color = color

    # Attachment point
    if 'attachmentPoint' in text_style:
        attachment_map = {
            'TOP_LEFT': 1, 'TOP_CENTER': 2, 'TOP_RIGHT': 3,
            'MIDDLE_LEFT': 4, 'MIDDLE_CENTER': 5, 'MIDDLE_RIGHT': 6,
            'BOTTOM_LEFT': 7, 'BOTTOM_CENTER': 8, 'BOTTOM_RIGHT': 9
        }
        attachment_key = text_style['attachmentPoint'].upper()
        if attachment_key in attachment_map:
            entity.dxf.attachment_point = attachment_map[attachment_key]

    # Flow direction (MTEXT specific)
    if hasattr(entity, 'dxf.flow_direction') and 'flowDirection' in text_style:
        flow_map = {
            'LEFT_TO_RIGHT': 1,
            'TOP_TO_BOTTOM': 3,
            'BY_STYLE': 5
        }
        flow_key = text_style['flowDirection'].upper()
        if flow_key in flow_map:
            entity.dxf.flow_direction = flow_map[flow_key]

    # Line spacing (MTEXT specific)
    if hasattr(entity, 'dxf.line_spacing_style'):
        if 'lineSpacingStyle' in text_style:
            spacing_map = {
                'AT_LEAST': 1,
                'EXACT': 2
            }
            spacing_key = text_style['lineSpacingStyle'].upper()
            if spacing_key in spacing_map:
                entity.dxf.line_spacing_style = spacing_map[spacing_key]

        if 'lineSpacingFactor' in text_style:
            factor = float(text_style['lineSpacingFactor'])
            if 0.25 <= factor <= 4.00:
                entity.dxf.line_spacing_factor = factor

    # Background fill
    if hasattr(entity, 'set_bg_color'):
        if 'bgFill' in text_style and text_style['bgFill']:
            bg_color = text_style.get('bgFillColor')
            bg_scale = text_style.get('bgFillScale', 1.5)
            if bg_color:
                entity.set_bg_color(bg_color, scale=bg_scale)

    # Rotation
    if 'rotation' in text_style:
        entity.dxf.rotation = float(text_style['rotation'])

    # Paragraph properties
    if 'paragraph' in text_style and hasattr(entity, 'text'):
        para = text_style['paragraph']
        if 'align' in para:
            align_map = {
                'LEFT': '\\pql;',
                'CENTER': '\\pqc;',
                'RIGHT': '\\pqr;',
                'JUSTIFIED': '\\pqj;',
                'DISTRIBUTED': '\\pqd;'
            }
            align_key = para['align'].upper()
            if align_key in align_map:
                current_text = entity.text
                entity.text = f"{align_map[align_key]}{current_text}"

def add_mtext(msp, text, x, y, layer_name, style_name, text_style=None, name_to_aci=None, max_width=None):
    """Add MTEXT entity with comprehensive style support."""
    log_debug(f"=== Starting MTEXT creation ===")
    log_debug(f"Text: '{text}'")
    log_debug(f"Position: ({x}, {y})")
    log_debug(f"Layer: '{layer_name}'")
    log_debug(f"Style name: '{style_name}'")
    log_debug(f"Text style config: {text_style}")
    
    # Build basic dxfattribs
    dxfattribs = {
        'style': style_name,
        'layer': layer_name,
        'char_height': text_style.get('height', 2.5),
        'width': text_style.get('maxWidth', max_width) if max_width is not None else 0,
        'insert': (x, y)
    }

    try:
        # Create the MTEXT entity
        mtext = msp.add_mtext(text, dxfattribs=dxfattribs)
        
        # Apply common text style properties
        _apply_text_style_properties(mtext, text_style, name_to_aci)

        # Attach custom data
        attach_custom_data(mtext, SCRIPT_IDENTIFIER)
        
        log_debug(f"=== Completed MTEXT creation ===")
        actual_height = mtext.dxf.char_height * mtext.dxf.line_spacing_factor * len(text.split('\n'))
        return mtext, actual_height

    except Exception as e:
        log_error(f"Failed to add MTEXT: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return None, 0

def add_text(msp, text, x, y, layer_name, style_name, height=5, color=None):
    text_entity = msp.add_text(text, dxfattribs={
        'style': style_name,
        'layer': layer_name,
        'insert': (x, y),
        'height': height,
        'color': color if color is not None else ezdxf.const.BYLAYER
    })
    text_entity.set_placement(
        (x, y),
        align=TextEntityAlignment.LEFT
    )
    return text_entity 