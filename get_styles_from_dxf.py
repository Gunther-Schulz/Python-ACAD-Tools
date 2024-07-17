import ezdxf
import yaml
from pathlib import Path




def decode_text(text):
    encodings = ['utf-8', 'latin-1', 'ascii']
    for encoding in encodings:
        try:
            return text.encode(encoding).decode('utf-8')
        except UnicodeEncodeError:
            continue
    return text

def str_presenter(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, str_presenter)

def get_layer_info(layer):
    return {
        "name": decode_text(layer.dxf.name),
        "color": {
            "index": layer.color,
            "name": aci_to_name.get(layer.color, f"Unknown Color ({layer.color})")
        },
        "true_color": layer.true_color if hasattr(layer, 'true_color') else None,
        "linetype": layer.dxf.linetype,
        "lineweight": layer.dxf.lineweight,
        "plot": bool(layer.dxf.plot),
        "locked": bool(layer.dxf.flags & 4),
        "frozen": bool(layer.dxf.flags & 1),
        "is_on": layer.is_on(),
        "vp_freeze": bool(layer.dxf.flags & 8),
        "transparency": layer.transparency,
        "handle": layer.dxf.handle,
        "owner": layer.dxf.owner,
    }

# Load the DXF file
dxf_path = Path("/home/g/hidrive/Öffentlich Planungsbüro Schulz/Allgemein/CAD/Zeichnung.dxf")
doc = ezdxf.readfile(dxf_path)

# Load the colors from colors.yaml
with open("colors.yaml", "r", encoding='utf-8') as color_file:
    colors = yaml.safe_load(color_file)

# Create a dictionary to map ACI codes to color names
aci_to_name = {color['aciCode']: color['name'] for color in colors}

# Get all layers and their properties
layers = [get_layer_info(layer) for layer in doc.layers]

# Write the layer information to tample_styles.yaml
output = {"layers": layers}
with open("template_styles.yaml", "w", encoding='utf-8') as output_file:
    yaml.dump(output, output_file, default_flow_style=False, sort_keys=False, allow_unicode=True)

print("Layer styles have been written to template_styles.yaml")