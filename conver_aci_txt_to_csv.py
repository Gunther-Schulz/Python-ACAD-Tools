import csv
import webcolors
import yaml
from math import sqrt

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])

def create_color_mapping():
    color_mapping = {}
    for name in webcolors.names():
        try:
            rgb = webcolors.name_to_rgb(name)
            color_mapping[rgb] = name
        except ValueError:
            # Skip colors that might not be recognized
            pass
    return color_mapping

COLOR_MAPPING = create_color_mapping()

def get_color_distance(c1, c2):
    # Weighted Euclidean distance, giving more weight to luminance differences
    return sqrt(2 * (c1[0] - c2[0])**2 + 4 * (c1[1] - c2[1])**2 + 3 * (c1[2] - c2[2])**2)

def detect_tint(rgb):
    # Detect if the color has a noticeable tint
    max_component = max(rgb)
    min_component = min(rgb)
    if max_component - min_component > 10:  # Lowered threshold for more sensitivity
        if rgb[0] == max_component:
            return "red"
        elif rgb[1] == max_component:
            return "green"
        elif rgb[2] == max_component:
            return "blue"
    return None

def closest_colour(requested_colour, used_names, previous_colors):
    r, g, b = requested_colour
    
    # Determine base hue
    if r > g and r > b:
        if b > g:
            base_hue = "purple" if b > r * 0.6 else "magenta"
        else:
            base_hue = "red"
    elif g > r and g > b:
        base_hue = "green"
    elif b > r and b > g:
        if r > g:
            base_hue = "purple" if r > b * 0.6 else "blue"
        else:
            base_hue = "blue"
    else:
        base_hue = "grey"

    # Brightness detection
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    if brightness < 64:
        brightness_prefix = "very-dark"
    elif brightness < 128:
        brightness_prefix = "dark"
    elif brightness > 220:
        brightness_prefix = "light"
    elif brightness > 180:
        brightness_prefix = "pale"
    else:
        brightness_prefix = ""

    # Saturation detection
    max_rgb = max(r, g, b)
    min_rgb = min(r, g, b)
    if max_rgb != 0:
        saturation = (max_rgb - min_rgb) / max_rgb
    else:
        saturation = 0

    if saturation > 0.7:
        saturation_prefix = "vivid"
    elif saturation > 0.4:
        saturation_prefix = "medium"
    else:
        saturation_prefix = "dull"

    # Construct the new name
    name_parts = [brightness_prefix, saturation_prefix, base_hue]
    name = "-".join(filter(None, name_parts))

    # Add simple numbering to avoid duplicates
    if name in used_names:
        suffix = 2
        while f"{name}-{suffix}" in used_names:
            suffix += 1
        name = f"{name}-{suffix}"
    
    return name

def get_colour_name(rgb_triplet, used_names, previous_colors):
    hex_color = rgb_to_hex(rgb_triplet)
    try:
        name = webcolors.hex_to_name(hex_color)
        if name in used_names:
            return closest_colour(rgb_triplet, used_names, previous_colors)
        return name
    except ValueError:
        return closest_colour(rgb_triplet, used_names, previous_colors)

def convert_to_csv_css_and_yaml(input_file, output_csv, output_css, output_yaml):
    used_names = set()
    yaml_data = []
    previous_colors = []
    
    # Add color name overrides
    color_overrides = {
        "dark-reddish-maroon-9": "black",
        "very-dark-black": "very-darkgrey"
    }
    
    with open(input_file, 'r') as infile, \
         open(output_csv, 'w', newline='') as outfile_csv, \
         open(output_css, 'w') as outfile_css:
        
        csv_writer = csv.writer(outfile_csv)
        
        # Write header to CSV
        csv_writer.writerow(['ACI', 'AutoDESK', 'Berechnet', 'Ermittelt', 'Color Name', 'Hex'])
        
        # Write CSS file header
        outfile_css.write("/* AutoCAD Color Index (ACI) colors */\n\n")
        
        # Skip the first two lines (header)
        next(infile)
        next(infile)
        
        for line in infile:
            # Strip whitespace and split the line
            parts = line.strip().split()
            
            # Skip empty lines or lines that don't start with a number
            if not parts or not parts[0].isdigit():
                continue
            
            # Extract values
            aci = parts[0]
            autodesk = f"{parts[1]},{parts[2]},{parts[3]}"
            berechnet = f"{parts[4]},{parts[5]},{parts[6]}"
            ermittelt = f"{parts[7]},{parts[8]},{parts[9]}"
            
            # Get color name and hex from Ermittelt RGB values
            rgb = tuple(map(int, parts[7:10]))
            color_name = get_colour_name(rgb, used_names, previous_colors)
            
            # Apply color name override if it exists
            original_color_name = color_name
            color_name = color_overrides.get(color_name.replace(' ', '-').lower(), color_name)
            
            used_names.add(color_name)
            hex_color = rgb_to_hex(rgb)
            
            # Update previous_colors
            previous_colors.append(color_name)
            if len(previous_colors) > 3:  # Keep only the last 3 colors
                previous_colors.pop(0)
            
            # Write to CSV
            csv_writer.writerow([aci, autodesk, berechnet, ermittelt, color_name, hex_color])
            
            # Write to CSS
            css_class_name = color_name.replace(' ', '-').lower()
            outfile_css.write(f".{css_class_name} {{ color: {hex_color}; }} /* ACI: {aci} */\n")
            
            # Prepare YAML data
            yaml_data.append({
                'aciCode': int(aci),
                'name': color_name,
                'rgb': list(rgb)
            })
    
    # Write YAML file
    with open(output_yaml, 'w') as outfile_yaml:
        yaml.dump(yaml_data, outfile_yaml, default_flow_style=False)

# Usage
input_file = 'aci_codes.txt'  # Your input text file
output_csv = 'aci_codes.csv'
output_css = 'aci_colors.css'
output_yaml = 'aci_colors.yaml'

convert_to_csv_css_and_yaml(input_file, output_csv, output_css, output_yaml)
print(f"Conversion complete. CSV file saved as {output_csv}")
print(f"CSS file saved as {output_css}")
print(f"YAML file saved as {output_yaml}")
