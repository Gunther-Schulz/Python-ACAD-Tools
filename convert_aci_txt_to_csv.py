import csv
import yaml
from colorsys import rgb_to_hsv
import random

hue_names = [
    "red", "scarlet", "vermilion", "persimmon", "orange-red", "orange", "tangerine", "amber",
    "marigold", "yellow-orange", "yellow", "lemon", "lime", "lime-green", "chartreuse", "green", "spring-green",
    "mint-green", "emerald", "forest-green", "teal-green", "teal",
    "turquoise", "aqua", "cyan", "azure", "sky-blue", "cerulean", "cobalt", "blue",
    "royal-blue", "indigo", "violet", "purple", "lavender", "mauve", "magenta", "fuchsia",
    "hot-pink", "deep-pink", "rose", "crimson", "maroon"
]

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
    
    # Convert RGB to HSV
    h, s, v = rgb_to_hsv(r/255, g/255, b/255)
    
    # Check for near-neutral greys
    max_diff = max(abs(r - g), abs(r - b), abs(g - b))
    if max_diff <= 10:
        brightness_levels = [
            (0.1, "darkest"),
            (0.2, "darker"),
            (0.3, "dark"),
            (0.4, "deep"),
            (0.5, "medium"),
            (0.6, "moderate"),
            (0.7, "light"),
            (0.8, "bright"),
            (0.9, "pale"),
            (1.0, "lightest")
        ]
        brightness = next((name for threshold, name in brightness_levels if v <= threshold), "lightest")
        return f"{brightness}-grey"

    # Determine base hue
    hue_names = [
        (0.025, "red"), (0.05, "vermilion"), (0.085, "orange"),
        (0.12, "amber"), (0.15, "yellow"), (0.20, "lemon"),
        (0.275, "lime"), (0.325, "chartreuse"), (0.40, "green"),
        (0.475, "spring-green"), (0.525, "cyan"), (0.575, "azure"),
        (0.625, "blue"), (0.7, "indigo"), (0.8, "violet"),
        (0.875, "purple"), (0.925, "magenta"), (0.975, "rose"),
        (1.0, "red")
    ]
    base_hue = next((name for threshold, name in hue_names if h <= threshold), "red")

    # Determine brightness
    brightness_levels = [
        (0.15, "darkest"),
        (0.25, "darker"),
        (0.35, "dark"),
        (0.45, "deep"),
        (0.55, "medium"),
        (0.65, "moderate"),
        (0.75, "light"),
        (0.85, "bright"),
        (0.95, "vivid"),
        (1.0, "brilliant")
    ]
    brightness = next((name for threshold, name in brightness_levels if v <= threshold), "brilliant")

    # Determine saturation
    saturation_levels = [
        (0.15, "greyed"),
        (0.35, "muted"),
        (0.55, "soft"),
        (0.75, "clear"),
        (1.0, "intense")
    ]
    saturation = next((name for threshold, name in saturation_levels if s <= threshold), "intense")

    # Construct the name
    if saturation in ["greyed", "muted"]:
        return f"{brightness}-{saturation}-{base_hue}"
    elif saturation == "soft":
        return f"{brightness}-{base_hue}"
    else:
        return f"{brightness}-{saturation}-{base_hue}"

    # If we still don't have a unique name, use a combination of all descriptors
    return "-".join(filter(None, [brightness, saturation, base_hue]))

def get_colour_name(rgb_triplet, used_names):
    return closest_colour(rgb_triplet, used_names)

def get_unique_color_name(rgb, used_names):
    r, g, b = rgb
    rgb_tuple = tuple(rgb)

    if rgb_tuple in used_names:
        return used_names[rgb_tuple]
    
    basic_colors = {
        (255, 0, 0): "red", (255, 255, 0): "yellow", (0, 255, 0): "green",
        (0, 255, 255): "cyan", (0, 0, 255): "blue", (255, 0, 255): "magenta",
        (255, 255, 255): "white", (0, 0, 0): "black"
    }
    
    if rgb_tuple in basic_colors:
        return basic_colors[rgb_tuple]
    
    special_colors = {
        (255, 0, 0): "red",
        (255, 63, 0): "vermilion",
        (255, 127, 0): "orange",
        (255, 191, 0): "amber",
        (255, 255, 0): "yellow",
        (191, 255, 0): "lime",
        (127, 255, 0): "chartreuse",
        (63, 255, 0): "lime-green",
        (0, 255, 0): "green",
        (0, 255, 63): "bright-green",
        (0, 255, 127): "mint-green",
        (0, 255, 191): "aquamarine",
        (0, 255, 255): "cyan",
        (0, 191, 255): "sky-blue",
        (0, 127, 255): "azure",
        (0, 63, 255): "indigo",
        (0, 0, 255): "blue",
        (63, 0, 255): "violet",
        (127, 0, 255): "purple",
        (191, 0, 255): "lavender",
        (255, 0, 255): "magenta",
        (255, 0, 191): "fuchsia",
        (255, 0, 127): "deep-pink",
        (255, 0, 63): "rose"
    }
    
    if rgb_tuple in special_colors:
        return special_colors[rgb_tuple]
    
    h, s, v = rgb_to_hsv(r/255, g/255, b/255)

    # Adjusted hue ranges
    hue_ranges = [
        (0, 0.025, "red"), (0.025, 0.05, "vermilion"), (0.05, 0.085, "orange"),
        (0.085, 0.12, "amber"), (0.12, 0.15, "yellow"), (0.15, 0.20, "lemon"),
        (0.20, 0.275, "lime"), (0.275, 0.3125, "chartreuse"), (0.3125, 0.375, "green"),
        (0.375, 0.46, "spring-green"), (0.46, 0.525, "cyan"), (0.525, 0.575, "azure"),
        (0.575, 0.625, "blue"), (0.625, 0.7, "indigo"), (0.7, 0.8, "violet"),
        (0.8, 0.875, "purple"), (0.875, 0.925, "magenta"), (0.925, 1.0, "rose")
    ]

    base_name = next((name for start, end, name in hue_ranges if start <= h < end), "red")
    
    grey_shades = [
        "charcoal", "graphite", "lead", "iron", "steel",
        "slate", "pewter", "nickel", "aluminum", "silver",
        "ash", "smoke", "fog", "mist", "pearl"
    ]
    
    # Check if the color is a shade of grey
    if max(rgb) - min(rgb) <= 10:
        shade_index = min(int(v * len(grey_shades)), len(grey_shades) - 1)
        color_name = grey_shades[shade_index]
    else:
        sat_descs = ["pale", "soft", "vivid"]
        val_descs = ["darkest", "darker", "dark", "deep", "medium", "moderate", "light", "bright", "brilliant"]
        
        sat_desc = sat_descs[min(int(s * len(sat_descs)), len(sat_descs) - 1)]
        val_desc = val_descs[min(int(v * len(val_descs)), len(val_descs) - 1)]
        
        if s < 0.2:
            color_name = f"{val_desc}-{base_name}"
        elif v < 0.2:
            color_name = f"dark-{base_name}"
        elif v > 0.8 and s > 0.8:
            color_name = base_name
        else:
            color_name = f"{val_desc}-{sat_desc}-{base_name}"
    
    # Ensure uniqueness
    if color_name in used_names.values():
        if color_name in grey_shades:
            for prefix in ["cool", "neutral", "warm"]:
                new_name = f"{prefix}-{color_name}"
                if new_name not in used_names.values():
                    color_name = new_name
                    break
        else:
            hue_index = hue_names.index(base_name)
            for i in range(1, len(hue_names)):
                new_hue = hue_names[(hue_index + i) % len(hue_names)]
                new_name = color_name.replace(base_name, new_hue)
                if new_name not in used_names.values():
                    color_name = new_name
                    break
    
    used_names[rgb_tuple] = color_name
    return color_name

def convert_to_csv_css_and_yaml(input_file, output_csv, output_css, output_yaml):
    used_names = {}
    yaml_data = []
    color_data = []
    
    hue_names = [
        "red", "scarlet", "vermilion", "persimmon", "orange-red", "orange", "tangerine", "amber",
        "marigold", "yellow-orange", "yellow", "lemon", "lime", "lime-green", "chartreuse", "green", "spring-green",
        "mint-green", "emerald", "forest-green", "teal-green", "teal",
        "turquoise", "aqua", "cyan", "azure", "sky-blue", "cerulean", "cobalt", "blue",
        "royal-blue", "indigo", "violet", "purple", "lavender", "mauve", "magenta", "fuchsia",
        "hot-pink", "deep-pink", "rose", "crimson", "maroon"
    ]
    
    with open(input_file, 'r') as infile, \
         open(output_csv, 'w', newline='') as outfile_csv, \
         open(output_css, 'w') as outfile_css:
        
        csv_writer = csv.writer(outfile_csv)
        
        # Write header to CSV
        csv_writer.writerow(['ACI', 'AutoDESK', 'Berechnet', 'Ermittelt', 'Color Name', 'RGB'])
        
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
            
            # Use 'Berechnet' values for RGB
            rgb = tuple(map(int, parts[4:7]))
            
            color_name = get_unique_color_name(rgb, used_names)
            
            # Write to CSV
            csv_writer.writerow([aci, autodesk, berechnet, ermittelt, color_name, f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"])
            
            # Store unique colors
            css_class_name = color_name.replace(' ', '-').lower()
            color_data.append((int(aci), css_class_name, rgb))
            
            # Prepare YAML data
            yaml_data.append({
                'aciCode': int(aci),
                'name': color_name,
                'rgb': list(rgb)
            })
        
        # Sort color_data by ACI code and write to CSS file
        previous_aci = 0
        for aci, css_class_name, rgb in sorted(color_data, key=lambda x: x[0]):
            # Add an empty line before each group of special colors
            if aci in [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210, 220, 230, 240]:
                outfile_css.write("\n")
            
            outfile_css.write(f".{css_class_name} {{ color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); }} /* ACI: {aci} */\n")
            
            previous_aci = aci
    
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
