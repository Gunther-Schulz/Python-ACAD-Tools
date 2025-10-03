import random
import ezdxf
from ezdxf import enums
from ezdxf import colors
from ezdxf.lldxf.const import (
    MTEXT_TOP_LEFT, MTEXT_TOP_CENTER, MTEXT_TOP_RIGHT,
    MTEXT_MIDDLE_LEFT, MTEXT_MIDDLE_CENTER, MTEXT_MIDDLE_RIGHT,
    MTEXT_BOTTOM_LEFT, MTEXT_BOTTOM_CENTER, MTEXT_BOTTOM_RIGHT,
    MTEXT_LEFT_TO_RIGHT, MTEXT_TOP_TO_BOTTOM, MTEXT_BY_STYLE,
    MTEXT_AT_LEAST, MTEXT_EXACT
)
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec3
from src.utils import log_info, log_warning, log_error, log_debug, profile_operation, log_performance
import re
import math
from ezdxf.math import Vec2, area
from ezdxf.math import intersection_line_line_2d
import os
from ezdxf.lldxf.const import DXFValueError
from shapely.geometry import Polygon, Point, LineString
from shapely import MultiLineString, affinity, unary_union
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import numpy as np
import logging
import sys
import matplotlib.patches as patches
from ezdxf.tools.text import ParagraphProperties, MTextParagraphAlignment
from ezdxf.tools.text import MTextEditor
import traceback


SCRIPT_IDENTIFIER = "Created by DXFExporter"
XDATA_APP_ID = "DXFEXPORTER"

# XDATA structure constants
XDATA_ENTITY_NAME_KEY = "ENTITY_NAME"
XDATA_ENTITY_TYPE_KEY = "ENTITY_TYPE"
XDATA_CONTENT_HASH_KEY = "CONTENT_HASH"
XDATA_ENTITY_HANDLE_KEY = "ENTITY_HANDLE"
XDATA_SYNC_MODE_KEY = "SYNC_MODE"  # NEW: Track sync mode for entity lifecycle


def convert_newlines_to_mtext(text):
    """Convert newlines to MTEXT paragraph breaks for reliable MTEXT formatting.

    Handles both:
    - Actual newline characters (\n as chr(10))
    - Literal \n sequences from YAML strings

    Args:
        text (str): Text content with newlines

    Returns:
        str: Text with newlines converted to MTEXT paragraph breaks (\\P)
    """
    if not text:
        return text

    # Handle actual newline characters first
    result = text.replace('\n', '\\P')

    # Handle literal \n sequences from YAML (e.g., from single-quoted strings)
    result = result.replace('\\n', '\\P')

    return result

def create_entity_xdata(script_identifier, entity_name=None, entity_type=None, content_hash=None, entity_handle=None, sync_mode=None):
    """
    Create XDATA for entity identification and ownership tracking.
    Unified function that handles both simple ownership and named entity tracking.

    Args:
        script_identifier: The script identifier string
        entity_name: Optional name for entities that need to be found later
        entity_type: Optional entity type (e.g., 'VIEWPORT', 'TEXT')
        content_hash: Optional content hash for sync tracking
        entity_handle: Optional entity handle for identity validation
        sync_mode: Optional sync mode for entity lifecycle tracking ('push', 'auto', 'pull')

    Returns:
        list: XDATA tuple list - simple for unnamed entities, structured for named entities
    """
    if entity_name:
        # Named entity - use structured format for searchability
        xdata = [
            (1000, script_identifier),
            (1002, '{'),
            (1000, XDATA_ENTITY_NAME_KEY),
            (1000, entity_name),
        ]

        if entity_type:
            xdata.extend([
                (1000, XDATA_ENTITY_TYPE_KEY),
                (1000, entity_type),
            ])

        if content_hash:
            xdata.extend([
                (1000, XDATA_CONTENT_HASH_KEY),
                (1000, content_hash),
            ])

        if entity_handle:
            xdata.extend([
                (1000, XDATA_ENTITY_HANDLE_KEY),
                (1000, entity_handle),
            ])

        if sync_mode:
            xdata.extend([
                (1000, XDATA_SYNC_MODE_KEY),
                (1000, sync_mode),
            ])

        xdata.append((1002, '}'))
        return xdata
    else:
        # Unnamed entity - simple ownership tracking
        return [(1000, script_identifier)]

def find_entity_by_xdata_name(space, entity_name, entity_types=None):
    """
    Find an entity by its XDATA name using the standardized structure.

    Args:
        space: DXF space (modelspace or paperspace)
        entity_name: Name to search for
        entity_types: Optional list of DXF entity types to filter (e.g., ['TEXT', 'MTEXT'])

    Returns:
        Entity object if found, None otherwise
    """
    for entity in space:
        if entity_types and entity.dxftype() not in entity_types:
            continue

        try:
            xdata = entity.get_xdata(XDATA_APP_ID)
            if xdata:
                in_entity_section = False
                found_name = None

                for code, value in xdata:
                    if code == 1000 and value == XDATA_ENTITY_NAME_KEY:
                        in_entity_section = True
                    elif in_entity_section and code == 1000:
                        found_name = value
                        break

                if found_name == entity_name:
                    return entity
        except Exception:
            continue
    return None

def extract_content_hash_from_xdata(entity):
    """
    Extract content hash from entity XDATA.

    Args:
        entity: DXF entity with potential XDATA

    Returns:
        str: Content hash if found, None otherwise
    """
    try:
        xdata = entity.get_xdata(XDATA_APP_ID)
        if xdata:
            found_hash_key = False
            for code, value in xdata:
                if code == 1000 and value == XDATA_CONTENT_HASH_KEY:
                    found_hash_key = True
                elif found_hash_key and code == 1000:
                    return value
    except Exception:
        pass
    return None

def extract_handle_from_xdata(entity):
    """
    Extract entity handle from entity XDATA.

    Args:
        entity: DXF entity with potential XDATA

    Returns:
        str: Entity handle if found, None otherwise
    """
    try:
        xdata = entity.get_xdata(XDATA_APP_ID)
        if xdata:
            found_handle_key = False
            for code, value in xdata:
                if code == 1000 and value == XDATA_ENTITY_HANDLE_KEY:
                    found_handle_key = True
                elif found_handle_key and code == 1000:
                    return value
    except Exception:
        pass
    return None

def get_color_code(color, name_to_aci):
    if color is None:
        return 7  # Default to 7 (white) if no color is specified
    if isinstance(color, int):
        return color  # Return ACI code as-is
    elif isinstance(color, str):
        if ',' in color:
            # It's an RGB string
            try:
                return tuple(map(int, color.split(',')))
            except ValueError:
                log_warning(f"Invalid RGB color string: {color}")
                return 7  # Default to white if invalid
        else:
            # It's a color name
            aci_code = name_to_aci.get(color.lower())
            if aci_code is None:
                log_warning(f"Color name '{color}' not found in ACI color mapping. Defaulting to white (7).")
                return 7
            return aci_code
    elif isinstance(color, (list, tuple)) and len(color) == 3:
        # It's already an RGB tuple
        return tuple(color)
    else:
        return 7  # Default to 7 (white) for any other type

def convert_transparency(transparency):
    if isinstance(transparency, (int, float)):
        return min(max(transparency, 0), 1)  # Ensure value is between 0 and 1
    elif isinstance(transparency, str):
        try:
            return float(transparency)
        except ValueError:
            log_warning(f"Invalid transparency value: {transparency}")
    return None

def attach_custom_data(entity, script_identifier, entity_name=None, entity_type=None, content_hash=None, entity_handle=None, sync_mode=None):
    """Attaches custom data to an entity with proper cleanup of existing data."""
    try:
        # Clear any existing XDATA first
        try:
            entity.discard_xdata(XDATA_APP_ID)
        except:
            pass

        # Auto-extract entity handle if not provided
        if entity_handle is None and hasattr(entity, 'dxf') and hasattr(entity.dxf, 'handle'):
            entity_handle = str(entity.dxf.handle)

        # Set XDATA using unified function
        xdata = create_entity_xdata(script_identifier, entity_name, entity_type, content_hash, entity_handle, sync_mode)
        entity.set_xdata(XDATA_APP_ID, xdata)

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

def is_created_by_script(entity, script_identifier):
    """Check if an entity was created by this script."""
    try:
        xdata = entity.get_xdata(XDATA_APP_ID)
        if xdata:
            for code, value in xdata:
                if code == 1000 and value == script_identifier:
                    return True
    except ezdxf.lldxf.const.DXFValueError:
        # This exception is raised when the entity has no XDATA for XDATA_APP_ID
        # It's not an error, just means the entity wasn't created by this script
        return False
    except Exception as e:
        log_error(f"Unexpected error checking XDATA for entity {entity}: {str(e)}")
    return False

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
        align=enums.TextEntityAlignment.LEFT
    )
    return text_entity

def remove_entities_by_layer(msp, layer_names, script_identifier):
    with profile_operation("Remove Entities By Layer", f"layers: {layer_names}"):
        doc = msp.doc
        key_func = doc.layers.key
        delete_count = 0
        problem_entities = []

        # Convert single layer name to list
        if isinstance(layer_names, str):
            layer_names = [layer_names]

        # Convert layer names to keys
        layer_keys = [key_func(layer_name) for layer_name in layer_names]

        log_performance(f"Scanning for entities in {len(layer_names)} layers from document with {len(doc.entitydb)} total entities")

        # First pass: collect problematic entities
        with profile_operation("First Pass - Collect Problematic Entities"):
            for space in [doc.modelspace(), doc.paperspace()]:
                for entity in doc.entitydb.values():
                    try:
                        if not hasattr(entity, 'dxf') or not entity.dxf.hasattr("layer"):
                            continue

                        if key_func(entity.dxf.layer) in layer_keys and is_created_by_script(entity, script_identifier):
                            try:
                                # Test if we can safely handle this entity
                                _ = entity.dxf.handle
                            except Exception as e:
                                problem_entities.append((entity, str(e)))
                    except AttributeError:
                        continue

    # If there are problem entities, show summary and ask for confirmation
    if problem_entities:
        log_warning(f"\nFound {len(problem_entities)} potentially problematic entities:")
        error_types = {}
        for _, error in problem_entities:
            error_types[error] = error_types.get(error, 0) + 1

        for error, count in error_types.items():
            log_warning(f"- {count} entities with error: {error}")

        # Ask for confirmation
        response = input("\nDo you want to proceed with deletion? (y/N): ").lower()
        if response != 'y':
            log_info("Deletion cancelled by user")
            return 0

    # Proceed with deletion
    with doc.entitydb.trashcan() as trash:
        for space in [doc.modelspace(), doc.paperspace()]:
            for entity in doc.entitydb.values():
                try:
                    if not hasattr(entity, 'dxf') or not entity.dxf.hasattr("layer"):
                        continue

                    if key_func(entity.dxf.layer) in layer_keys and is_created_by_script(entity, script_identifier):
                        try:
                            # Clear any XDATA before deletion
                            try:
                                entity.discard_xdata(XDATA_APP_ID)
                            except:
                                pass

                            # Add to trashcan for safe deletion
                            trash.add(entity.dxf.handle)
                            delete_count += 1

                        except Exception as e:
                            continue
                except AttributeError:
                    continue

    # Try to perform cleanup operations
    try:
        doc.entitydb.purge()
    except Exception as e:
        log_warning(f"Database purge failed: {str(e)}")

    try:
        doc.audit()
    except Exception as e:
        log_warning(f"Document audit failed (this is not critical): {str(e)}")

    return delete_count

def remove_entities_by_layer_optimized(msp, layer_names, script_identifier):
    """
    Optimized version of remove_entities_by_layer using msp.query() for better performance.
    """
    with profile_operation("Remove Entities By Layer (Optimized)", f"layers: {layer_names}"):
        delete_count = 0

        # Convert single layer name to list
        if isinstance(layer_names, str):
            layer_names = [layer_names]

        log_performance(f"Optimized removal for {len(layer_names)} layers")

        for layer_name in layer_names:
            with profile_operation("Remove Layer Entities", layer_name):
                # Use query to efficiently find entities on this specific layer
                entities_to_remove = []

                # Query only entities on this layer - much faster than scanning all entities!
                layer_entities = msp.query(f'*[layer=="{layer_name}"]')

                log_performance(f"Found {len(layer_entities)} entities on layer {layer_name}")

                # Filter to only script-created entities
                for entity in layer_entities:
                    if is_created_by_script(entity, script_identifier):
                        entities_to_remove.append(entity)

                log_performance(f"Removing {len(entities_to_remove)} script-created entities from layer {layer_name}")

                # Remove the entities
                for entity in entities_to_remove:
                    try:
                        # Clear any XDATA before deletion
                        try:
                            entity.discard_xdata(XDATA_APP_ID)
                        except:
                            pass

                        # Delete the entity
                        msp.delete_entity(entity)
                        delete_count += 1
                    except Exception as e:
                        log_debug(f"Could not delete entity {entity.dxf.handle}: {e}")
                        continue

        log_performance(f"Total entities removed: {delete_count}")
        return delete_count

def update_layer_geometry(msp, layer_name, script_identifier, update_function):
    # Remove existing entities using optimized function
    remove_entities_by_layer_optimized(msp, layer_name, script_identifier)

    # Add new geometry
    update_function()

def ensure_layer_exists(doc, layer_name):
    """Ensure a layer exists in the DXF document."""
    if layer_name not in doc.layers:
        doc.layers.add(layer_name)
        log_debug(f"Created new layer: {layer_name}")
    else:
        log_debug(f"Layer already exists: {layer_name}")

def update_layer_properties(layer, layer_properties, name_to_aci):
    """Update layer properties with color, linetype, etc."""
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
        layer.dxf.lineweight = layer_properties['lineweight']
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

def ensure_text_style_exists(doc, style_name, style_config):
    """Ensure a text style exists in the DXF document."""
    if style_name not in doc.styles:
        try:
            style = doc.styles.new(style_name)
            style.dxf.font = style_config['font']
            style.dxf.height = style_config['height']
            style.dxf.width = 1.0  # Default width factor
            style.dxf.oblique = 0.0  # Default oblique angle
            style.dxf.last_height = 2.5  # Default last height
            log_debug(f"Added text style: {style_name}")
        except ezdxf.lldxf.const.DXFTableEntryError:
            log_warning(f"Failed to add text style: {style_name}")
    else:
        log_debug(f"Text style '{style_name}' already exists.")

def set_drawing_properties(doc):
    # Set the properties
    doc.header['$MEASUREMENT'] = 1  # 1 for metric, 0 for imperial
    doc.header['$INSUNITS'] = 6  # 6 for meters
    doc.header['$LUNITS'] = 2  # 2 for decimal units
    doc.header['$LUPREC'] = 4  # Precision for linear units
    doc.header['$AUPREC'] = 4  # Precision for angular units

    # Define meaning of values
    measurement_meaning = {
        0: "Imperial (inches, feet)",
        1: "Metric (millimeters, meters)"
    }

    insunits_meaning = {
        0: "Unitless",
        1: "Inches",
        2: "Feet",
        3: "Miles",
        4: "Millimeters",
        5: "Centimeters",
        6: "Meters",
        7: "Kilometers",
        8: "Microinches",
        9: "Mils",
        10: "Yards",
        11: "Angstroms",
        12: "Nanometers",
        13: "Microns",
        14: "Decimeters",
        15: "Decameters",
        16: "Hectometers",
        17: "Gigameters",
        18: "Astronomical units",
        19: "Light years",
        20: "Parsecs"
    }

    lunits_meaning = {
        1: "Scientific",
        2: "Decimal",
        3: "Engineering",
        4: "Architectural",
        5: "Fractional"
    }

    # Log and print the settings with their meanings
    log_debug("\n=== Drawing Properties Set ===")

    # MEASUREMENT
    measurement_msg = f"$MEASUREMENT: {doc.header['$MEASUREMENT']} - {measurement_meaning.get(doc.header['$MEASUREMENT'], 'Unknown')}"
    log_debug(measurement_msg)

    # INSUNITS
    insunits_msg = f"$INSUNITS: {doc.header['$INSUNITS']} - {insunits_meaning.get(doc.header['$INSUNITS'], 'Unknown')}"
    log_debug(insunits_msg)

    # LUNITS
    lunits_msg = f"$LUNITS: {doc.header['$LUNITS']} - {lunits_meaning.get(doc.header['$LUNITS'], 'Unknown')}"
    log_debug(lunits_msg)

    # LUPREC
    luprec_msg = f"$LUPREC: {doc.header['$LUPREC']} - Linear units precision (number of decimal places)"
    log_debug(luprec_msg)

    # AUPREC
    auprec_msg = f"$AUPREC: {doc.header['$AUPREC']} - Angular units precision (number of decimal places)"
    log_debug(auprec_msg)

    log_debug("\n=== End of Drawing Properties ===")

def verify_dxf_settings(filename):
    # Skip verification unless explicitly requested (it's expensive - reloads entire DXF!)
    if os.getenv('VERIFY_DXF_SETTINGS') != '1':
        log_debug("DXF settings verification skipped (set VERIFY_DXF_SETTINGS=1 to enable)")
        return

    with profile_operation("DXF Settings Verification (Debug)"):
        loaded_doc = ezdxf.readfile(filename)

        # Define meaning of values
        measurement_meaning = {
            0: "Imperial (inches, feet)",
            1: "Metric (millimeters, meters)"
        }

        insunits_meaning = {
            0: "Unitless", 1: "Inches", 2: "Feet", 3: "Miles",
            4: "Millimeters", 5: "Centimeters", 6: "Meters", 7: "Kilometers",
            8: "Microinches", 9: "Mils", 10: "Yards", 11: "Angstroms",
            12: "Nanometers", 13: "Microns", 14: "Decimeters", 15: "Decameters",
            16: "Hectometers", 17: "Gigameters", 18: "Astronomical units",
            19: "Light years", 20: "Parsecs"
        }

        lunits_meaning = {
            1: "Scientific", 2: "Decimal", 3: "Engineering",
            4: "Architectural", 5: "Fractional"
        }

        log_debug("\n=== Verifying DXF Settings ===")

        measurement = loaded_doc.header.get('$MEASUREMENT', None)
        measurement_msg = f"$MEASUREMENT: {measurement} - {measurement_meaning.get(measurement, 'Unknown')}"
        log_debug(measurement_msg)

        insunits = loaded_doc.header.get('$INSUNITS', None)
        insunits_msg = f"$INSUNITS: {insunits} - {insunits_meaning.get(insunits, 'Unknown')}"
        log_debug(insunits_msg)

        lunits = loaded_doc.header.get('$LUNITS', None)
        lunits_msg = f"$LUNITS: {lunits} - {lunits_meaning.get(lunits, 'Unknown')}"
        log_debug(lunits_msg)

        luprec = loaded_doc.header.get('$LUPREC', None)
        luprec_msg = f"$LUPREC: {luprec} - Linear units precision (decimal places)"
        log_debug(luprec_msg)

        auprec = loaded_doc.header.get('$AUPREC', None)
        auprec_msg = f"$AUPREC: {auprec} - Angular units precision (decimal places)"
        log_debug(auprec_msg)

        log_debug("=== End of DXF Settings Verification ===\n")

def get_style(style, project_loader):
    if isinstance(style, str):
        return project_loader.get_style(style)
    return style

def linetype_exists(doc, linetype):
    return linetype in doc.linetypes

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
                # Convert color name to proper color code
                color_code = get_color_code(bg_color, name_to_aci)
                entity.set_bg_color(color_code, scale=bg_scale)

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

def apply_style_to_entity(entity, style, project_loader, loaded_styles=None, item_type='area'):
    """Apply style properties to any DXF entity."""
    if entity.dxftype() in ('MTEXT', 'TEXT'):
        _apply_text_style_properties(entity, style, project_loader.name_to_aci)

    # Apply non-text properties
    if 'color' in style:
        color = get_color_code(style['color'], project_loader.name_to_aci)
        if isinstance(color, tuple):
            entity.rgb = color
        else:
            entity.dxf.color = color
    else:
        entity.dxf.color = ezdxf.const.BYLAYER

    if 'linetype' in style:
        if linetype_exists(entity.doc, style['linetype']):
            entity.dxf.linetype = style['linetype']
        else:
            log_warning(f"Linetype '{style['linetype']}' not defined. Using 'BYLAYER'.")
            entity.dxf.linetype = 'BYLAYER'

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

def create_hatch(msp, boundary_paths, hatch_config, project_loader):
    hatch = msp.add_hatch()

    pattern = hatch_config.get('pattern', 'SOLID')
    pattern_scale = hatch_config.get('scale', 1)
    pattern_angle = hatch_config.get('angle', 0)

    if pattern != 'SOLID':
        try:
            hatch.set_pattern_fill(pattern, scale=pattern_scale, angle=pattern_angle)
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

def add_mtext(msp, text, x, y, layer_name, style_name, text_style=None, name_to_aci=None, max_width=None):
    """Add MTEXT entity with comprehensive style support."""
    log_debug(f"=== Starting MTEXT creation ===")
    log_debug(f"Text: '{text}'")
    log_debug(f"Position: ({x}, {y})")
    log_debug(f"Layer: '{layer_name}'")
    log_debug(f"Style name: '{style_name}'")
    log_debug(f"Text style config: {text_style}")

    # Convert newlines to MTEXT paragraph breaks for reliable formatting
    mtext_formatted_text = convert_newlines_to_mtext(text)
    log_debug(f"MTEXT formatted text: '{mtext_formatted_text}'")

    # Build basic dxfattribs
    dxfattribs = {
        'style': style_name,
        'layer': layer_name,
        'char_height': text_style.get('height', 2.5),
        'width': text_style.get('maxWidth', max_width) if max_width is not None else 0,
        'insert': (x, y)
    }

    try:
        # Create the MTEXT entity with properly formatted text
        mtext = msp.add_mtext(mtext_formatted_text, dxfattribs=dxfattribs)

        # Apply common text style properties
        _apply_text_style_properties(mtext, text_style, name_to_aci)

        # Note: XDATA attachment is handled by the caller to ensure proper entity naming

        log_debug(f"=== Completed MTEXT creation ===")
        actual_height = mtext.dxf.char_height * mtext.dxf.line_spacing_factor * len(mtext_formatted_text.split('\\P'))
        return mtext, actual_height

    except Exception as e:
        log_error(f"Failed to add MTEXT: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return None, 0

def sanitize_layer_name(name):
    # Define a set of allowed characters, including German-specific ones, space, dash, underscore, and periods
    allowed_chars = r'a-zA-Z0-9_\-öüäßÖÜÄ .'

    # Check for forbidden characters and issue warning
    forbidden_chars = re.findall(f'[^{allowed_chars}]', name)
    if forbidden_chars:
        unique_forbidden = list(set(forbidden_chars))
        log_warning(f"DXF Layer name '{name}' contains forbidden characters: {unique_forbidden} - sanitizing to replace with underscores")

    # Actually sanitize the name by replacing forbidden characters with underscores
    sanitized_name = re.sub(f'[^{allowed_chars}]', '_', name)

    # Clean up multiple consecutive underscores
    sanitized_name = re.sub(r'_+', '_', sanitized_name)

    # Remove leading/trailing underscores
    sanitized_name = sanitized_name.strip('_')

    # Check if name starts with an invalid character (space) and fix it
    if sanitized_name.startswith(' '):
        log_warning(f"DXF Layer name '{name}' starts with a space, removing it.")
        sanitized_name = sanitized_name.lstrip(' ')

    # Check if name starts with a number (which may cause issues in some CAD software)
    if sanitized_name and sanitized_name[0].isdigit():
        log_warning(f"DXF Layer name '{name}' starts with a number, which may cause compatibility issues.")
        sanitized_name = f"Layer_{sanitized_name}"

    # Check length limit and truncate if necessary
    if len(sanitized_name) > 255:
        log_warning(f"DXF Layer name '{name}' is {len(sanitized_name)} characters long, exceeding the 255 character limit.")
        log_warning(f"Truncating layer name to 255 characters.")
        sanitized_name = sanitized_name[:255]

    # Ensure we don't return an empty string
    if not sanitized_name:
        sanitized_name = "Unknown_Layer"
        log_warning(f"Layer name '{name}' resulted in empty string after sanitization, using 'Unknown_Layer'")

    # Log the change if the name was modified
    if sanitized_name != name:
        log_debug(f"Sanitized layer name: '{name}' → '{sanitized_name}'")

    return sanitized_name

def load_standard_text_styles(doc):
    standard_styles = [
        ('Standard', 'Arial', 0.0),
        ('Arial', 'Arial', 0.0),
        ('Arial Narrow', 'Arial Narrow', 0.0),
        ('Isocpeur', 'Isocpeur', 0.0),
        ('Isocp', 'Isocp', 0.0),
        ('Romantic', 'Romantic', 0.0),
        ('Romans', 'Romans', 0.0),
        ('Romand', 'Romand', 0.0),
        ('Romant', 'Romant', 0.0),
    ]

    loaded_styles = set()

    for style_name, font, height in standard_styles:
        if style_name not in doc.styles:
            try:
                style = doc.styles.new(style_name)
                style.dxf.font = font
                style.dxf.height = height
                style.dxf.width = 1.0  # Default width factor
                style.dxf.oblique = 0.0  # Default oblique angle
                style.dxf.last_height = 2.5  # Default last height
                loaded_styles.add(style_name)
                log_debug(f"Added standard text style: {style_name}")
            except ezdxf.lldxf.const.DXFTableEntryError:
                log_warning(f"Failed to add standard text style: {style_name}")
        else:
            loaded_styles.add(style_name)

    return loaded_styles

# This function should be called once when the document is loaded
def initialize_document(doc):
    loaded_styles = load_standard_text_styles(doc)
    return loaded_styles

def get_available_blocks(doc):
    return set(block.name for block in doc.blocks if not block.name.startswith('*'))

def add_block_reference(msp, block_name, insert_point, layer_name, scale=1.0, rotation=0.0):
    # Validate input parameters
    if not block_name:
        log_warning("Cannot create block reference: block_name is empty or None")
        return None

    if not isinstance(block_name, str):
        log_warning(f"Cannot create block reference: block_name must be string, got {type(block_name)}")
        return None

    if not msp or not hasattr(msp, 'doc') or not msp.doc:
        log_warning("Cannot create block reference: invalid modelspace or document")
        return None

    if block_name not in msp.doc.blocks:
        try:
            # Try to list available blocks for debugging
            available_blocks = [block.name for block in msp.doc.blocks]
            log_warning(f"Block '{block_name}' not found in the document. Available blocks: {available_blocks[:10]}...")
        except Exception as e:
            log_warning(f"Block '{block_name}' not found in the document. Could not list available blocks: {str(e)}")
        return None

    try:
        block_ref = msp.add_blockref(block_name, insert_point)
        block_ref.dxf.layer = layer_name
        block_ref.dxf.xscale = scale
        block_ref.dxf.yscale = scale
        block_ref.dxf.rotation = rotation
        # Note: XDATA attachment is handled by the caller to ensure proper entity naming
        log_debug(f"Successfully created block reference for '{block_name}' on layer '{layer_name}'")
        return block_ref
    except Exception as e:
        log_error(f"Error creating block reference for '{block_name}': {str(e)}")
        return None

def cleanup_document(doc):
    """Perform thorough document cleanup."""
    try:
        # Run audit to fix potential structural issues
        auditor = doc.audit()
        if len(auditor.errors) > 0:
            log_warning(f"Audit found {len(auditor.errors)} issues")

        # Clean up empty groups
        for group in doc.groups:
            if len(group) == 0:
                doc.groups.remove(group.dxf.name)

        # Purge unused blocks
        modelspace = doc.modelspace()
        paperspace = doc.paperspace()
        used_blocks = set()

        # Check modelspace for block references
        for insert in modelspace.query('INSERT'):
            used_blocks.add(insert.dxf.name)

        # Check paperspace for block references
        for insert in paperspace.query('INSERT'):
            used_blocks.add(insert.dxf.name)

        # Remove unused blocks
        for block in list(doc.blocks):
            block_name = block.name

            # Skip special blocks, used blocks, and AutoCAD special blocks
            if (block_name.startswith('_') or
                block_name.startswith('*') or
                block_name.startswith('A$C') or
                block_name in used_blocks):
                continue

            try:
                doc.blocks.delete_block(block_name)
                log_debug(f"Removed unused block: {block_name}")
            except Exception as e:
                # Only log errors that aren't related to block being in use
                if "still in use" not in str(e):
                    log_warning(f"Could not remove block {block_name}: {str(e)}")

        # Purge unused layers
        for layer in list(doc.layers):
            layer_name = layer.dxf.name

            # Skip system layers (0, Defpoints)
            if layer_name in ['0', 'Defpoints']:
                continue

            # Check if the layer has any entities
            has_entities = False

            # Check modelspace
            for entity in modelspace:
                if entity.dxf.layer == layer_name:
                    has_entities = True
                    break

            # If not found in modelspace, check paperspace
            if not has_entities:
                for entity in paperspace:
                    if entity.dxf.layer == layer_name:
                        has_entities = True
                        break

            # Remove empty layer
            if not has_entities:
                try:
                    doc.layers.remove(layer_name)
                    log_debug(f"Removed empty layer: {layer_name}")
                except Exception as e:
                    log_warning(f"Could not remove layer {layer_name}: {str(e)}")

        # Purge unused linetypes
        for linetype in list(doc.linetypes):
            try:
                doc.linetypes.remove(linetype.dxf.name)
            except Exception as e:
                # Skip if linetype is in use or is a default linetype
                continue

        # Purge unused text styles
        for style in list(doc.styles):
            try:
                doc.styles.remove(style.dxf.name)
            except Exception as e:
                # Skip if style is in use or is a default style
                continue

        # Purge unused dimension styles
        for dimstyle in list(doc.dimstyles):
            try:
                doc.dimstyles.remove(dimstyle.dxf.name)
            except Exception as e:
                # Skip if dimstyle is in use or is a default style
                continue

        # Force database update
        doc.entitydb.purge()

        log_debug("Document cleanup completed successfully")

    except Exception as e:
        log_error(f"Error during document cleanup: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")

def atomic_save_dxf(doc, target_path, create_backup=True):
    """
    Safely save a DXF document using atomic write operations.

    This method:
    1. Creates a backup of the existing file (if it exists and create_backup=True)
    2. Writes to a temporary file first
    3. Only moves the temp file to the target location if successful
    4. This ensures we never have a partially written file at the target location

    Args:
        doc: The ezdxf document to save
        target_path: The final path where the file should be saved
        create_backup: Whether to create a backup of existing file (default: True)

    Returns:
        bool: True if successful, False otherwise
    """
    import tempfile
    import shutil

    target_path = str(target_path)  # Ensure string path

    try:
        # Step 1: Create backup of existing file if it exists and backup is requested
        backup_path = None
        with profile_operation("Backup Creation"):
            if create_backup and os.path.exists(target_path):
                backup_path = f"{target_path}.ezdxf_bak"
                shutil.copy2(target_path, backup_path)
                log_info(f"Created backup: {backup_path}")

        # Step 2: Create temporary file in the same directory as target
        # This ensures the temp file is on the same filesystem for atomic move
        with profile_operation("Temp File Creation"):
            target_dir = os.path.dirname(target_path) or '.'
            target_basename = os.path.basename(target_path)
            temp_fd = None
            temp_path = None

            # Create temporary file with similar name for easier identification
            temp_fd, temp_path = tempfile.mkstemp(
                prefix=f".{target_basename}.tmp.",
                suffix=".dxf",
                dir=target_dir
            )
            os.close(temp_fd)  # Close the file descriptor, we'll use ezdxf's save method

            log_debug(f"Writing to temporary file: {temp_path}")

        try:
            # Step 3: Save to temporary file - THIS IS LIKELY THE SLOW PART
            with profile_operation("ezdxf doc.saveas()"):
                doc.saveas(temp_path)
                log_debug(f"Successfully wrote temporary file: {temp_path}")

            # Step 4: Atomic move - this is the critical atomic operation
            # On most filesystems, rename/move is atomic if source and destination are on same filesystem
            with profile_operation("File Move/Rename"):
                if os.name == 'nt':  # Windows
                    # On Windows, we need to remove the target first if it exists
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    shutil.move(temp_path, target_path)
                else:  # Unix-like systems
                    os.rename(temp_path, target_path)

            log_info(f"Successfully saved DXF file: {target_path}")
            return True

        except Exception as e:
            # Clean up temporary file if something went wrong
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    log_debug(f"Cleaned up temporary file: {temp_path}")
                except:
                    log_warning(f"Could not clean up temporary file: {temp_path}")

            # If we created a backup and the save failed, we could optionally restore it
            # but since the original file wasn't touched yet, this may not be necessary

            raise e  # Re-raise the original exception

    except Exception as e:
        log_error(f"Failed to save DXF file to {target_path}: {str(e)}")
        return False

def polygon_patch(polygon):
    """Convert Shapely polygon to matplotlib patch"""
    def ring_coding(x):
        codes = np.ones(len(x), dtype=Path.code_type) * Path.LINETO
        codes[0] = Path.MOVETO
        return codes

    def ring_coord(x):
        return np.array(x).reshape(-1, 2)

    vertices = []
    codes = []
    for ring in [polygon.exterior] + list(polygon.interiors):
        vertices.append(ring_coord(ring.coords))
        codes.append(ring_coding(ring.coords))

    vertices = np.concatenate(vertices)
    codes = np.concatenate(codes)

    return PathPatch(Path(vertices, codes))


def delete_entities_clean(entities, purge_threshold=10):
    """
    Centralized clean deletion of DXF entities.

    This function provides a safe and clean way to delete entities from a DXF document,
    following the same pattern used throughout the dxf_utils module.

    Args:
        entities: List of (entity, entity_name) tuples or list of entities
        purge_threshold: If more than this many entities are deleted, purge the database

    Returns:
        int: Number of entities successfully deleted
    """
    if not entities:
        return 0

    # Normalize input - handle both entity lists and (entity, name) tuples
    entity_list = []
    for item in entities:
        if isinstance(item, tuple):
            entity, name = item
            entity_list.append((entity, name))
        else:
            entity_list.append((item, getattr(item, 'name', 'unnamed')))

    deleted_count = 0
    doc = None

    for entity, entity_name in entity_list:
        try:
            # Store doc reference for potential purge later
            if not doc and hasattr(entity, 'doc'):
                doc = entity.doc

            # 1. Clear any XDATA before deletion (clean up metadata)
            try:
                entity.discard_xdata(XDATA_APP_ID)
            except:
                pass  # Ignore XDATA cleanup failures

            # 2. Get the proper space for deletion
            entity_space = _get_entity_space(entity)

            # 3. Use space.delete_entity() for clean deletion
            if entity_space:
                entity_space.delete_entity(entity)
                log_info(f"🗑️  DELETED: Entity '{entity_name}' from DXF")
                deleted_count += 1
            else:
                log_warning(f"Could not determine space for entity '{entity_name}' - skipping deletion")

        except Exception as e:
            log_warning(f"Failed to delete entity '{entity_name}': {str(e)}")

    # 4. Clean up database if we deleted many entities (bulk deletion optimization)
    if deleted_count > purge_threshold and doc:
        try:
            log_debug(f"Purging database after deleting {deleted_count} entities")
            doc.entitydb.purge()
        except Exception as e:
            log_debug(f"Database purge after entity deletion failed: {str(e)}")

    return deleted_count


def _get_entity_space(entity):
    """
    Get the appropriate space (modelspace/paperspace) for an entity using reliable owner-based detection.

    Args:
        entity: DXF entity

    Returns:
        space: The space containing the entity, or None if not found
    """
    try:
        doc = entity.doc
        if not doc:
            return None

        # Use reliable owner-based detection instead of unreliable iteration
        paperspace = detect_entity_paperspace(entity)

        if paperspace is True:
            return doc.paperspace()
        elif paperspace is False:
            return doc.modelspace()
        else:
            # Detection failed - fallback to modelspace as safe default
            log_debug(f"Owner-based space detection failed for entity {getattr(entity.dxf, 'handle', 'unknown')}, using modelspace")
            return doc.modelspace()

    except Exception as e:
        log_debug(f"Error determining entity space: {str(e)}")
        return None

def remove_entities_by_layer_and_sync_mode(space, layer_name, script_identifier, sync_mode=None):
    """
    Remove entities from a layer with sync mode awareness.

    Args:
        space: DXF space (modelspace or paperspace)
        layer_name: Name of the layer to clean
        script_identifier: Script identifier to match
        sync_mode: Optional sync mode filter ('push', 'auto', 'pull', None for all)

    Returns:
        int: Number of entities removed
    """
    with profile_operation("Remove Entities By Layer and Sync Mode", f"layer: {layer_name}, mode: {sync_mode}"):
        delete_count = 0

        # Query entities on the specific layer
        layer_entities = space.query(f'*[layer=="{layer_name}"]')
        entities_to_remove = []

        for entity in layer_entities:
            try:
                # Check if entity was created by our script
                if not is_created_by_script(entity, script_identifier):
                    continue

                # If sync mode filter is specified, check it
                if sync_mode is not None:
                    entity_sync_mode = _extract_sync_mode_from_xdata(entity)
                    if entity_sync_mode != sync_mode:
                        continue

                entities_to_remove.append(entity)

            except Exception as e:
                log_debug(f"Error checking entity for removal: {str(e)}")
                continue

        # Remove the entities
        for entity in entities_to_remove:
            try:
                # Clear XDATA before deletion
                try:
                    entity.discard_xdata(XDATA_APP_ID)
                except:
                    pass

                # Delete the entity
                space.delete_entity(entity)
                delete_count += 1

            except Exception as e:
                log_debug(f"Could not delete entity {getattr(entity.dxf, 'handle', 'unknown')}: {e}")
                continue

        log_debug(f"Removed {delete_count} entities from layer '{layer_name}' with sync mode '{sync_mode}'")
        return delete_count


def _extract_sync_mode_from_xdata(entity):
    """
    Extract sync mode from entity XDATA.

    Args:
        entity: DXF entity

    Returns:
        str: Sync mode ('push', 'auto', 'pull') or None if not found
    """
    try:
        xdata = entity.get_xdata(XDATA_APP_ID)
        if not xdata:
            return None

        # Look for sync mode in XDATA
        in_structured_data = False
        next_is_sync_mode = False

        for code, value in xdata:
            if code == 1002 and value == '{':
                in_structured_data = True
            elif code == 1002 and value == '}':
                in_structured_data = False
            elif in_structured_data and code == 1000:
                if value == XDATA_SYNC_MODE_KEY:
                    next_is_sync_mode = True
                elif next_is_sync_mode:
                    return value
                else:
                    next_is_sync_mode = False

        return None

    except Exception:
        return None


def clean_layer_by_sync_mode(doc, layer_name, script_identifier, sync_mode, spaces=None):
    """
    Clean a layer with sync mode awareness.

    Args:
        doc: DXF document
        layer_name: Layer to clean
        script_identifier: Script identifier
        sync_mode: Sync mode to target ('push' for bulk, 'auto' for selective, etc.)
        spaces: List of spaces to clean (default: both model and paper space)

    Returns:
        int: Total number of entities removed
    """
    if spaces is None:
        spaces = [doc.modelspace(), doc.paperspace()]

    total_removed = 0

    for space in spaces:
        removed = remove_entities_by_layer_and_sync_mode(space, layer_name, script_identifier, sync_mode)
        total_removed += removed

    log_debug(f"Cleaned layer '{layer_name}' for sync mode '{sync_mode}': {total_removed} entities removed")
    return total_removed


def remove_specific_entity_by_handle(space, entity_handle, script_identifier):
    """
    Remove a specific entity by its handle (for selective auto sync updates).

    Args:
        space: DXF space
        entity_handle: Handle of entity to remove
        script_identifier: Script identifier to verify ownership

    Returns:
        bool: True if entity was removed, False otherwise
    """
    try:
        entity = space.get_entity_by_handle(entity_handle)

        if entity and is_created_by_script(entity, script_identifier):
            # Clear XDATA before deletion
            try:
                entity.discard_xdata(XDATA_APP_ID)
            except:
                pass

            # Delete the entity
            space.delete_entity(entity)
            log_debug(f"Removed specific entity with handle: {entity_handle}")
            return True

    except Exception as e:
        log_debug(f"Could not remove entity with handle {entity_handle}: {str(e)}")

    return False

def read_cad_layer_to_geodataframe(doc, layer_name, crs, entity_types=None):
    """
    Read geometry from a CAD layer and return as GeoDataFrame.
    Uses existing convert_entity_to_geometry() infrastructure for robust conversion.

    Args:
        doc: DXF document
        layer_name: Name of the layer to read
        crs: Coordinate reference system for the GeoDataFrame
        entity_types: Optional list of entity types to filter by (e.g., ['LINE', 'LWPOLYLINE'])

    Returns:
        GeoDataFrame with geometries from the specified layer
    """
    from src.dump_to_shape import convert_entity_to_geometry
    import geopandas as gpd
    from src.utils import log_debug, log_warning

    geometries = []
    attributes = []

    # Get model space
    msp = doc.modelspace()

    log_debug(f"Reading geometries from CAD layer: {layer_name}")

    # Collect entities from the specified layer
    entity_count = 0
    entities_by_type = {}

    for entity in msp:
        try:
            # Check if entity has layer attribute and matches target layer
            if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer'):
                if entity.dxf.layer == layer_name:
                    entity_type = entity.dxftype()

                    # Track entity types for debugging
                    entities_by_type[entity_type] = entities_by_type.get(entity_type, 0) + 1

                    # Filter by entity type if specified
                    if entity_types and entity_type not in entity_types:
                        continue

                    # Convert entity to Shapely geometry using existing converter
                    geom = convert_entity_to_geometry(entity)
                    if geom:
                        geometries.append(geom)
                        # Basic attributes - could be extended to include entity properties
                        attributes.append({
                            'entity_type': entity_type,
                            'handle': getattr(entity.dxf, 'handle', None)
                        })
                        entity_count += 1
        except Exception as e:
            log_warning(f"Error processing entity in layer {layer_name}: {str(e)}")
            continue

    # Log entity type summary for debugging
    if entities_by_type:
        log_debug(f"Found entity types in layer {layer_name}: {entities_by_type}")

        # If we found entities but no geometries, that's a conversion issue
        total_entities_found = sum(entities_by_type.values())
        if total_entities_found > 0 and entity_count == 0:
            log_warning(f"Found {total_entities_found} entities in layer {layer_name} but none converted to valid geometry")

    log_debug(f"Successfully read {entity_count} geometries from layer {layer_name}")

    # Create GeoDataFrame
    if geometries:
        gdf = gpd.GeoDataFrame(geometry=geometries, data=attributes, crs=crs)
        return gdf
    else:
        return gpd.GeoDataFrame(geometry=[], crs=crs)

def detect_entity_paperspace(entity):
    """
    Reliably detect if an entity is in paperspace using DXF owner-based detection.

    This function uses the entity's actual layout ownership to determine paperspace,
    which is more reliable than iteration-based or attribute-based heuristics.

    Args:
        entity: DXF entity (TEXT, MTEXT, INSERT, etc.)

    Returns:
        bool: True if entity is in paperspace, False if in modelspace
        None: If detection failed (caller should handle gracefully)
    """
    try:
        # Get the entity's owner (layout handle) - this is the DXF-standard way
        owner_handle = entity.dxf.owner
        doc = entity.doc
        layout_record = doc.entitydb[owner_handle]
        layout_name = layout_record.dxf.name

        # According to DXF spec - this is deterministic and reliable:
        # - "*Model_Space" = modelspace (paperspace = false)
        # - "*Paper_Space*" = any paperspace (paperspace = true)
        return layout_name.startswith('*Paper_Space')

    except Exception as e:
        log_debug(f"Could not determine paperspace for entity {getattr(entity.dxf, 'handle', 'unknown')}: {str(e)}")
        return None
