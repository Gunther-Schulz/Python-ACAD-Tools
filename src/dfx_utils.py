import random
import ezdxf

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
