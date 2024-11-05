import yaml
import os
from src.utils import log_info, log_warning, log_error, resolve_path

class ProjectLoader:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.load_global_settings()
        self.load_project_settings()
        self.load_color_mapping()
        self.load_styles()

    def load_global_settings(self):
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            self.folder_prefix = data.get('folderPrefix', '')
            self.log_file = data.get('logFile', './log.txt')

    def load_project_settings(self):
        # Create projects directory if it doesn't exist
        projects_dir = 'projects'
        if not os.path.exists(projects_dir):
            os.makedirs(projects_dir)
            log_warning(f"Created projects directory: {projects_dir}")

        project_file = os.path.join(projects_dir, f'{self.project_name}.yaml')
        if not os.path.exists(project_file):
            available_projects = [f[:-5] for f in os.listdir(projects_dir) if f.endswith('.yaml')]
            error_msg = f"Project file not found: {project_file}"
            if available_projects:
                error_msg += f"\nAvailable projects: {', '.join(available_projects)}"
            else:
                error_msg += "\nNo project files found in the projects directory."
                error_msg += "\nPlease create a project file with the .yaml extension in the projects directory."
            raise ValueError(error_msg)

        with open(project_file, 'r') as file:
            self.project_settings = yaml.safe_load(file)

        self.crs = self.project_settings['crs']
        self.dxf_filename = resolve_path(self.project_settings['dxfFilename'], self.folder_prefix)
        self.template_dxf = resolve_path(self.project_settings.get('template', ''), self.folder_prefix) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Process layers to handle operations
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
        return resolve_path(path, self.folder_prefix)

    def load_color_mapping(self):
        """Load color mapping from colors.yaml"""
        try:
            with open('colors.yaml', 'r') as file:
                color_data = yaml.safe_load(file)
                self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
                self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}
        except FileNotFoundError:
            log_warning("colors.yaml not found. Using default color mapping.")
            self.name_to_aci = {'white': 7, 'red': 1, 'yellow': 2, 'green': 3, 'cyan': 4, 'blue': 5, 'magenta': 6}
            self.aci_to_name = {v: k for k, v in self.name_to_aci.items()}

    def load_styles(self):
        """Load styles from project settings"""
        self.styles = self.project_settings.get('styles', {})
        if not self.styles:
            log_warning("No styles found in project settings")

    def get_style(self, style_name):
        """Get a style by name from the loaded styles"""
        if style_name in self.styles:
            return self.styles[style_name]
        log_warning(f"Style '{style_name}' not found in styles configuration")
        return None
