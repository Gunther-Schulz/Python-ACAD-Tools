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
from src.utils import log_info, log_warning, log_error
import re
import math
from ezdxf.math import Vec2, area
from ezdxf.math import intersection_line_line_2d
import os
from ezdxf.lldxf.const import DXFValueError
from shapely.geometry import Polygon, Point, LineString
from shapely import MultiLineString, affinity, unary_union
import matplotlib.pyplot as plt
from descartes import PolygonPatch
import numpy as np
import logging
import sys
import matplotlib.patches as patches
from ezdxf.tools.text import ParagraphProperties, MTextParagraphAlignment
from ezdxf.tools.text import MTextEditor
import traceback


SCRIPT_IDENTIFIER = "Created by DXFExporter"

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

def attach_custom_data(entity, script_identifier, entity_name=None):
    """Attaches custom data to an entity with proper cleanup of existing data."""
    try:
        # NEW: Clear any existing XDATA first
        try:
            entity.discard_xdata('DXFEXPORTER')
        except:
            pass
            
        # Set new XDATA
        entity.set_xdata(
            'DXFEXPORTER',
            [(1000, script_identifier)]
        )
        
        # NEW: Ensure entity is properly added to the document database
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
    doc = msp.doc
    key_func = doc.layers.key
    delete_count = 0
    
    # Convert single layer name to list
    if isinstance(layer_names, str):
        layer_names = [layer_names]
    
    # Convert layer names to keys
    layer_keys = [key_func(layer_name) for layer_name in layer_names]
    
    # Use trashcan context manager for safe entity deletion
    with doc.entitydb.trashcan() as trash:
        # Process all entities in both model and paper space
        for space in [doc.modelspace(), doc.paperspace()]:
            for entity in doc.entitydb.values():
                if not entity.dxf.hasattr("layer"):
                    continue
                    
                if key_func(entity.dxf.layer) in layer_keys and is_created_by_script(entity, script_identifier):
                    try:
                        # Clear any XDATA before deletion
                        try:
                            entity.discard_xdata('DXFEXPORTER')
                        except:
                            pass

                        # Clear any hyperlinks if supported
                        if hasattr(entity, 'set_hyperlink'):
                            try:
                                entity.remove_hyperlink()
                            except:
                                pass

                        # Clear any extension dictionary
                        if hasattr(entity, 'has_extension_dict') and entity.has_extension_dict:
                            try:
                                entity.discard_extension_dict()
                            except:
                                pass

                        # Clean up any reactors
                        if hasattr(entity, 'reactors') and entity.reactors is not None:  # Add None check
                            for reactor in entity.reactors:
                                try:
                                    trash.add(reactor)
                                except:
                                    pass
                        
                        # Clean up any dependent entities (like dimensions)
                        if hasattr(entity, 'dependent_entities'):
                            try:
                                dependents = entity.dependent_entities()
                                if dependents is not None:  # Add None check
                                    for dependent in dependents:
                                        try:
                                            trash.add(dependent.dxf.handle)
                                        except:
                                            pass
                            except:
                                pass
                        
                        # Add to trashcan for safe deletion
                        trash.add(entity.dxf.handle)
                        delete_count += 1
                        
                    except Exception as e:
                        log_error(f"Error preparing entity for deletion: {str(e)}")
                        log_error(f"Traceback:\n{traceback.format_exc()}")
                        continue  # Continue with next entity even if this one fails
    
    # Force database purge and audit
    try:
        doc.entitydb.purge()
        doc.audit()
    except Exception as e:
        log_error(f"Error during document cleanup: {str(e)}")
    
    return delete_count

def update_layer_geometry(msp, layer_name, script_identifier, update_function):
    # Remove existing entities
    remove_entities_by_layer(msp, layer_name, script_identifier)
    
    # Add new geometry
    update_function()

def ensure_layer_exists(doc, layer_name, properties=None, name_to_aci=None):
    """Ensures a layer exists in the document with the given properties."""
    if layer_name not in doc.layers:
        dxfattribs = {}
        if properties:
            if 'color' in properties:
                color = get_color_code(properties['color'], name_to_aci) if name_to_aci else properties['color']
                dxfattribs['color'] = color
            if 'linetype' in properties:
                dxfattribs['linetype'] = properties['linetype']
            if 'lineweight' in properties:
                dxfattribs['lineweight'] = properties['lineweight']
            if 'plot' in properties:
                dxfattribs['plot'] = properties['plot']
        
        new_layer = doc.layers.new(name=layer_name, dxfattribs=dxfattribs)
        
        # Apply additional properties if provided
        if properties:
            update_layer_properties(new_layer, properties, name_to_aci)
            
        return new_layer
    return doc.layers[layer_name]

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

# def load_standard_linetypes(doc):
#     linetypes = doc.linetypes
    
#     acadiso_lin_file = 'acadiso.lin'  # Adjust this path if necessary
    
#     if not os.path.exists(acadiso_lin_file):
#         log_warning(f"acadiso.lin file not found at: {acadiso_lin_file}")
#         return

#     def parse_pattern(pattern_string):
#         elements = []
#         parts = pattern_string.split(',')
#         for part in parts:
#             part = part.strip()
#             if part.startswith('['):
#                 # Complex element, add as is
#                 elements.append(part)
#             else:
#                 try:
#                     elements.append(float(part))
#                 except ValueError:
#                     # Ignore non-numeric, non-complex elements
#                     pass
#         return elements

#     with open(acadiso_lin_file, 'r') as file:
#         current_linetype = None
#         current_description = ''
#         current_pattern = []

#         for line in file:
#             line = line.strip()
#             if line.startswith('*'):
#                 # New linetype definition
#                 if current_linetype:
#                     add_linetype(linetypes, current_linetype, current_description, current_pattern)
                
#                 # Start a new linetype
#                 parts = line[1:].split(',', 1)
#                 current_linetype = parts[0]
#                 current_description = parts[1] if len(parts) > 1 else ''
#                 current_pattern = []
#             elif line.startswith('A,'):
#                 # Pattern definition
#                 pattern_string = line[2:]
#                 current_pattern = parse_pattern(pattern_string)

#     # Add the last linetype
#     if current_linetype:
#         add_linetype(linetypes, current_linetype, current_description, current_pattern)

#     # Verify that all linetypes are present
#     for name in linetypes:
#         log_info(f"Linetype '{name}' is present in the document.")

#     # Set a default linetype scale
#     doc.header['$LTSCALE'] = 1.0  # Adjust this value as needed

# def add_linetype(linetypes, name, description, pattern):
#     if name not in linetypes:
#         try:
#             linetypes.add(name, pattern, description=description)
#             log_info(f"Added linetype: {name}")
#         except Exception as e:
#             log_warning(f"Failed to add linetype {name}: {str(e)}")
#     else:
#         log_info(f"Linetype {name} already exists")

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
    log_info("\n=== Drawing Properties Set ===")
    print("\n=== Drawing Properties Set ===")
    
    # MEASUREMENT
    measurement_msg = f"$MEASUREMENT: {doc.header['$MEASUREMENT']} - {measurement_meaning.get(doc.header['$MEASUREMENT'], 'Unknown')}"
    log_info(measurement_msg)
    print(measurement_msg)
    
    # INSUNITS
    insunits_msg = f"$INSUNITS: {doc.header['$INSUNITS']} - {insunits_meaning.get(doc.header['$INSUNITS'], 'Unknown')}"
    log_info(insunits_msg)
    print(insunits_msg)
    
    # LUNITS
    lunits_msg = f"$LUNITS: {doc.header['$LUNITS']} - {lunits_meaning.get(doc.header['$LUNITS'], 'Unknown')}"
    log_info(lunits_msg)
    print(lunits_msg)
    
    # LUPREC
    luprec_msg = f"$LUPREC: {doc.header['$LUPREC']} - Linear units precision (number of decimal places)"
    log_info(luprec_msg)
    print(luprec_msg)
    
    # AUPREC
    auprec_msg = f"$AUPREC: {doc.header['$AUPREC']} - Angular units precision (number of decimal places)"
    log_info(auprec_msg)
    print(auprec_msg)
    
    print("\n=== End of Drawing Properties ===")
    log_info("=== End of Drawing Properties ===\n")

def verify_dxf_settings(filename):
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

    print("\n=== Verifying DXF Settings ===")
    log_info("\n=== Verifying DXF Settings ===")

    measurement = loaded_doc.header.get('$MEASUREMENT', None)
    measurement_msg = f"$MEASUREMENT: {measurement} - {measurement_meaning.get(measurement, 'Unknown')}"
    print(measurement_msg)
    log_info(measurement_msg)

    insunits = loaded_doc.header.get('$INSUNITS', None)
    insunits_msg = f"$INSUNITS: {insunits} - {insunits_meaning.get(insunits, 'Unknown')}"
    print(insunits_msg)
    log_info(insunits_msg)

    lunits = loaded_doc.header.get('$LUNITS', None)
    lunits_msg = f"$LUNITS: {lunits} - {lunits_meaning.get(lunits, 'Unknown')}"
    print(lunits_msg)
    log_info(lunits_msg)

    luprec = loaded_doc.header.get('$LUPREC', None)
    luprec_msg = f"$LUPREC: {luprec} - Linear units precision (decimal places)"
    print(luprec_msg)
    log_info(luprec_msg)

    auprec = loaded_doc.header.get('$AUPREC', None)
    auprec_msg = f"$AUPREC: {auprec} - Angular units precision (decimal places)"
    print(auprec_msg)
    log_info(auprec_msg)

    print("=== End of DXF Settings Verification ===\n")
    log_info("=== End of DXF Settings Verification ===\n")

def get_style(style, project_loader):
    if isinstance(style, str):
        return project_loader.get_style(style)
    return style

def linetype_exists(doc, linetype):
    return linetype in doc.linetypes

def apply_style_to_entity(entity, style, project_loader, loaded_styles, item_type='area'):
    if entity.dxftype() == 'MTEXT':
        if 'height' in style:
            entity.dxf.char_height = style['height']
        if 'font' in style:
            entity.dxf.style = style['font']
    
    if 'color' in style:
        color = get_color_code(style['color'], project_loader.name_to_aci)
        if isinstance(color, tuple):
            entity.rgb = color  # Set RGB color directly
        else:
            entity.dxf.color = color  # Set ACI color
    else:
        entity.dxf.color = ezdxf.const.BYLAYER
    
    if 'linetype' in style:
        linetype = style['linetype']
        if linetype_exists(entity.doc, linetype):
            entity.dxf.linetype = linetype
        else:
            log_warning(f"Linetype '{linetype}' is not defined in the current DXF object. Using 'BYLAYER' instead.")
            entity.dxf.linetype = 'BYLAYER'
    
    if 'lineweight' in style:
        entity.dxf.lineweight = style['lineweight']
    
    # Set transparency for all entity types
    if 'transparency' in style:
        transparency = convert_transparency(style['transparency'])
        if transparency is not None:
            try:
                entity.transparency = transparency
            except Exception as e:
                print(f"Warning: Could not set transparency for {entity.dxftype()}. Error: {str(e)}")
    else:
        # To set transparency to ByLayer, we'll try to remove the attribute if it exists
        try:
            del entity.transparency
        except AttributeError:
            # If the entity doesn't have a transparency attribute, we don't need to do anything
            pass

    # Apply linetype scale if specified
    if 'linetypeScale' in style:
        entity.dxf.ltscale = float(style['linetypeScale'])
    else:
        entity.dxf.ltscale = 1.0  # Default scale

    if 'text_style' in style:
        text_style = style['text_style']
        if text_style not in loaded_styles:
            log_warning(f"Text style '{text_style}' was not loaded during initialization. Using 'Standard' instead.")
            entity.dxf.style = 'Standard'
        elif text_style not in entity.doc.styles:
            log_warning(f"Text style '{text_style}' is not defined in the current DXF object. Using 'Standard' instead.")
            entity.dxf.style = 'Standard'
        else:
            entity.dxf.style = text_style

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

def add_mtext(msp, text, x, y, layer_name, style_name, text_style=None, name_to_aci=None, max_width=None):
    log_info(f"Adding MTEXT: text='{text}', x={x}, y={y}, layer='{layer_name}', style='{style_name}', max_width={max_width}")
    
    # Create MText editor for advanced paragraph formatting
    editor = MTextEditor()
    
    # Get paragraph alignment from style
    alignment_map = {
        'LEFT': MTextParagraphAlignment.LEFT,
        'RIGHT': MTextParagraphAlignment.RIGHT,
        'CENTER': MTextParagraphAlignment.CENTER,
        'JUSTIFIED': MTextParagraphAlignment.JUSTIFIED,
        'DISTRIBUTED': MTextParagraphAlignment.DISTRIBUTED
    }
    
    # Get paragraph properties from text_style
    if text_style and 'paragraph' in text_style:
        para_props = text_style['paragraph']
        props = ParagraphProperties(
            indent=para_props.get('indent', 0),
            left=para_props.get('left', 0),
            right=para_props.get('right', 0),
            align=alignment_map.get(para_props.get('align', 'LEFT').upper(), MTextParagraphAlignment.LEFT),
            tab_stops=para_props.get('tab_stops', tuple())
        )
        editor.paragraph(props)
    
    # Add the text content
    for paragraph in text.split('\n'):
        editor.append(paragraph)
        editor.append('\\P')  # Add paragraph break
    
    dxfattribs = {
        'style': style_name,
        'layer': layer_name,
        'char_height': text_style.get('height', 2.5),
        'insert': Vec3(x, y, 0),
        'attachment_point': MTEXT_MIDDLE_LEFT,
        'width': max_width if max_width is not None else 0,
    }
    
    # Apply other text style properties
    if text_style:
        if 'color' in text_style:
            dxfattribs['color'] = get_color_code(text_style['color'], name_to_aci)
        if 'rotation' in text_style:
            dxfattribs['rotation'] = text_style['rotation']
        if 'attachment_point' in text_style:
            dxfattribs['attachment_point'] = get_mtext_constant(text_style['attachment_point'])
        if 'flow_direction' in text_style:
            dxfattribs['flow_direction'] = get_mtext_constant(text_style['flow_direction'])
        if 'line_spacing_style' in text_style:
            dxfattribs['line_spacing_style'] = get_mtext_constant(text_style['line_spacing_style'])
        if 'line_spacing_factor' in text_style:
            dxfattribs['line_spacing_factor'] = text_style['line_spacing_factor']
        if 'bg_fill' in text_style:
            dxfattribs['bg_fill'] = text_style['bg_fill']
        if 'bg_fill_color' in text_style:
            dxfattribs['bg_fill_color'] = get_color_code(text_style['bg_fill_color'], name_to_aci)
        if 'bg_fill_scale' in text_style:
            dxfattribs['box_fill_scale'] = text_style['bg_fill_scale']
    
    try:
        mtext = msp.add_mtext(str(editor), dxfattribs=dxfattribs)
        attach_custom_data(mtext, SCRIPT_IDENTIFIER)
        
        # Apply additional formatting if specified
        if text_style:
            if 'underline' in text_style and text_style['underline']:
                mtext.text = f"\\L{mtext.text}\\l"
            if 'overline' in text_style and text_style['overline']:
                mtext.text = f"\\O{mtext.text}\\o"
            if 'strike_through' in text_style and text_style['strike_through']:
                mtext.text = f"\\K{mtext.text}\\k"
            if 'oblique_angle' in text_style:
                mtext.text = f"\\Q{text_style['oblique_angle']};{mtext.text}"
        
        log_info("MTEXT added successfully")
        
        # Calculate and return the actual height of the MTEXT entity
        actual_height = mtext.dxf.char_height * mtext.dxf.line_spacing_factor * len(text.split('\n'))
        return mtext, actual_height
    except Exception as e:
        log_error(f"Failed to add MTEXT: {str(e)}")
        return None, 0

def get_mtext_constant(value):
    mtext_constants = {
        'MTEXT_TOP_LEFT': MTEXT_TOP_LEFT,
        'MTEXT_TOP_CENTER': MTEXT_TOP_CENTER,
        'MTEXT_TOP_RIGHT': MTEXT_TOP_RIGHT,
        'MTEXT_MIDDLE_LEFT': MTEXT_MIDDLE_LEFT,
        'MTEXT_MIDDLE_CENTER': MTEXT_MIDDLE_CENTER,
        'MTEXT_MIDDLE_RIGHT': MTEXT_MIDDLE_RIGHT,
        'MTEXT_BOTTOM_LEFT': MTEXT_BOTTOM_LEFT,
        'MTEXT_BOTTOM_CENTER': MTEXT_BOTTOM_CENTER,
        'MTEXT_BOTTOM_RIGHT': MTEXT_BOTTOM_RIGHT,
        'MTEXT_LEFT_TO_RIGHT': MTEXT_LEFT_TO_RIGHT,
        'MTEXT_TOP_TO_BOTTOM': MTEXT_TOP_TO_BOTTOM,
        'MTEXT_BY_STYLE': MTEXT_BY_STYLE,
        'MTEXT_AT_LEAST': MTEXT_AT_LEAST,
        'MTEXT_EXACT': MTEXT_EXACT
    }
    return mtext_constants.get(value, value)

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
                log_info(f"Added standard text style: {style_name}")
            except ezdxf.lldxf.const.DXFTableEntryError:
                log_warning(f"Failed to add standard text style: {style_name}")
        else:
            loaded_styles.add(style_name)

    return loaded_styles

# This function should be called once when the document is loaded
def initialize_document(doc):
    # load_standard_linetypes(doc)
    loaded_styles = load_standard_text_styles(doc)
    return loaded_styles

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

def add_text_insert(msp, text_config, layer_name, project_loader, script_identifier):
    """Add text at a specific position with given properties."""
    try:
        # Check update flag
        if not text_config.get('updateDxf', False):
            log_info(f"Skipping text insert for layer '{layer_name}' as updateDxf flag is not set")
            return None

        # Sanitize layer name
        layer_name = sanitize_layer_name(layer_name)
        
        # Get the correct space (model or paper)
        doc = msp.doc
        space = doc.paperspace() if text_config.get('paperspace', False) else doc.modelspace()
        
        # Ensure layer exists
        ensure_layer_exists(doc, layer_name, {}, project_loader.name_to_aci)

        # Extract text properties from config
        text = text_config.get('text', '')
        position = text_config.get('position', {'x': 0, 'y': 0})
        style_name = text_config.get('style')
        
        # Handle style presets
        style = {}
        if style_name:
            style = project_loader.get_style(style_name)
            if style is None:
                log_warning(f"Style preset '{style_name}' not found. Using default style.")
                style = {}
            # If style contains a text section, use that
            if isinstance(style, dict) and 'text' in style:
                style = style['text']
        
        # Get position coordinates
        x = position.get('x', 0)
        y = position.get('y', 0)
        
        # Extract text style properties
        height = style.get('height', 2.5)
        rotation = style.get('rotation', 0)
        font = style.get('font', 'Standard')
        max_width = style.get('width', None)
        
        # Convert attachment point
        attachment_dict = {
            'TOP_LEFT': MTEXT_TOP_LEFT,
            'TOP_CENTER': MTEXT_TOP_CENTER,
            'TOP_RIGHT': MTEXT_TOP_RIGHT,
            'MIDDLE_LEFT': MTEXT_MIDDLE_LEFT,
            'MIDDLE_CENTER': MTEXT_MIDDLE_CENTER,
            'MIDDLE_RIGHT': MTEXT_MIDDLE_RIGHT,
            'BOTTOM_LEFT': MTEXT_BOTTOM_LEFT,
            'BOTTOM_CENTER': MTEXT_BOTTOM_CENTER,
            'BOTTOM_RIGHT': MTEXT_BOTTOM_RIGHT
        }
        
        attachment = attachment_dict.get(
            style.get('attachment_point', 'TOP_LEFT').upper(),
            MTEXT_TOP_LEFT
        )
        
        # Convert color using get_color_code
        color = get_color_code(style.get('color'), project_loader.name_to_aci)
        
        log_info(f"Adding MTEXT '{text}' to layer '{layer_name}' at ({x}, {y})")
        
        # Use add_mtext with correct attachment point
        result = add_mtext(
            space,
            text,
            x,
            y,
            layer_name,
            font,
            text_style={
                **style,
                'attachment_point': attachment
            },
            name_to_aci=project_loader.name_to_aci,
            max_width=max_width
        )
        
        if result is None or result[0] is None:
            log_error(f"Failed to create MTEXT entity for text '{text}'")
            return None
            
        text_entity = result[0]
        
        # Attach custom data
        attach_custom_data(text_entity, script_identifier)
        
        log_info(f"Successfully added MTEXT '{text}' at position ({x}, {y})")
        return text_entity
        
    except Exception as e:
        log_error(f"Failed to add text insert: {str(e)}")
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
                log_info(f"Removed unused block: {block_name}")
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
                    log_info(f"Removed empty layer: {layer_name}")
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
        
        log_info("Document cleanup completed successfully")
        
    except Exception as e:
        log_error(f"Error during document cleanup: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")























































































