import ezdxf
import yaml
from pathlib import Path

def get_layer_info(layer):
    return {
        "name": layer.dxf.name,
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
        "on": not bool(layer.dxf.flags & 2),
        "vp_freeze": bool(layer.dxf.flags & 8),
        "transparency": layer.transparency,
        "handle": layer.dxf.handle,
        "owner": layer.dxf.owner,
    }

# Load the DXF file
dxf_path = Path("/home/g/hidrive/Öffentlich Planungsbüro Schulz/Allgemein/CAD/Zeichnung.dxf")
doc = ezdxf.readfile(dxf_path)

# Load the colors from colors.yaml
with open("colors.yaml", "r") as color_file:
    colors = yaml.safe_load(color_file)

# Create a dictionary to map ACI codes to color names
aci_to_name = {color['aciCode']: color['name'] for color in colors}

# Get all layers and their properties
layers = [get_layer_info(layer) for layer in doc.layers]

# Write the layer information to tample_styles.yaml
output = {"layers": layers}
with open("template_styles.yaml", "w") as output_file:
    yaml.dump(output, output_file, default_flow_style=False, sort_keys=False)

print("Layer styles have been written to tample_styles.yaml")