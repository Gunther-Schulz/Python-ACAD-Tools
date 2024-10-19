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

script_identifier = "Created by DXFExporter"

def get_color_code(color, name_to_aci):
    if color is None:
        return 7  # Default to 7 (white) if no color is specified
    if isinstance(color, int):
        return min(max(color, 0), 255)  # Ensure color is between 0 and 255
    elif isinstance(color, str):
        return name_to_aci.get(color.lower(), 7)  # Default to 7 (white) if not found
    else:
        return 7  # Default to 7 (white) for any other type

def convert_transparency(transparency):
    if isinstance(transparency, (int, float)):
        return min(max(transparency, 0), 1)  # Ensure value is between 0 and 1
    elif isinstance(transparency, str):
        try:
            return float(transparency)
        except ValueError:
            print(f"Invalid transparency value: {transparency}")
    return None

def attach_custom_data(entity, script_identifier):
    if entity is None:
        log_warning("Attempted to attach custom data to a None entity")
        return

    xdata_set = False
    hyperlink_set = False

    try:
        # Set XDATA
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
        log_info(f"XDATA set for entity {entity.dxftype()}")
    except Exception as e:
        log_error(f"Error setting XDATA for entity {entity.dxftype()}: {str(e)}")

    # Set hyperlink
    if hasattr(entity, 'set_hyperlink'):
        try:
            hyperlink_text = f"{script_identifier} - Created by DXFExporter"
            entity.set_hyperlink(hyperlink_text, description="Entity created by DXFExporter")
            hyperlink_set = True
            log_info(f"Hyperlink set for entity {entity.dxftype()}")
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
        print(f"Unexpected error checking XDATA for entity {entity}: {str(e)}")
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
            print(f"Error deleting entity: {e}")
    return delete_count

def update_layer_geometry(msp, layer_name, script_identifier, update_function):
    # Remove existing entities
    remove_entities_by_layer(msp, layer_name, script_identifier)
    
    # Add new geometry
    update_function()

def ensure_layer_exists(doc, layer_name, layer_properties):
    if layer_name not in doc.layers:
        new_layer = doc.layers.new(layer_name)
        update_layer_properties(new_layer, layer_properties)
    else:
        existing_layer = doc.layers.get(layer_name)
        update_layer_properties(existing_layer, layer_properties)

def update_layer_properties(layer, layer_properties):
    if 'color' in layer_properties:
        layer.color = layer_properties['color']
    if 'linetype' in layer_properties:
        layer.linetype = layer_properties['linetype']
    if 'lineweight' in layer_properties:
        layer.lineweight = layer_properties['lineweight']
    if 'transparency' in layer_properties:
        # Convert the 0-1 transparency value to what ezdxf expects for layers
        transparency = layer_properties['transparency']
        if isinstance(transparency, (int, float)):
            # Ensure the value is between 0 and 1
            layer.transparency = min(max(transparency, 0), 1)
        elif isinstance(transparency, str):
            try:
                transparency_value = float(transparency)
                layer.transparency = min(max(transparency_value, 0), 1)
            except ValueError:
                print(f"Invalid transparency value for layer: {transparency}")
    if 'plot' in layer_properties:
        layer.plot = layer_properties['plot']

def load_standard_linetypes(doc):
    standard_linetypes = [
        'CONTINUOUS', 'CENTER', 'DASHED', 'PHANTOM', 'HIDDEN', 'DASHDOT',
        'BORDER', 'DIVIDE', 'DOT', 'ACAD_ISO02W100', 'ACAD_ISO03W100',
        'ACAD_ISO04W100', 'ACAD_ISO05W100', 'ACAD_ISO06W100', 'ACAD_ISO07W100',
        'ACAD_ISO08W100', 'ACAD_ISO09W100', 'ACAD_ISO10W100', 'ACAD_ISO11W100',
        'ACAD_ISO12W100', 'ACAD_ISO13W100', 'ACAD_ISO14W100', 'ACAD_ISO15W100'
    ]
    for lt in standard_linetypes:
        if lt not in doc.linetypes:
            doc.linetypes.new(lt)

def set_drawing_properties(doc):
    doc.header['$INSUNITS'] = 6  # Assuming meters, adjust if needed
    doc.header['$LUNITS'] = 2  # Assuming decimal units
    doc.header['$LUPREC'] = 4  # Precision for linear units
    doc.header['$AUPREC'] = 4  # Precision for angular units

def verify_dxf_settings(filename):
    loaded_doc = ezdxf.readfile(filename)
    print(f"INSUNITS after load: {loaded_doc.header['$INSUNITS']}")
    print(f"LUNITS after load: {loaded_doc.header['$LUNITS']}")
    print(f"LUPREC after load: {loaded_doc.header['$LUPREC']}")
    print(f"AUPREC after load: {loaded_doc.header['$AUPREC']}")

def get_style(style, project_loader):
    if isinstance(style, str):
        return project_loader.get_style(style)
    return style

def apply_style_to_entity(entity, style, project_loader, item_type='area'):
    if entity.dxftype() == 'MTEXT':
        if 'height' in style:
            entity.dxf.char_height = style['height']
        if 'font' in style:
            entity.dxf.style = style['font']
    
    if 'color' in style:
        entity.dxf.color = get_color_code(style['color'], project_loader.name_to_aci)
    else:
        entity.dxf.color = ezdxf.const.BYLAYER
    
    if 'linetype' in style:
        entity.dxf.linetype = style['linetype']
    else:
        entity.dxf.linetype = 'BYLAYER'
    
    if 'lineweight' in style:
        entity.dxf.lineweight = style['lineweight']
    else:
        entity.dxf.lineweight = ezdxf.const.LINEWEIGHT_BYLAYER
    
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

def create_hatch(msp, boundary_paths, style, project_loader, is_legend=False):
    hatch = msp.add_hatch()
    
    hatch_style = style.get('hatch', {})
    pattern = hatch_style.get('pattern', 'SOLID')
    scale = hatch_style.get('scale', 1)
    
    if pattern != 'SOLID':
        try:
            hatch.set_pattern_fill(pattern, scale=scale)
        except ezdxf.DXFValueError:
            print(f"Invalid hatch pattern: {pattern}. Using SOLID instead.")
            hatch.set_pattern_fill("SOLID")
    else:
        hatch.set_solid_fill()

    for path in boundary_paths:
        hatch.paths.add_polyline_path(path)
    
    # Apply color and transparency only for legend items
    if is_legend:
        if 'color' in style:
            hatch.dxf.color = get_color_code(style['color'], project_loader.name_to_aci)
        if 'transparency' in style:
            transparency = convert_transparency(style['transparency'])
            if transparency is not None:
                set_hatch_transparency(hatch, transparency)
    else:
        hatch.dxf.color = ezdxf.const.BYLAYER
    
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
        'attachment_point': MTEXT_TOP_LEFT,
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
        attach_custom_data(mtext, script_identifier)
        
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
    # Define a set of allowed characters, including German-specific ones
    allowed_chars = r'a-zA-Z0-9_\-öüäßÖÜÄ'
    
    # Replace disallowed characters with underscores
    sanitized = re.sub(f'[^{allowed_chars}]', '_', name)
    
    # Ensure the name starts with a letter, underscore, or allowed special character
    if not re.match(f'^[{allowed_chars}]', sanitized):
        sanitized = '_' + sanitized
    
    # Truncate to 255 characters (AutoCAD limit)
    return sanitized[:255]
