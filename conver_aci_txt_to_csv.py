import csv
import yaml
from colorsys import rgb_to_hsv

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])

def closest_colour(requested_colour, used_names):
    r, g, b = requested_colour
    
    # Check for pure white and black
    if r == g == b == 255:
        return "white"
    if r == g == b == 0:
        return "black"
    
    # Check for pure or near-pure greys
    max_diff = max(abs(r - g), abs(r - b), abs(g - b))
    if max_diff <= 5:  # Tolerance for near-greys
        avg = (r + g + b) // 3
        grey_levels = [
            (16, "charcoal"), (32, "coal"), (48, "dark-slate"),
            (64, "slate"), (80, "dim"), (96, "smoke"),
            (112, "ash"), (128, "stone"), (144, "overcast"),
            (160, "cloudy"), (176, "silver"), (192, "pale-silver"),
            (208, "light-silver"), (224, "pearl"), (240, "off-white")
        ]
        for threshold, name in grey_levels:
            if avg < threshold:
                return name
        return "near-white"
    
    # Convert RGB to HSV
    h, s, v = rgb_to_hsv(r/255, g/255, b/255)
    
    # Determine base hue
    hue_names = [
        (0.025, "red"), (0.05, "vermilion"), (0.075, "orange-red"),
        (0.1, "orange"), (0.125, "amber"), (0.15, "golden"),
        (0.175, "yellow"), (0.2, "lime"), (0.275, "chartreuse"),
        (0.35, "green"), (0.4, "emerald"), (0.45, "spring-green"),
        (0.5, "turquoise"), (0.55, "cyan"), (0.6, "azure"),
        (0.65, "cerulean"), (0.7, "blue"), (0.75, "indigo"),
        (0.8, "violet"), (0.85, "purple"), (0.9, "magenta"),
        (0.95, "fuchsia"), (1.0, "crimson")
    ]
    base_hue = next((name for threshold, name in hue_names if h <= threshold), "red")

    # Brightness levels
    brightness_levels = [
        (0.15, "very-dark"), (0.3, "dark"), (0.45, "deep"),
        (0.6, "medium"), (0.75, "soft"), (0.9, "light"),
        (1.0, "pale")
    ]
    brightness = next((name for threshold, name in brightness_levels if v <= threshold), "bright")

    # Saturation levels
    saturation_levels = [
        (0.15, "muted"), (0.3, "subdued"), (0.45, "moderate"),
        (0.6, "clear"), (0.75, "vivid"), (1.0, "intense")
    ]
    saturation = next((name for threshold, name in saturation_levels if s <= threshold), "pure")

    # Construct the new name
    name_parts = [brightness, saturation, base_hue]
    name = "-".join(filter(lambda x: x not in ["medium", "moderate"], name_parts))
    
    return name

def get_colour_name(rgb_triplet, used_names):
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
            
            # Write to CSV
            csv_writer.writerow([aci, autodesk, berechnet, ermittelt, color_name, rgb_to_hex(rgb)])
            
            # Write to CSS
            css_class_name = color_name.replace(' ', '-').lower()
            outfile_css.write(f".{css_class_name} {{ color: {rgb_to_hex(rgb)}; }} /* ACI: {aci} */\n")
            
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
