import random
import ezdxf
from ezdxf import enums
from ezdxf import colors

def get_color_code(color, name_to_aci):
    if isinstance(color, int):
        if 1 <= color <= 255:
            return color
        else:
            random_color = random.randint(1, 255)
            print(f"Warning: Invalid color code {color}. Assigning random color: {random_color}")
            return random_color
    elif isinstance(color, str):
        color_lower = color.lower()
        if color_lower in name_to_aci:
            return name_to_aci[color_lower]
        else:
            random_color = random.randint(1, 255)
            print(f"Warning: Color name '{color}' not found. Assigning random color: {random_color}")
            return random_color
    else:
        random_color = random.randint(1, 255)
        print(f"Warning: Invalid color type. Assigning random color: {random_color}")
        return random_color

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
    """Attach custom data to identify entities created by this script."""
    try:
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
    except Exception as e:
        print(f"Error setting XDATA for entity {entity}: {str(e)}")

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

def apply_style_to_entity(entity, style, project_loader, item_type='area', is_legend_item=False):
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
    
    # Set transparency for legend items or when explicitly specified
    if is_legend_item or 'transparency' in style:
        transparency = convert_transparency(style.get('transparency', 0))
        if transparency is not None:
            entity.transparency = colors.float2transparency(transparency)

    # Apply specific styles based on item type
    if item_type == 'line':
        if 'linetype_scale' in style:
            entity.dxf.ltscale = style['linetype_scale']
        else:
            entity.dxf.ltscale = 1.0  # Default scale

def create_hatch(msp, boundary_paths, style, project_loader, is_legend_item=False):
    hatch = msp.add_hatch()
    
    pattern = style.get('hatch', {}).get('pattern', 'SOLID')
    scale = style.get('hatch', {}).get('scale', 1)
    
    if pattern != 'SOLID':
        try:
            hatch.set_pattern_fill(pattern, scale=scale)
        except ezdxf.DXFValueError:
            print(f"Invalid hatch pattern: {pattern}. Using SOLID instead.")
            hatch.set_pattern_fill("SOLID")
    
    for path in boundary_paths:
        hatch.paths.add_polyline_path(path)
    
    # Apply color
    if 'color' in style:
        hatch.dxf.color = get_color_code(style['color'], project_loader.name_to_aci)
    
    # We'll set transparency in create_area_item, so we don't need to do it here
    
    return hatch
