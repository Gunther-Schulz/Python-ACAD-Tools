import yaml
import os
from src.utils import log_info, log_warning, log_error, resolve_path

class ProjectLoader:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.project_dir = os.path.join('projects', self.project_name)
        self.project_settings = {}
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
        # Load main project settings
        main_settings = self.load_yaml_file('project.yaml', required=True)
        
        # Load additional configurations
        geom_layers = self.load_yaml_file('geom_layers.yaml', required=False) or {}
        legends = self.load_yaml_file('legends.yaml', required=False) or {}
        viewports = self.load_yaml_file('viewports.yaml', required=False) or {}
        block_inserts = self.load_yaml_file('block_inserts.yaml', required=False) or {}
        text_inserts = self.load_yaml_file('text_inserts.yaml', required=False) or {}
        path_arrays = self.load_yaml_file('path_arrays.yaml', required=False) or {}
        wmts_wms_layers = self.load_yaml_file('wmts_wms_layers.yaml', required=False) or {}
        update_from_source = self.load_yaml_file('update_from_source.yaml', required=False) or {}

        # Merge all configurations with safe defaults
        self.project_settings = {
            **main_settings,
            'geomLayers': geom_layers.get('geomLayers', []),
            'legends': legends.get('legends', []),
            'viewports': viewports.get('viewports', []),
            'blockInserts': block_inserts.get('blockInserts', []),
            'textInserts': text_inserts.get('textInserts', []),
            'pathArrays': path_arrays.get('pathArrays', []),
            'wmtsLayers': wmts_wms_layers.get('wmtsLayers', []),
            'wmsLayers': wmts_wms_layers.get('wmsLayers', []),
            'updateFromSource': update_from_source.get('updateFromSource', [])  # Ensure this is loaded
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

        # Load and merge DXF transfer settings if they exist
        dxf_transfer_path = os.path.join(self.project_dir, 'dxf_transfer.yaml')
        if os.path.exists(dxf_transfer_path):
            with open(dxf_transfer_path, 'r', encoding='utf-8') as f:
                dxf_transfer_settings = yaml.safe_load(f)
                if dxf_transfer_settings and 'dxfTransfer' in dxf_transfer_settings:
                    self.project_settings['dxfTransfer'] = dxf_transfer_settings['dxfTransfer']
                    log_info(f"Loaded DXF transfer settings from {dxf_transfer_path}")

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
