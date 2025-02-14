"""Utilities for handling DXF entities."""

import ezdxf
from ezdxf.lldxf import const
from ezdxf import colors
from src.core.utils import log_warning, log_info, log_error, log_debug
from .constants import SCRIPT_IDENTIFIER
from .style_utils import get_color_code, convert_transparency
from .style_defaults import (
    DEFAULT_ENTITY_STYLE,
    DEFAULT_TEXT_STYLE,
    TEXT_ATTACHMENT_POINTS,
    VALID_ATTACHMENT_POINTS,
    TEXT_FLOW_DIRECTIONS,
    TEXT_LINE_SPACING_STYLES
)
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN

def attach_custom_data(entity, script_identifier, entity_name=None):
    """Attaches custom data to an entity with proper cleanup of existing data."""
    try:
        # Clear any existing XDATA first
        try:
            entity.discard_xdata('DXFEXPORTER')
        except:
            pass
            
        # Set new XDATA
        entity.set_xdata(
            'DXFEXPORTER',
            [(1000, script_identifier)]
        )
        
        # Ensure entity is properly added to the document database
        if hasattr(entity, 'doc') and entity.doc:
            entity.doc.entitydb.add(entity)
            
        # Add hyperlink with entity name if supported
        if hasattr(entity, 'set_hyperlink'):
            try:
                hyperlink_text = entity_name if entity_name else f"{script_identifier}"
                # Only set hyperlink if it doesn't already exist
                if not entity.get_hyperlink():
                    entity.set_hyperlink(hyperlink_text)
            except Exception as e:
                log_warning(f"Failed to set hyperlink for entity: {str(e)}")
    except Exception as e:
        log_warning(f"Failed to attach custom data to entity: {str(e)}")

def remove_entities_by_layer(msp, layer_names, script_identifier):
    """Remove entities from specified layers that were created by this script.
    
    Args:
        msp: The modelspace or paperspace to remove entities from
        layer_names: A single layer name or list of layer names
        script_identifier: The identifier used to mark entities created by this script
    """
    if isinstance(layer_names, str):
        layer_names = [layer_names]
    
    for layer_name in layer_names:
        # Query all entities in the layer
        query = f'*[layer=="{layer_name}"]'
        try:
            entities = msp.query(query)
            removed_count = 0
            
            for entity in entities:
                if is_created_by_script(entity, script_identifier):
                    msp.delete_entity(entity)
                    removed_count += 1
            
            if removed_count > 0:
                log_debug(f"Removed {removed_count} entities from layer: {layer_name}")
                
        except Exception as e:
            log_warning(f"Error removing entities from layer {layer_name}: {str(e)}")

def is_created_by_script(entity, script_identifier):
    """Check if an entity was created by this script."""
    try:
        xdata = entity.get_xdata('DXFEXPORTER')
        if xdata:
            for code, value in xdata:
                if code == 1000 and value == script_identifier:
                    return True
    except ezdxf.lldxf.const.DXFValueError:
        # This exception is raised when the entity has no XDATA for 'DXFEXPORTER'
        # It's not an error, just means the entity wasn't created by this script
        return False
    except Exception as e:
        log_error(f"Unexpected error checking XDATA for entity {entity}: {str(e)}")
    return False

def apply_style_to_entity(entity, style, project_loader, loaded_styles=None):
    """Apply style properties to an entity."""
    if not style:
        style = DEFAULT_ENTITY_STYLE.copy()

    # Get linetype
    if 'linetype' in style:
        if style['linetype'] not in entity.doc.linetypes:
            log_warning(f"Linetype '{style['linetype']}' not defined. Using '{DEFAULT_ENTITY_STYLE['linetype']}'.")
            entity.dxf.linetype = DEFAULT_ENTITY_STYLE['linetype']
        else:
            entity.dxf.linetype = style['linetype']

    # Handle text-specific properties
    if entity.dxftype() in ('MTEXT', 'TEXT'):
        _apply_text_style_properties(entity, style, loaded_styles)
    
    # Apply non-text properties
    if 'color' in style:
        color = get_color_code(style['color'], loaded_styles)
        if isinstance(color, tuple):
            entity.rgb = color
        else:
            entity.dxf.color = color
    else:
        entity.dxf.color = get_color_code(DEFAULT_ENTITY_STYLE['color'], None)
    
    if 'lineweight' in style:
        entity.dxf.lineweight = style['lineweight']
    else:
        entity.dxf.lineweight = DEFAULT_ENTITY_STYLE['lineweight']
    
    # Set transparency
    if 'transparency' in style:
        transparency = convert_transparency(style['transparency'])
        if transparency is not None:
            try:
                entity.transparency = transparency
            except Exception as e:
                log_info(f"Could not set transparency for {entity.dxftype()}. Error: {str(e)}")
    else:
        try:
            entity.transparency = DEFAULT_ENTITY_STYLE['transparency']
        except AttributeError:
            pass

    # Apply linetype scale
    if 'linetypeScale' in style:
        entity.dxf.ltscale = float(style['linetypeScale'])
    else:
        entity.dxf.ltscale = DEFAULT_ENTITY_STYLE['linetypeScale']

    # Handle polyline-specific properties
    if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
        # Apply close property
        if 'close' in style:
            entity.close(style['close'])
        else:
            entity.close(DEFAULT_ENTITY_STYLE['close'])
        
        # Apply linetype generation if present
        if 'linetypeGeneration' in style:
            if style['linetypeGeneration']:
                entity.dxf.flags |= LWPOLYLINE_PLINEGEN
            else:
                entity.dxf.flags &= ~LWPOLYLINE_PLINEGEN

def _apply_text_style_properties(entity, text_style, name_to_aci=None):
    """Apply text-specific style properties."""
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
        flow_key = text_style.get('flowDirection', DEFAULT_TEXT_STYLE['flowDirection']).upper()
        if flow_key in TEXT_FLOW_DIRECTIONS:
            entity.dxf.flow_direction = TEXT_FLOW_DIRECTIONS[flow_key]

    # Line spacing (MTEXT specific)
    if hasattr(entity, 'dxf.line_spacing_style'):
        spacing_key = text_style.get('lineSpacingStyle', DEFAULT_TEXT_STYLE['lineSpacingStyle']).upper()
        if spacing_key in TEXT_LINE_SPACING_STYLES:
            entity.dxf.line_spacing_style = TEXT_LINE_SPACING_STYLES[spacing_key]

        factor = text_style.get('lineSpacingFactor', DEFAULT_TEXT_STYLE['lineSpacingFactor'])
        entity.dxf.line_spacing_factor = factor

    # Background fill
    if hasattr(entity, 'set_bg_color'):
        if text_style.get('bgFill', DEFAULT_TEXT_STYLE['bgFill']):
            bg_color = text_style.get('bgFillColor', DEFAULT_TEXT_STYLE['bgFillColor'])
            bg_scale = text_style.get('bgFillScale', DEFAULT_TEXT_STYLE['bgFillScale'])
            if bg_color:
                entity.set_bg_color(bg_color, scale=bg_scale)

    # Rotation
    entity.dxf.rotation = float(text_style.get('rotation', DEFAULT_TEXT_STYLE['rotation']))

def linetype_exists(doc, linetype_name):
    """Check if a linetype exists in the document."""
    try:
        return linetype_name in doc.linetypes
    except:
        return False 