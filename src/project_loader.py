import yaml
import os
from src.utils import log_info, log_warning, log_error

class ProjectLoader:
    def __init__(self, project_name: str):
        self.load_project_settings(project_name)
        self.load_color_mapping()
        self.load_styles()

    def load_color_mapping(self):
        with open('aci_colors.yaml', 'r') as file:
            color_data = yaml.safe_load(file)
            self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
            self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}

    def load_project_settings(self, project_name: str):
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            self.project_config = data
            projects = data['projects']
            self.folder_prefix = data.get('folderPrefix', '')
            self.log_file = data.get('logFile', './log.txt')
            self.project_settings = next((project for project in projects if project['name'] == project_name), None)
            if not self.project_settings:
                raise ValueError(f"Project {project_name} not found.")

        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(self.project_settings['dxfFilename'])
        self.template_dxf = self.resolve_full_path(self.project_settings.get('template', '')) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Process layers to handle the new 'copy' operation
        for layer in self.project_settings['geomLayers']:
            if 'operations' in layer:
                self.process_operations(layer)

        self.shapefile_output_dir = self.resolve_full_path(self.project_settings.get('shapefileOutputDir', ''))

    def process_operations(self, layer):
        if 'operations' in layer:
            new_operations = []
            for operation in layer['operations']:
                if isinstance(operation, dict) and 'type' in operation:
                    new_operations.append(operation)
                else:
                    layer_name = layer.get('name', 'Unknown')
                    error_message = f"Invalid operation found in layer '{layer_name}': {operation}."
                    log_error(error_message)
                    raise ValueError(error_message)
            layer['operations'] = new_operations

    def resolve_full_path(self, path: str) -> str:
        return os.path.abspath(os.path.expanduser(os.path.join(self.folder_prefix, path)))

    def load_styles(self):
        with open('styles.yaml', 'r') as file:
            style_data = yaml.safe_load(file)
            self.styles = style_data.get('styles', {})

    def get_style(self, style_name):
        if isinstance(style_name, dict):
            return style_name
        style = self.styles.get(style_name, {})
        log_info(f"Retrieved style for '{style_name}': {style}")
        return style
