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
    if max_component - min_component > 20:
        if rgb[0] == max_component:
            return "reddish"
        elif rgb[1] == max_component:
            return "greenish"
        elif rgb[2] == max_component:
            return "bluish"
    return None

def closest_colour(requested_colour, used_names):
    min_colours = {}
    for rgb, name in COLOR_MAPPING.items():
        distance = get_color_distance(requested_colour, rgb)
        min_colours[distance] = name
    
    closest_names = sorted(min_colours.items())[:3]  # Get top 3 closest colors
    
    tint = detect_tint(requested_colour)
    if tint:
        for _, name in closest_names:
            if tint in name.lower():
                return name
    
    closest_name = closest_names[0][1]
    if closest_name in used_names:
        suffix = 1
        while f"{closest_name}-{suffix}" in used_names:
            suffix += 1
        return f"{closest_name}-{suffix}"
    return closest_name

def get_colour_name(rgb_triplet, used_names):
    hex_color = rgb_to_hex(rgb_triplet)
    try:
        name = webcolors.hex_to_name(hex_color)
        if name in used_names:
            return closest_colour(rgb_triplet, used_names)
        return name
    except ValueError:
        return closest_colour(rgb_triplet, used_names)

def convert_to_csv_css_and_yaml(input_file, output_csv, output_css, output_yaml):
    used_names = set()
    yaml_data = []
    
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
            color_name = get_colour_name(rgb, used_names)
            used_names.add(color_name)
            hex_color = rgb_to_hex(rgb)
            
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
