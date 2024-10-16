import random
import ezdxf
from ezdxf import enums

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
        return max(0, min(transparency, 1))
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

def ensure_layer_exists(doc, layer_name, layer_properties):
    if layer_name not in doc.layers:
        new_layer = doc.layers.new(layer_name)
        update_layer_properties(new_layer, layer_properties)
    else:
        existing_layer = doc.layers.get(layer_name)
        update_layer_properties(existing_layer, layer_properties)

def update_layer_properties(layer, properties):
    layer.color = properties.get('color', layer.color)
    layer.dxf.linetype = properties.get('linetype', layer.dxf.linetype)
    layer.dxf.lineweight = properties.get('lineweight', layer.dxf.lineweight)
    layer.dxf.plot = properties.get('plot', layer.dxf.plot)
    layer.is_locked = properties.get('locked', layer.is_locked)
    layer.is_frozen = properties.get('frozen', layer.is_frozen)
    layer.is_on = properties.get('is_on', layer.is_on)
    
    if 'transparency' in properties:
        transparency = convert_transparency(properties['transparency'])
        if transparency is not None:
            layer.transparency = transparency

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
