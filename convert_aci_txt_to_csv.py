import csv
import yaml
from colorsys import rgb_to_hsv

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])

def closest_colour(requested_colour, used_names):
    r, g, b = requested_colour
    
    # Check for pure colors
    pure_colors = {
        (255, 0, 0): "red",
        (255, 255, 0): "yellow",
        (0, 255, 0): "green",
        (0, 255, 255): "cyan",
        (0, 0, 255): "blue",
        (255, 0, 255): "magenta",
        (255, 255, 255): "white",
        (0, 0, 0): "black"
    }
    if (r, g, b) in pure_colors:
        return pure_colors[(r, g, b)]
    
    # Check for near-pure greys
    max_diff = max(abs(r - g), abs(r - b), abs(g - b))
    if max_diff <= 10:
        avg = (r + g + b) // 3
        grey_levels = [
            (32, "charcoal"), (64, "dark-grey"),
            (96, "grey"), (128, "medium-grey"),
            (192, "light-grey"), (224, "pale-grey"),
            (255, "off-white")
        ]
        return next((name for threshold, name in grey_levels if avg <= threshold), "off-white")
    
    # Convert RGB to HSV
    h, s, v = rgb_to_hsv(r/255, g/255, b/255)
    
    # Determine base hue
    hue_names = [
        (0.025, "red"), (0.05, "vermilion"), (0.085, "orange"),
        (0.12, "amber"), (0.17, "yellow"), (0.225, "chartreuse"),
        (0.35, "green"), (0.475, "spring-green"), (0.525, "cyan"),
        (0.575, "azure"), (0.625, "blue"), (0.7, "indigo"),
        (0.8, "violet"), (0.875, "purple"), (0.925, "magenta"),
        (0.975, "rose"), (1.0, "red")
    ]
    base_hue = next((name for threshold, name in hue_names if h <= threshold), "red")

    # Determine brightness
    if v < 0.2:
        brightness = "very-dark"
    elif v < 0.4:
        brightness = "dark"
    elif v > 0.9:
        brightness = "bright"
    elif v > 0.7:
        brightness = "light"
    else:
        brightness = "medium"

    # Determine saturation
    if s < 0.1:
        saturation = "grey"
    elif s < 0.3:
        saturation = "muted"
    elif s < 0.6:
        saturation = "moderate"
    elif s > 0.9:
        saturation = "vivid"
    else:
        saturation = "strong"

    # Additional descriptors
    additional_descriptors = {
        "red": ["crimson", "scarlet", "ruby", "cherry", "maroon", "burgundy", "cardinal", "carmine"],
        "orange": ["tangerine", "rust", "bronze", "copper", "amber", "terracotta", "cinnamon", "sienna"],
        "yellow": ["gold", "lemon", "mustard", "sand", "khaki", "ochre", "maize", "flax"],
        "green": ["emerald", "lime", "olive", "sage", "forest", "mint", "jade", "fern"],
        "blue": ["sapphire", "navy", "denim", "sky", "azure", "cobalt", "turquoise", "teal"],
        "purple": ["lavender", "plum", "mauve", "eggplant", "amethyst", "lilac", "periwinkle", "indigo"],
        "pink": ["salmon", "coral", "peach", "blush", "rose", "fuchsia", "cerise", "magenta"]
    }

    # Construct the name
    base_descriptors = [brightness, saturation, base_hue]
    name = "-".join(filter(None, base_descriptors))

    # Check if we need an additional descriptor
    if name in used_names.values() and (r, g, b) not in used_names:
        for descriptor in additional_descriptors.get(base_hue, []):
            new_name = "-".join(filter(None, [brightness, saturation, descriptor]))
            if new_name not in used_names.values():
                return new_name

        # If still not unique, try combinations
        for i, desc1 in enumerate(additional_descriptors.get(base_hue, [])):
            for desc2 in additional_descriptors.get(base_hue, [])[i+1:]:
                new_name = "-".join(filter(None, [brightness, desc1, desc2]))
                if new_name not in used_names.values():
                    return new_name

    return name

def get_colour_name(rgb_triplet, used_names):
    return closest_colour(rgb_triplet, used_names)

def convert_to_csv_css_and_yaml(input_file, output_csv, output_css, output_yaml):
    used_names = {}
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
            
            rgb = tuple(map(int, parts[7:10]))
            if rgb in used_names:
                color_name = used_names[rgb]
            else:
                color_name = closest_colour(rgb, used_names)
                used_names[rgb] = color_name
            
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
