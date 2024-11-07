import yaml
import os
from src.utils import log_info, log_warning, log_error, resolve_path

class ProjectLoader:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.project_dir = os.path.join('projects', self.project_name)
        self.load_global_settings()
        self.load_project_settings()
        self.load_color_mapping()
        self.load_styles()

    def load_global_settings(self):
        """Load global settings from projects.yaml"""
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            self.folder_prefix = data.get('folderPrefix', '')
            self.log_file = data.get('logFile', './log.txt')

    def load_yaml_file(self, filename, required=True):
        """Helper to load YAML files from project directory"""
        filepath = os.path.join(self.project_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as file:
                return yaml.safe_load(file)
        elif required:
            raise ValueError(f"Required config file not found: {filepath}")
        return {}

    def load_project_settings(self):
        """Load project specific settings from modular config files"""
        # First check if project directory exists
        if not os.path.exists(self.project_dir):
            # Try loading legacy single file
            legacy_file = os.path.join('projects', f'{self.project_name}.yaml')
            if os.path.exists(legacy_file):
                with open(legacy_file, 'r') as file:
                    self.project_settings = yaml.safe_load(file)
            else:
                available_projects = []
                # Check both directories and yaml files
                for item in os.listdir('projects'):
                    if os.path.isdir(os.path.join('projects', item)):
                        available_projects.append(item)
                    elif item.endswith('.yaml'):
                        available_projects.append(item[:-5])  # Remove .yaml extension
                
                error_msg = f"Project '{self.project_name}' not found.\n\nAvailable projects:"
                if available_projects:
                    error_msg += "\n  - " + "\n  - ".join(sorted(available_projects))
                else:
                    error_msg += "\n  No projects found."
                error_msg += "\n\nTip: Use --create-project to create a new project"
                raise ValueError(error_msg)
        else:
            # Load main project settings
            main_settings = self.load_yaml_file('project.yaml', required=True)
            
            # Load optional modular configs and handle None cases
            legends = self.load_yaml_file('legends.yaml', required=False) or {}
            geom_layers = self.load_yaml_file('geom_layers.yaml', required=False) or {}
            viewports = self.load_yaml_file('viewports.yaml', required=False) or {}
            block_inserts = self.load_yaml_file('block_inserts.yaml', required=False) or {}
            text_inserts = self.load_yaml_file('text_inserts.yaml', required=False) or {}
            path_arrays = self.load_yaml_file('path_arrays.yaml', required=False) or {}

            # Merge all configurations with safe defaults
            self.project_settings = {
                **main_settings,
                'legends': legends.get('legends', []),
                'geomLayers': geom_layers.get('geomLayers', []),
                'viewports': viewports.get('viewports', []),
                'blockInserts': block_inserts.get('blockInserts', []),
                'textInserts': text_inserts.get('textInserts', []),
                'pathArrays': path_arrays.get('pathArrays', [])
            }

        # Process core settings
        self.crs = self.project_settings['crs']
        self.dxf_filename = resolve_path(self.project_settings['dxfFilename'], self.folder_prefix)
        self.template_dxf = resolve_path(self.project_settings.get('template', ''), self.folder_prefix) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Create output directory if it doesn't exist
        self.shapefile_output_dir = self.resolve_full_path(self.project_settings.get('shapefileOutputDir', ''))
        if self.shapefile_output_dir:
            os.makedirs(self.shapefile_output_dir, exist_ok=True)

        # First load all layers
        wmts_layers, wms_layers = self.load_wmts_wms_layers()
        self.project_settings['wmtsLayers'] = wmts_layers
        self.project_settings['wmsLayers'] = wms_layers

        # Then process all layer operations
        for layer in self.project_settings.get('geomLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
            if 'shapeFile' in layer:
                layer['shapeFile'] = self.resolve_full_path(layer['shapeFile'])

        # Process WMTS/WMS layers operations
        for layer in self.project_settings.get('wmtsLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
                # Set type for each operation
                for operation in layer['operations']:
                    operation['type'] = 'wmts'

        for layer in self.project_settings.get('wmsLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
                # Set type for each operation
                for operation in layer['operations']:
                    operation['type'] = 'wms'

    def process_operations(self, layer):
        """Process and validate operations in a layer"""
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

    def load_color_mapping(self):
        """Load color mapping from aci_colors.yaml"""
        try:
            with open('aci_colors.yaml', 'r') as file:
                color_data = yaml.safe_load(file)
                self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
                self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}
        except FileNotFoundError:
            log_warning("aci_colors.yaml not found. Using default color mapping.")
            self.name_to_aci = {'white': 7, 'red': 1, 'yellow': 2, 'green': 3, 'cyan': 4, 'blue': 5, 'magenta': 6}
            self.aci_to_name = {v: k for k, v in self.name_to_aci.items()}

    def load_styles(self):
        """Load styles from root styles.yaml"""
        try:
            with open('styles.yaml', 'r') as file:
                style_data = yaml.safe_load(file)
                self.styles = style_data.get('styles', {})
        except FileNotFoundError:
            log_warning("styles.yaml not found. Using project-specific styles.")
            self.styles = self.project_settings.get('styles', {})

    def get_style(self, style_name):
        """Get a style by name from the loaded styles"""
        if isinstance(style_name, dict):
            return style_name
        style = self.styles.get(style_name, {})
        log_info(f"Retrieved style for '{style_name}': {style}")
        return style

    def resolve_full_path(self, path: str) -> str:
        """Resolve a path using the folder prefix"""
        return resolve_path(path, self.folder_prefix)

    def load_wmts_wms_layers(self):
        wmts_wms_file = os.path.join(self.project_dir, 'wmts_wms_layers.yaml')
        if not os.path.exists(wmts_wms_file):
            return [], []
        
        with open(wmts_wms_file, 'r', encoding='utf-8') as f:
            wmts_wms_config = yaml.safe_load(f)
        
        wmts_layers = wmts_wms_config.get('wmtsLayers', [])
        wms_layers = wmts_wms_config.get('wmsLayers', [])
        
        return wmts_layers, wms_layers
