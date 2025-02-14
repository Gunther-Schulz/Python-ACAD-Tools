"""Utilities for handling text in DXF files."""

import traceback
import ezdxf
from ezdxf.enums import TextEntityAlignment
from src.utils import log_warning, log_info, log_error, log_debug
from .constants import SCRIPT_IDENTIFIER
from .entity_utils import attach_custom_data
from .style_utils import get_color_code
from .style_defaults import (
    DEFAULT_TEXT_STYLE,
    TEXT_ATTACHMENT_POINTS,
    VALID_ATTACHMENT_POINTS,
    TEXT_FLOW_DIRECTIONS,
    TEXT_LINE_SPACING_STYLES,
    VALID_STYLE_PROPERTIES
)

def _apply_text_style_properties(entity, text_style, name_to_aci=None):
    """Apply common text style properties to a text entity (MTEXT or TEXT)."""
    if not text_style:
        text_style = DEFAULT_TEXT_STYLE.copy()

    # Basic properties
    entity.dxf.char_height = text_style.get('height', DEFAULT_TEXT_STYLE['height'])
    entity.dxf.style = text_style.get('font', DEFAULT_TEXT_STYLE['font'])
    
    # Color
    color = get_color_code(text_style.get('color', DEFAULT_TEXT_STYLE['color']), name_to_aci)
    if isinstance(color, tuple):
        entity.rgb = color
    else:
        entity.dxf.color = color

    # Attachment point
    attachment_key = text_style.get('attachmentPoint', DEFAULT_TEXT_STYLE['attachmentPoint']).upper()
    if attachment_key in TEXT_ATTACHMENT_POINTS:
        entity.dxf.attachment_point = TEXT_ATTACHMENT_POINTS[attachment_key]

    # Flow direction (MTEXT specific)
    if hasattr(entity, 'dxf.flow_direction'):
        flow_key = text_style.get('flowDirection', 'LEFT_TO_RIGHT').upper()
        if flow_key in TEXT_FLOW_DIRECTIONS:
            entity.dxf.flow_direction = TEXT_FLOW_DIRECTIONS[flow_key]

    # Line spacing (MTEXT specific)
    if hasattr(entity, 'dxf.line_spacing_style'):
        spacing_key = text_style.get('lineSpacingStyle', 'AT_LEAST').upper()
        if spacing_key in TEXT_LINE_SPACING_STYLES:
            entity.dxf.line_spacing_style = TEXT_LINE_SPACING_STYLES[spacing_key]

        factor = text_style.get('lineSpacingFactor', DEFAULT_TEXT_STYLE.get('lineSpacingFactor', 1.0))
        min_factor, max_factor = VALID_STYLE_PROPERTIES['text']['lineSpacingFactor'][1]
        if min_factor <= factor <= max_factor:
            entity.dxf.line_spacing_factor = factor

    # Background fill
    if hasattr(entity, 'set_bg_color'):
        if text_style.get('bgFill', DEFAULT_TEXT_STYLE.get('bgFill', False)):
            bg_color = text_style.get('bgFillColor', DEFAULT_TEXT_STYLE.get('bgFillColor', None))
            min_scale, max_scale = VALID_STYLE_PROPERTIES['text']['bgFillScale'][1]
            bg_scale = text_style.get('bgFillScale', DEFAULT_TEXT_STYLE.get('bgFillScale', (min_scale + max_scale) / 2))
            if bg_color:
                entity.set_bg_color(bg_color, scale=bg_scale)

    # Rotation
    entity.dxf.rotation = float(text_style.get('rotation', DEFAULT_TEXT_STYLE.get('rotation', 0.0)))

    # Paragraph properties
    if 'paragraph' in text_style and hasattr(entity, 'text'):
        para = text_style['paragraph']
        default_para = DEFAULT_TEXT_STYLE['paragraph']
        align_map = {
            'LEFT': '\\pql;',
            'CENTER': '\\pqc;',
            'RIGHT': '\\pqr;',
            'JUSTIFIED': '\\pqj;',
            'DISTRIBUTED': '\\pqd;'
        }
        align_key = para.get('align', default_para['align']).upper()
        if align_key in align_map:
            current_text = entity.text
            entity.text = f"{align_map[align_key]}{current_text}"

def get_text_attachment_point(attachment_key):
    """Get the DXF attachment point value for a given key."""
    attachment_key = attachment_key.upper()
    if attachment_key in TEXT_ATTACHMENT_POINTS:
        return TEXT_ATTACHMENT_POINTS[attachment_key]
    log_warning(f"Invalid attachment point '{attachment_key}'. Using default.")
    return TEXT_ATTACHMENT_POINTS[DEFAULT_TEXT_STYLE['attachmentPoint']]

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
        'char_height': text_style.get('height', DEFAULT_TEXT_STYLE['height']),
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

def add_text(msp, text, x, y, layer_name, style_name, text_style=None, name_to_aci=None):
    """Add TEXT entity with style support."""
    # Use text_style if provided, otherwise use defaults
    if text_style is None:
        text_style = DEFAULT_TEXT_STYLE.copy()

    text_entity = msp.add_text(text, dxfattribs={
        'style': style_name,
        'layer': layer_name,
        'insert': (x, y),
        'height': text_style.get('height', DEFAULT_TEXT_STYLE['height']),
        'color': get_color_code(text_style.get('color', DEFAULT_TEXT_STYLE['color']), name_to_aci)
    })

    # Set placement based on attachment point
    attachment_point = text_style.get('attachmentPoint', DEFAULT_TEXT_STYLE['attachmentPoint'])
    text_entity.set_placement(
        (x, y),
        align=get_text_attachment_point(attachment_point)
    )

    # Apply any additional text style properties
    _apply_text_style_properties(text_entity, text_style, name_to_aci)
    
    return text_entity 