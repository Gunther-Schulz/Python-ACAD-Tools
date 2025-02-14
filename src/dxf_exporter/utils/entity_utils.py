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
    
    log_debug(f"Applying style to entity {entity.dxftype()}: {style}")

    try:
        # Get linetype
        if 'linetype' in style:
            try:
                if style['linetype'] not in entity.doc.linetypes:
                    log_warning(f"Linetype '{style['linetype']}' not defined. Using '{DEFAULT_ENTITY_STYLE['linetype']}'.")
                    entity.dxf.linetype = DEFAULT_ENTITY_STYLE['linetype']
                else:
                    entity.dxf.linetype = style['linetype']
                    log_debug(f"Set linetype to: {style['linetype']}")
            except Exception as e:
                log_warning(f"Error setting linetype: {str(e)}")

        # Handle text-specific properties
        if entity.dxftype() in ('MTEXT', 'TEXT'):
            _apply_text_style_properties(entity, style, loaded_styles)
        
        # Apply non-text properties
        try:
            if 'color' in style:
                color = get_color_code(style['color'], loaded_styles)
                if isinstance(color, tuple):
                    entity.rgb = color
                    log_debug(f"Set RGB color to: {color}")
                else:
                    entity.dxf.color = color
                    log_debug(f"Set ACI color to: {color}")
            else:
                entity.dxf.color = get_color_code(DEFAULT_ENTITY_STYLE['color'], None)
        except Exception as e:
            log_warning(f"Error setting color: {str(e)}")
        
        try:
            if 'lineweight' in style:
                entity.dxf.lineweight = style['lineweight']
                log_debug(f"Set lineweight to: {style['lineweight']}")
            else:
                entity.dxf.lineweight = DEFAULT_ENTITY_STYLE['lineweight']
        except Exception as e:
            log_warning(f"Error setting lineweight: {str(e)}")
        
        # Set transparency
        try:
            if 'transparency' in style:
                transparency = convert_transparency(style['transparency'])
                if transparency is not None:
                    entity.transparency = transparency
                    log_debug(f"Set transparency to: {transparency}")
            else:
                entity.transparency = DEFAULT_ENTITY_STYLE['transparency']
        except Exception as e:
            log_warning(f"Error setting transparency: {str(e)}")

        # Apply linetype scale
        try:
            if 'linetypeScale' in style:
                ltscale = float(style['linetypeScale'])
                log_debug(f"Attempting to set ltscale to {ltscale}")
                
                # Get current ltscale for comparison
                try:
                    current_ltscale = entity.dxf.ltscale
                    log_debug(f"Current ltscale before setting: {current_ltscale}")
                except Exception as e:
                    log_debug(f"Could not read current ltscale: {str(e)}")
                
                # Set the new ltscale
                entity.dxf.ltscale = ltscale
                
                # Verify the change
                try:
                    new_ltscale = entity.dxf.ltscale
                    log_debug(f"New ltscale after setting: {new_ltscale}")
                except Exception as e:
                    log_warning(f"Could not verify new ltscale: {str(e)}")
            else:
                entity.dxf.ltscale = DEFAULT_ENTITY_STYLE['linetypeScale']
                log_debug(f"Set default ltscale: {DEFAULT_ENTITY_STYLE['linetypeScale']}")
        except Exception as e:
            log_warning(f"Error setting linetype scale: {str(e)}")

        # Handle polyline-specific properties
        if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            log_debug(f"Processing polyline-specific properties for {entity.dxftype()}")
            
            try:
                # Apply close property
                if 'close' in style:
                    entity.close(style['close'])
                    log_debug(f"Set close to: {style['close']}")
                else:
                    entity.close(DEFAULT_ENTITY_STYLE['close'])
            except Exception as e:
                log_warning(f"Error setting close property: {str(e)}")
            
            try:
                # Apply linetype generation
                if 'linetypeGeneration' in style:
                    # Get current flags
                    current_flags = entity.dxf.flags
                    log_debug(f"Current flags before linetypeGeneration: {current_flags}")
                    
                    if style['linetypeGeneration']:
                        entity.dxf.flags |= LWPOLYLINE_PLINEGEN
                    else:
                        entity.dxf.flags &= ~LWPOLYLINE_PLINEGEN
                    
                    # Verify the change
                    new_flags = entity.dxf.flags
                    log_debug(f"New flags after linetypeGeneration: {new_flags}")
                    log_debug(f"PLINEGEN bit is {'set' if new_flags & LWPOLYLINE_PLINEGEN else 'not set'}")
            except Exception as e:
                log_warning(f"Error setting linetype generation: {str(e)}")

        # Final verification of critical properties
        try:
            log_debug(f"Final entity state - Type: {entity.dxftype()}")
            if hasattr(entity.dxf, 'ltscale'):
                log_debug(f"Final ltscale: {entity.dxf.ltscale}")
            if hasattr(entity.dxf, 'flags') and entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
                log_debug(f"Final flags: {entity.dxf.flags}")
            if hasattr(entity.dxf, 'color'):
                log_debug(f"Final color: {entity.dxf.color}")
            if hasattr(entity.dxf, 'lineweight'):
                log_debug(f"Final lineweight: {entity.dxf.lineweight}")
            if hasattr(entity.dxf, 'linetype'):
                log_debug(f"Final linetype: {entity.dxf.linetype}")
        except Exception as e:
            log_warning(f"Error during final verification: {str(e)}")
            
    except Exception as e:
        log_error(f"Error applying style to entity: {str(e)}")
        # Don't re-raise to allow processing to continue

def _apply_text_style_properties(entity, text_style, name_to_aci=None):
    """Apply text-specific style properties."""
    if not text_style:
        text_style = DEFAULT_TEXT_STYLE.copy()
    
    log_debug(f"Applying text style properties to {entity.dxftype()}: {text_style}")

    try:
        # Basic properties
        try:
            entity.dxf.char_height = float(text_style.get('height', DEFAULT_TEXT_STYLE['height']))
            log_debug(f"Set text height to: {entity.dxf.char_height}")
        except Exception as e:
            log_warning(f"Error setting text height: {str(e)}")

        try:
            font = text_style.get('font', DEFAULT_TEXT_STYLE['font'])
            entity.dxf.style = font
            log_debug(f"Set text font to: {font}")
        except Exception as e:
            log_warning(f"Error setting text font: {str(e)}")
        
        # Color
        try:
            color = get_color_code(text_style.get('color', DEFAULT_TEXT_STYLE['color']), name_to_aci)
            if isinstance(color, tuple):
                entity.rgb = color
                log_debug(f"Set text RGB color to: {color}")
            else:
                entity.dxf.color = color
                log_debug(f"Set text ACI color to: {color}")
        except Exception as e:
            log_warning(f"Error setting text color: {str(e)}")

        # Attachment point
        try:
            attachment_key = text_style.get('attachmentPoint', DEFAULT_TEXT_STYLE['attachmentPoint']).upper()
            if attachment_key in TEXT_ATTACHMENT_POINTS:
                entity.dxf.attachment_point = TEXT_ATTACHMENT_POINTS[attachment_key]
                log_debug(f"Set text attachment point to: {attachment_key}")
            else:
                log_warning(f"Invalid attachment point: {attachment_key}")
        except Exception as e:
            log_warning(f"Error setting text attachment point: {str(e)}")

        # Flow direction (MTEXT specific)
        if hasattr(entity, 'dxf.flow_direction'):
            try:
                flow_key = text_style.get('flowDirection', DEFAULT_TEXT_STYLE['flowDirection']).upper()
                if flow_key in TEXT_FLOW_DIRECTIONS:
                    entity.dxf.flow_direction = TEXT_FLOW_DIRECTIONS[flow_key]
                    log_debug(f"Set text flow direction to: {flow_key}")
                else:
                    log_warning(f"Invalid flow direction: {flow_key}")
            except Exception as e:
                log_warning(f"Error setting text flow direction: {str(e)}")

        # Line spacing (MTEXT specific)
        if hasattr(entity, 'dxf.line_spacing_style'):
            try:
                spacing_key = text_style.get('lineSpacingStyle', DEFAULT_TEXT_STYLE['lineSpacingStyle']).upper()
                if spacing_key in TEXT_LINE_SPACING_STYLES:
                    entity.dxf.line_spacing_style = TEXT_LINE_SPACING_STYLES[spacing_key]
                    log_debug(f"Set line spacing style to: {spacing_key}")
                else:
                    log_warning(f"Invalid line spacing style: {spacing_key}")

                factor = float(text_style.get('lineSpacingFactor', DEFAULT_TEXT_STYLE['lineSpacingFactor']))
                entity.dxf.line_spacing_factor = factor
                log_debug(f"Set line spacing factor to: {factor}")
            except Exception as e:
                log_warning(f"Error setting line spacing properties: {str(e)}")

        # Background fill
        if hasattr(entity, 'set_bg_color'):
            try:
                if text_style.get('bgFill', DEFAULT_TEXT_STYLE['bgFill']):
                    bg_color = text_style.get('bgFillColor', DEFAULT_TEXT_STYLE['bgFillColor'])
                    bg_scale = float(text_style.get('bgFillScale', DEFAULT_TEXT_STYLE['bgFillScale']))
                    if bg_color:
                        entity.set_bg_color(bg_color, scale=bg_scale)
                        log_debug(f"Set background color to {bg_color} with scale {bg_scale}")
            except Exception as e:
                log_warning(f"Error setting background fill: {str(e)}")

        # Rotation
        try:
            rotation = float(text_style.get('rotation', DEFAULT_TEXT_STYLE['rotation']))
            entity.dxf.rotation = rotation
            log_debug(f"Set text rotation to: {rotation}")
        except Exception as e:
            log_warning(f"Error setting text rotation: {str(e)}")

        # Final verification of text properties
        try:
            log_debug(f"=== Final text entity state ===")
            log_debug(f"height: {getattr(entity.dxf, 'char_height', 'Not set')}")
            log_debug(f"style: {getattr(entity.dxf, 'style', 'Not set')}")
            log_debug(f"color: {getattr(entity.dxf, 'color', 'Not set')}")
            log_debug(f"attachment_point: {getattr(entity.dxf, 'attachment_point', 'Not set')}")
            log_debug(f"rotation: {getattr(entity.dxf, 'rotation', 'Not set')}")
            if hasattr(entity, 'dxf.flow_direction'):
                log_debug(f"flow_direction: {getattr(entity.dxf, 'flow_direction', 'Not set')}")
            if hasattr(entity, 'dxf.line_spacing_style'):
                log_debug(f"line_spacing_style: {getattr(entity.dxf, 'line_spacing_style', 'Not set')}")
                log_debug(f"line_spacing_factor: {getattr(entity.dxf, 'line_spacing_factor', 'Not set')}")
            log_debug(f"=== End final state ===")
        except Exception as e:
            log_warning(f"Error during final text property verification: {str(e)}")

    except Exception as e:
        log_error(f"Error applying text style properties: {str(e)}")
        # Don't re-raise to allow processing to continue

def linetype_exists(doc, linetype_name):
    """Check if a linetype exists in the document."""
    try:
        return linetype_name in doc.linetypes
    except:
        return False 