"""Utilities for handling DXF entities."""

import ezdxf
from ezdxf.lldxf import const
from ezdxf import colors
from src.core.utils import log_warning, log_info, log_error, log_debug
from .constants import SCRIPT_IDENTIFIER
from .style_utils import get_color_code, convert_transparency
from .style_defaults import (
    DEFAULT_ENTITY_STYLE,
    TEXT_ATTACHMENT_POINTS,
    VALID_ATTACHMENT_POINTS,
    TEXT_FLOW_DIRECTIONS,
    TEXT_LINE_SPACING_STYLES
)

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
        return

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
        entity.dxf.color = ezdxf.const.BYLAYER
    
    if 'lineweight' in style:
        entity.dxf.lineweight = style['lineweight']
    
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
            del entity.transparency
        except AttributeError:
            pass

    # Apply linetype scale
    if 'linetypeScale' in style:
        entity.dxf.ltscale = float(style['linetypeScale'])
    else:
        entity.dxf.ltscale = 1.0

def _apply_text_style_properties(entity, text_style, name_to_aci=None):
    """Apply text-specific style properties."""
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
        attachment_key = text_style['attachmentPoint'].upper()
        if attachment_key in TEXT_ATTACHMENT_POINTS:
            entity.dxf.attachment_point = TEXT_ATTACHMENT_POINTS[attachment_key]

    # Flow direction (MTEXT specific)
    if hasattr(entity, 'dxf.flow_direction') and 'flowDirection' in text_style:
        flow_key = text_style['flowDirection'].upper()
        if flow_key in TEXT_FLOW_DIRECTIONS:
            entity.dxf.flow_direction = TEXT_FLOW_DIRECTIONS[flow_key]

    # Line spacing (MTEXT specific)
    if hasattr(entity, 'dxf.line_spacing_style'):
        if 'lineSpacingStyle' in text_style:
            spacing_key = text_style['lineSpacingStyle'].upper()
            if spacing_key in TEXT_LINE_SPACING_STYLES:
                entity.dxf.line_spacing_style = TEXT_LINE_SPACING_STYLES[spacing_key]

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

def linetype_exists(doc, linetype_name):
    """Check if a linetype exists in the document."""
    try:
        return linetype_name in doc.linetypes
    except:
        return False 