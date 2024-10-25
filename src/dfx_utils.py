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
from ezdxf.math import Vec2
import os
from ezdxf.lldxf.const import DXFValueError

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

def create_path_array(msp, source_layer_name, target_layer_name, block_name, spacing, scale=1.0, rotation=0.0, margin=0.1):
    if block_name not in msp.doc.blocks:
        log_warning(f"Block '{block_name}' not found in the document")
        return

    polylines = msp.query(f'LWPOLYLINE[layer=="{source_layer_name}"]')
    
    for polyline in polylines:
        points = polyline.get_points()
        total_length = 0
        segments = []

        for i in range(len(points) - 1):
            start = Vec2(points[i][:2])
            end = Vec2(points[i+1][:2])
            segment_length = (end - start).magnitude
            if segment_length == 0:
                log_warning(f"Zero-length segment found between points {start} and {end}. Skipping this segment.")
                continue
            segments.append((start, end, segment_length))
            total_length += segment_length

        current_distance = 0
        for start, end, segment_length in segments:
            segment_direction = (end - start).normalize()
            
            while current_distance < segment_length:
                insertion_point = start + segment_direction * current_distance
                angle = math.atan2(segment_direction.y, segment_direction.x)
                
                # Check if the insertion point is inside the polyline or within the margin
                if is_point_inside_or_near_polyline(insertion_point, points, margin):
                    block_ref = add_block_reference(
                        msp,
                        block_name,
                        insertion_point,
                        target_layer_name,
                        scale=scale,
                        rotation=rotation + math.degrees(angle)
                    )
                    
                    if block_ref:
                        attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
                
                current_distance += spacing
            
            current_distance -= segment_length

    log_info(f"Path array created for source layer '{source_layer_name}' using block '{block_name}' and placed on target layer '{target_layer_name}'")

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

def is_point_inside_polyline(point, polyline_points):
    x, y = point.x, point.y
    inside = False
    n = len(polyline_points)
    
    for i in range(n):
        j = (i + 1) % n
        xi, yi = polyline_points[i][:2]
        xj, yj = polyline_points[j][:2]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
    
    return inside






























