import re
import yaml

def parse_css_to_yaml(css_file_path, yaml_file_path):
    colors = []
    aci_code = 1
    
    with open(css_file_path, 'r') as css_file:
        css_content = css_file.read()
    
    # Regular expression to match color definitions
    pattern = r'\.([a-zA-Z-]+)\s*{\s*background-color:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\);\s*}'
    matches = re.findall(pattern, css_content)
    
    for match in matches:
        name, r, g, b = match
        colors.append({
            'name': name.replace('-', ' ').title(),
            'rgb': [int(r), int(g), int(b)],
            'aciCode': aci_code
        })
        aci_code = (aci_code % 255) + 1  # Cycle from 1 to 255
    
    # Write to YAML file
    with open(yaml_file_path, 'w') as yaml_file:
        yaml.dump(colors, yaml_file, default_flow_style=False)

# Usage
css_file_path = 'colors.css'
yaml_file_path = 'colors.yaml'
parse_css_to_yaml(css_file_path, yaml_file_path)