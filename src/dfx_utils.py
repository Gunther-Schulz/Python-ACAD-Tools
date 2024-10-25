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

# Set up file handler
file_handler = logging.FileHandler('path_array_debug.log', mode='w')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Set up console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_formatter = logging.Formatter('%(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Configure root logger
logging.root.setLevel(logging.DEBUG)
logging.root.addHandler(file_handler)
logging.root.addHandler(console_handler)

# Get logger for this module
logger = logging.getLogger(__name__)

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
            return name_to_aci.get(color.lower(), 7)
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

def attach_custom_data(entity, script_identifier):
    if entity is None:
        log_warning("Attempted to attach custom data to a None entity")
        return

    xdata_set = False
    hyperlink_set = False

    # Set XDATA
    try:
        existing_xdata = entity.get_xdata('DXFEXPORTER')
        if existing_xdata:
            for code, value in existing_xdata:
                if code == 1000 and value == script_identifier:
                    xdata_set = True
                    break
        
        if not xdata_set:
            entity.set_xdata(
                'DXFEXPORTER',
                [
                    (1000, script_identifier),
                    (1002, '{'),
                    (1000, 'CREATED_BY'),
                    (1000, 'DXFExporter'),
                    (1002, '}')
                ]
            )
            xdata_set = True
    except ezdxf.lldxf.const.DXFValueError:
        # This exception is raised when the XDATA application ID doesn't exist
        # We can safely add the XDATA in this case
        entity.set_xdata(
            'DXFEXPORTER',
            [
                (1000, script_identifier),
                (1002, '{'),
                (1000, 'CREATED_BY'),
                (1000, 'DXFExporter'),
                (1002, '}')
            ]
        )
        xdata_set = True
    except Exception as e:
        log_error(f"Error setting XDATA for entity {entity.dxftype()}: {str(e)}")

    # Set hyperlink
    if hasattr(entity, 'set_hyperlink'):
        try:
            existing_hyperlink = entity.get_hyperlink()
            if isinstance(existing_hyperlink, tuple) and len(existing_hyperlink) > 0:
                existing_url = existing_hyperlink[0]
            else:
                existing_url = ''

            if script_identifier in existing_url:
                hyperlink_set = True
            else:
                hyperlink_text = f"{script_identifier} - Created by DXFExporter"
                entity.set_hyperlink(hyperlink_text, description="Entity created by DXFExporter")
                hyperlink_set = True
        except Exception as e:
            log_error(f"Error setting hyperlink for entity {entity.dxftype()}: {str(e)}")
    else:
        log_warning(f"Entity {entity.dxftype()} does not support hyperlinks")

    if xdata_set and not hyperlink_set:
        log_warning(f"Entity {entity.dxftype()} received XDATA but not a hyperlink")

    return xdata_set, hyperlink_set

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

def remove_entities_by_layer(msp, layer_name, script_identifier):
    entities_to_delete = [entity for entity in msp.query(f'*[layer=="{layer_name}"]') if is_created_by_script(entity, script_identifier)]
    delete_count = 0
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
            delete_count += 1
        except Exception as e:
            log_error(f"Error deleting entity: {e}")
    return delete_count

def update_layer_geometry(msp, layer_name, script_identifier, update_function):
    # Remove existing entities
    remove_entities_by_layer(msp, layer_name, script_identifier)
    
    # Add new geometry
    update_function()

def ensure_layer_exists(doc, layer_name, layer_properties, name_to_aci):
    if layer_name not in doc.layers:
        new_layer = doc.layers.new(layer_name)
        update_layer_properties(new_layer, layer_properties, name_to_aci)
    else:
        existing_layer = doc.layers.get(layer_name)
        update_layer_properties(existing_layer, layer_properties, name_to_aci)

def update_layer_properties(layer, layer_properties, name_to_aci):
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
    doc.header['$INSUNITS'] = 6  # Assuming meters, adjust if needed
    doc.header['$LUNITS'] = 2  # Assuming decimal units
    doc.header['$LUPREC'] = 4  # Precision for linear units
    doc.header['$AUPREC'] = 4  # Precision for angular units

def verify_dxf_settings(filename):
    loaded_doc = ezdxf.readfile(filename)
    log_info(f"INSUNITS after load: {loaded_doc.header['$INSUNITS']}")
    log_info(f"LUNITS after load: {loaded_doc.header['$LUNITS']}")
    log_info(f"LUPREC after load: {loaded_doc.header['$LUPREC']}")
    log_info(f"AUPREC after load: {loaded_doc.header['$AUPREC']}")

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

    # Apply specific styles based on item type
    if item_type == 'line':
        if 'linetype_scale' in style:
            entity.dxf.ltscale = style['linetype_scale']
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

def create_hatch(msp, boundary_paths, hatch_config, project_loader, is_legend=False):
    if is_legend:
        log_info(f"Creating symbol hatch with config: {hatch_config}")
    else:
        log_info(f"Creating hatch with config: {hatch_config}")
    
    hatch = msp.add_hatch()
    
    pattern = hatch_config.get('pattern', 'SOLID')
    scale = hatch_config.get('scale', 1)
    
    if pattern != 'SOLID':
        try:
            hatch.set_pattern_fill(pattern, scale=scale)
        except ezdxf.DXFValueError:
            log_warning(f"Invalid hatch pattern: {pattern}. Using SOLID instead.")
            hatch.set_pattern_fill("SOLID")
    else:
        hatch.set_solid_fill()

    for path in boundary_paths:
        hatch.paths.add_polyline_path(path)
    
    # Apply color for both legend and non-legend hatches
    if 'color' in hatch_config and hatch_config['color'] not in (None, 'BYLAYER'):
        color = get_color_code(hatch_config['color'], project_loader.name_to_aci)
        if isinstance(color, tuple):
            hatch.rgb = color  # Set RGB color directly
        else:
            hatch.dxf.color = color  # Set ACI color
    else:
        hatch.dxf.color = ezdxf.const.BYLAYER

    # Check if 'transparency' key exists and set it only if specified
    if 'transparency' in hatch_config:
        transparency = hatch_config['transparency']
        if transparency not in (None, 'BYLAYER'):
            transparency_value = convert_transparency(transparency)
            if transparency_value is not None:
                set_hatch_transparency(hatch, transparency_value)
    
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
    
    sanitized_text = text.replace('\n', '\\P')
    
    dxfattribs = {
        'style': style_name,
        'layer': layer_name,
        'char_height': text_style.get('height', 2.5),
        'insert': Vec3(x, y, 0),
        'attachment_point': MTEXT_MIDDLE_LEFT,
        'width': max_width if max_width is not None else 0,
    }
    
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
        mtext = msp.add_mtext(sanitized_text, dxfattribs=dxfattribs)
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
    # Define a set of allowed characters, including German-specific ones and space
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

def calculate_overlap_ratio(block_shape, polyline_geom):
    logger.debug(f"Block shape: {block_shape}")
    logger.debug(f"Polyline: {polyline_geom}")

    # Create a buffer around the polyline
    buffer_distance = 0.1
    polyline_buffer = polyline_geom.buffer(buffer_distance)
    logger.debug(f"Polyline buffer: {polyline_buffer}")

    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polyline_buffer).area
    outside_area = block_shape.difference(polyline_buffer).area

    logger.debug(f"Block area: {block_area}")
    logger.debug(f"Intersection area: {intersection_area}")
    logger.debug(f"Outside area: {outside_area}")

    if block_area == 0:
        logger.warning("Block area is zero!")
        return 100.0

    outside_percentage = (outside_area / block_area) * 100
    logger.debug(f"Calculated outside percentage: {outside_percentage}")

    return round(outside_percentage, 1)

def create_path_array(msp, source_layer_name, target_layer_name, block_name, spacing, scale=1.0, rotation=0.0, max_outside_percentage=0.0):
    if block_name not in msp.doc.blocks:
        log_warning(f"Block '{block_name}' not found in the document")
        return

    block = msp.doc.blocks[block_name]
    block_shape, block_base_point = get_block_shape_and_base(block, scale)
    
    if block_shape is None:
        log_warning(f"Could not determine shape for block '{block_name}'")
        return

    polylines = msp.query(f'LWPOLYLINE[layer=="{source_layer_name}"]')
    
    fig, ax = plt.subplots(figsize=(12, 8))

    for polyline in polylines:
        points = [Vec2(p[0], p[1]) for p in polyline.get_points()]
        polyline_geom = LineString([(p.x, p.y) for p in points])
        total_length = polyline_geom.length
        
        # Plot base geometry
        x, y = polyline_geom.xy
        ax.plot(x, y, color='gray', linewidth=2, alpha=0.5)
        
        log_info(f"Polyline length: {total_length}, Number of points: {len(points)}")
        
        # Convert source polyline to a polygon with a smaller buffer
        buffer_distance = min(block_shape.bounds[2] - block_shape.bounds[0], 
                              block_shape.bounds[3] - block_shape.bounds[1]) / 4
        polygon_geom = polyline_geom.buffer(buffer_distance)
        
        # Plot the polygon area
        x, y = polygon_geom.exterior.xy
        ax.fill(x, y, alpha=0.2, fc='gray', ec='none')
        
        block_distance = spacing / 2

        while block_distance < total_length:
            point = polyline_geom.interpolate(block_distance)
            insertion_point = Vec2(point.x, point.y)
            angle = get_angle_at_point(polyline_geom, block_distance / total_length)

            log_info(f"Trying to place block at {insertion_point}, angle: {math.degrees(angle)}")

            rotated_block_shape = rotate_and_adjust_block(block_shape, block_base_point, insertion_point, angle)
            
            outside_percentage = calculate_outside_percentage(rotated_block_shape, polygon_geom)

            # Create a color based on the outside percentage
            color = plt.cm.RdYlGn(1 - (outside_percentage / 100))  # Red (high outside %) to Green (low outside %)

            if outside_percentage <= max_outside_percentage:
                block_ref = add_block_reference(
                    msp,
                    block_name,
                    insertion_point,
                    target_layer_name,
                    scale=scale,
                    rotation=math.degrees(angle) + rotation
                )
                
                if block_ref:
                    attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
                    log_info(f"Block placed at {insertion_point}")
            else:
                log_info(f"Block not placed at {insertion_point} due to excessive outside area")
            
            # Plot block with color based on outside percentage
            plot_polygon(ax, rotated_block_shape, color, 0.7)
            
            # Add label with outside percentage
            ax.text(insertion_point.x, insertion_point.y, f"{outside_percentage:.1f}%", 
                    ha='center', va='center', fontsize=8, 
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))
            
            block_distance += spacing

    log_info(f"Path array creation completed for source layer '{source_layer_name}' using block '{block_name}'")
    
    # Add a colorbar to show the outside percentage scale
    sm = plt.cm.ScalarMappable(cmap=plt.cm.RdYlGn_r, norm=plt.Normalize(vmin=0, vmax=100))
    sm.set_array([])
    plt.colorbar(sm, label='Outside Percentage', ax=ax)
    
    ax.set_aspect('equal', 'datalim')
    plt.title(f"Block Placement for {source_layer_name}")
    plt.show()

def calculate_outside_percentage(block_shape, polygon_geom):
    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polygon_geom).area
    
    if block_area == 0:
        logger.warning("Block area is zero!")
        return 100.0  # Assume fully outside if block has no area
    
    outside_area = block_area - intersection_area
    outside_percentage = (outside_area / block_area) * 100
    
    logger.debug(f"Block area: {block_area}, Intersection area: {intersection_area}")
    logger.debug(f"Outside area: {outside_area}, Outside percentage: {outside_percentage}")
    
    return round(outside_percentage, 1)

def get_block_shape_and_base(block, scale):
    shapes = []
    base_point = Vec2(block.base_point[0] * scale, block.base_point[1] * scale)
    
    for entity in block:
        if entity.dxftype() == "LWPOLYLINE":
            points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
            shapes.append(Polygon(points))
        elif entity.dxftype() == "LINE":
            start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
            end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
            shapes.append(LineString([start, end]))
    
    if not shapes:
        logger.warning(f"No shapes found in block {block.name}")
        return None, None
    
    combined_shape = unary_union(shapes)
    logger.debug(f"Combined block shape: {combined_shape}")
    return combined_shape, base_point

def rotate_and_adjust_block(block_shape, base_point, insertion_point, angle):
    # Translate the block shape so that its base point is at the origin
    translated_shape = affinity.translate(block_shape, 
                                          xoff=-base_point.x, 
                                          yoff=-base_point.y)
    
    # Rotate the translated shape around the origin
    rotated_shape = affinity.rotate(translated_shape, 
                                    angle=math.degrees(angle), 
                                    origin=(0, 0))
    
    # Translate the rotated shape to the insertion point
    final_shape = affinity.translate(rotated_shape, 
                                     xoff=insertion_point.x, 
                                     yoff=insertion_point.y)
    
    return final_shape

def plot_polygon(ax, polygon, color, alpha):
    if polygon.geom_type == 'Polygon':
        x, y = polygon.exterior.xy
        ax.fill(x, y, alpha=alpha, fc=color, ec='black')
    elif polygon.geom_type == 'MultiPolygon':
        for geom in polygon.geoms:
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=alpha, fc=color, ec='black')

def get_angle_at_point(linestring, param):
    # Get the angle of the tangent at the given parameter
    point = linestring.interpolate(param, normalized=True)
    if param == 0:
        next_point = linestring.interpolate(0.01, normalized=True)
        return math.atan2(next_point.y - point.y, next_point.x - point.x)
    elif param == 1:
        prev_point = linestring.interpolate(0.99, normalized=True)
        return math.atan2(point.y - prev_point.y, point.x - prev_point.x)
    else:
        prev_point = linestring.interpolate(param - 0.01, normalized=True)
        next_point = linestring.interpolate(param + 0.01, normalized=True)
        return math.atan2(next_point.y - prev_point.y, next_point.x - prev_point.x)

def rotate_shape(shape, center, angle):
    # First, rotate the shape around its center
    rotated = affinity.rotate(shape, math.degrees(angle), origin='center')
    
    # Then, translate the rotated shape to the desired center
    translated = affinity.translate(rotated, xoff=center.x, yoff=center.y)
    
    return translated

def get_block_shape(block, scale):
    shapes = []
    for entity in block:
        if entity.dxftype() == "LWPOLYLINE":
            points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
            shapes.append(Polygon(points))
        elif entity.dxftype() == "LINE":
            start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
            end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
            shapes.append(LineString([start, end]))
    
    if not shapes:
        log_warning(f"No suitable entities found in block '{block.name}'")
        return None
    
    # Combine all shapes into a single shape
    combined_shape = unary_union(shapes)
    
    # If the result is a MultiLineString, convert it to a Polygon
    if isinstance(combined_shape, MultiLineString):
        combined_shape = combined_shape.buffer(0.01)  # Small buffer to create a polygon
    
    # Check if we can determine a bounding box
    if combined_shape.is_empty:
        log_warning(f"Could not determine bounding box for block '{block.name}'")
        return None
    
    # Log the bounding box size
    minx, miny, maxx, maxy = combined_shape.bounds
    width = maxx - minx
    height = maxy - miny
    print(f"Block '{block.name}' bounding box size: width={width}, height={height}")
    log_info(f"Block '{block.name}' bounding box size: width={width}, height={height}")
    
    return combined_shape

def is_shape_sufficiently_inside(shape, polyline_polygon, overlap_margin):
    if shape is None:
        log_warning("Block shape is None")
        return False

    intersection_area = shape.intersection(polyline_polygon).area
    shape_area = shape.area
    
    if shape_area == 0:
        log_warning("Shape area is zero")
        return False
    
    overlap_ratio = intersection_area / shape_area
    required_overlap = 1 - overlap_margin
    log_info(f"Overlap ratio: {overlap_ratio}, Required: {required_overlap}")
    
    return overlap_ratio >= required_overlap

def is_point_inside_polyline(point, polyline_points):
    n = len(polyline_points)
    inside = False
    p1x, p1y = polyline_points[0]
    for i in range(n + 1):
        p2x, p2y = polyline_points[i % n]
        if point.y > min(p1y, p2y):
            if point.y <= max(p1y, p2y):
                if point.x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (point.y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or point.x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def does_line_intersect_polyline(start, end, polyline_points):
    for i in range(len(polyline_points)):
        p1 = polyline_points[i]
        p2 = polyline_points[(i + 1) % len(polyline_points)]
        if do_lines_intersect(start, end, p1, p2):
            return True
    return False

def do_lines_intersect(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x)
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

def clip_polygon(subject_polygon, clip_polygon):
    from ezdxf.math import intersection_line_line_2d
    
    def inside(p, cp1, cp2):
        return (cp2.x - cp1.x) * (p.y - cp1.y) > (cp2.y - cp1.y) * (p.x - cp1.x)
    
    output_list = subject_polygon
    cp1 = clip_polygon[-1]
    
    for clip_vertex in clip_polygon:
        cp2 = clip_vertex
        input_list = output_list
        output_list = []
        if not input_list:
            break
        s = input_list[-1]
        for subject_vertex in input_list:
            e = subject_vertex
            if inside(e, cp1, cp2):
                if not inside(s, cp1, cp2):
                    intersection = intersection_line_line_2d((cp1, cp2), (s, e))
                    if intersection:
                        output_list.append(intersection)
                output_list.append(e)
            elif inside(s, cp1, cp2):
                intersection = intersection_line_line_2d((cp1, cp2), (s, e))
                if intersection:
                    output_list.append(intersection)
            s = e
        cp1 = cp2
    
    return output_list

def calculate_polygon_area(points):
    if len(points) < 3:
        return 0.0
    n = len(points)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i].x * points[j].y
        area -= points[j].x * points[i].y
    area = abs(area) / 2.0
    return area

def get_block_dimensions(block):
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
    
    for entity in block.entity_space:
        if entity.dxftype() == "LWPOLYLINE":
            for point in entity.get_points():
                x, y = point[:2]
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    
    if min_x == float('inf') or min_y == float('inf') or max_x == float('-inf') or max_y == float('-inf'):
        log_warning(f"No LWPOLYLINE entities found in block '{block.name}'. Using default dimensions.")
        return 1, 1  # Default dimensions if no LWPOLYLINE is found
    
    width = max_x - min_x
    height = max_y - min_y
    return width, height

def get_block_corners(center, width, height, angle):
    half_width = width / 2
    half_height = height / 2
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    
    corners = [
        Vec2(center.x + (half_width * cos_angle - half_height * sin_angle),
             center.y + (half_width * sin_angle + half_height * cos_angle)),
        Vec2(center.x + (half_width * cos_angle + half_height * sin_angle),
             center.y + (half_width * sin_angle - half_height * cos_angle)),
        Vec2(center.x + (-half_width * cos_angle + half_height * sin_angle),
             center.y + (-half_width * sin_angle - half_height * cos_angle)),
        Vec2(center.x + (-half_width * cos_angle - half_height * sin_angle),
             center.y + (-half_width * sin_angle + half_height * cos_angle))
    ]
    return corners

def is_point_inside_or_near_polyline(point, polyline_points, margin):
    if is_point_inside_polyline(point, polyline_points):
        return True
    
    # Check if the point is within the margin of any polyline edge
    for i in range(len(polyline_points)):
        start = Vec2(polyline_points[i][:2])
        end = Vec2(polyline_points[(i + 1) % len(polyline_points)][:2])
        
        # Calculate the distance from the point to the line segment
        line_vec = end - start
        if line_vec.magnitude == 0:
            continue  # Skip zero-length segments
        point_vec = point - start
        try:
            projection = point_vec.project(line_vec)
            if 0 <= projection.magnitude <= line_vec.magnitude:
                distance = (point_vec - projection).magnitude
                if distance <= margin:
                    return True
        except ZeroDivisionError:
            log_warning(f"Zero-length vector encountered in is_point_inside_or_near_polyline. Skipping this segment.")
            continue
    
    return False

def calculate_overlap_ratio(block_shape, polyline_geom):
    # Create a buffer around the polyline to give it some width
    buffer_distance = max(block_shape.bounds[2] - block_shape.bounds[0], 
                          block_shape.bounds[3] - block_shape.bounds[1]) / 2
    polyline_buffer = polyline_geom.buffer(buffer_distance)
    
    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polyline_buffer).area
    
    if block_area == 0:
        logger.warning("Block area is zero!")
        return 100.0  # Assume full overlap if block has no area
    
    overlap_ratio = intersection_area / block_area
    inside_percentage = overlap_ratio * 100
    
    logger.debug(f"Block area: {block_area}, Intersection area: {intersection_area}")
    logger.debug(f"Overlap ratio: {overlap_ratio}, Inside percentage: {inside_percentage}")
    
    return round(inside_percentage, 1)


































































