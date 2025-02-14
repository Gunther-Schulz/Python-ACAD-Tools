import yaml
import os
from src.core.utils import log_info, log_warning, log_error, resolve_path, log_debug
from src.dxf.dxf_processor import DXFProcessor
from src.dxf_exporter.utils.style_defaults import DEFAULT_COLOR_MAPPING
from src.dxf_exporter.style_manager import StyleManager
from src.dxf_exporter.layer_manager import LayerManager

class ConfigurationManager:
    """Manages loading and validation of configuration files."""
    
    def __init__(self, project_dir):
        self.project_dir = project_dir
        
    def load_yaml_file(self, filename, required=True):
        """Helper to load YAML files from project directory"""
        filepath = os.path.join(self.project_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as file:
                data = yaml.safe_load(file)
                if data is None:  # File is empty or contains only comments
                    log_debug(f"File {filename} is empty or contains only comments")
                    return {}
                return data
        elif required:
            raise ValueError(f"Required config file not found: {filepath}")
        return {}
        
    def load_project_configs(self):
        """Load all project configuration files."""
        configs = {
            'main': self.load_yaml_file('project.yaml', required=True),
            'geom_layers': self.load_yaml_file('geom_layers.yaml', required=False),
            'legends': self.load_yaml_file('legends.yaml', required=False),
            'viewports': self.load_yaml_file('viewports.yaml', required=False),
            'block_inserts': self.load_yaml_file('block_inserts.yaml', required=False),
            'text_inserts': self.load_yaml_file('text_inserts.yaml', required=False),
            'path_arrays': self.load_yaml_file('path_arrays.yaml', required=False),
            'wmts_wms_layers': self.load_yaml_file('wmts_wms_layers.yaml', required=False),
            'styles': self.load_yaml_file('styles.yaml', required=False)
        }
        
        # Log loaded configurations
        for config_name, config_data in configs.items():
            if config_data:
                log_debug(f"Loaded configuration from {config_name}")
            else:
                log_debug(f"No configuration found for {config_name}")
                
        return configs
        
    def validate_layer_names(self, geom_layers):
        """Check for duplicate layer names."""
        layer_names = {}
        for idx, layer in enumerate(geom_layers.get('geomLayers', [])):
            name = layer.get('name')
            if name in layer_names:
                log_warning(f"Duplicate layer name found: '{name}' at positions {layer_names[name]} and {idx}. "
                           f"The first definition will be used, subsequent definitions will be ignored.")
            else:
                layer_names[name] = idx
        return layer_names

class ProjectLoader:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.project_dir = os.path.join('projects', self.project_name)
        self.project_settings = {}
        
        # Initialize configuration manager
        self.config_manager = ConfigurationManager(self.project_dir)
        
        # Load all configurations
        self.load_global_settings()
        self.load_project_settings()
        self.load_dxf_operations()
        self.load_color_mapping()
        self.load_styles()

    def load_global_settings(self):
        """Load global settings from projects.yaml"""
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            self.folder_prefix = data.get('folderPrefix', '')
            self.log_file = data.get('logFile', './log.txt')

    def load_project_settings(self):
        """Load project specific settings from modular config files"""
        # Load all configurations using the configuration manager
        configs = self.config_manager.load_project_configs()
        
        # Validate layer names
        self.config_manager.validate_layer_names(configs['geom_layers'])
        
        # Merge all configurations with safe defaults
        self.project_settings = {
            **configs['main'],
            'geomLayers': configs['geom_layers'].get('geomLayers', []),
            'legends': configs['legends'].get('legends', []),
            'viewports': configs['viewports'].get('viewports', []),
            'blockInserts': configs['block_inserts'].get('blockInserts', []),
            'textInserts': configs['text_inserts'].get('textInserts', []),
            'pathArrays': configs['path_arrays'].get('pathArrays', []),
            'wmtsLayers': configs['wmts_wms_layers'].get('wmtsLayers', []),
            'wmsLayers': configs['wmts_wms_layers'].get('wmsLayers', [])
        }

        # Process core settings
        self._process_core_settings()
        self._process_layer_paths()
        self._process_web_service_layers()

    def _process_core_settings(self):
        """Process core project settings."""
        self.crs = self.project_settings['crs']
        self.dxf_filename = resolve_path(self.project_settings['dxfFilename'], self.folder_prefix)
        self.template_dxf = resolve_path(self.project_settings.get('template', ''), self.folder_prefix) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Create output directory if it doesn't exist
        self.shapefile_output_dir = self.resolve_full_path(self.project_settings.get('shapefileOutputDir', ''))
        if self.shapefile_output_dir:
            os.makedirs(self.shapefile_output_dir, exist_ok=True)

    def _process_layer_paths(self):
        """Process paths in layer configurations."""
        for layer in self.project_settings.get('geomLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
            if 'shapeFile' in layer:
                layer['shapeFile'] = self.resolve_full_path(layer['shapeFile'])

    def _process_web_service_layers(self):
        """Process WMTS/WMS layer configurations."""
        for layer in self.project_settings.get('wmtsLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
                for operation in layer['operations']:
                    operation['type'] = 'wmts'

        for layer in self.project_settings.get('wmsLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
                for operation in layer['operations']:
                    operation['type'] = 'wms'

    def load_color_mapping(self):
        """Load color mapping from aci_colors.yaml"""
        try:
            with open('aci_colors.yaml', 'r') as file:
                color_data = yaml.safe_load(file)
                self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
                self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}
        except FileNotFoundError:
            log_warning("aci_colors.yaml not found. Using default color mapping.")
            self.name_to_aci = DEFAULT_COLOR_MAPPING
            self.aci_to_name = {v: k for k, v in self.name_to_aci.items()}

    def load_styles(self):
        """Load and merge styles from both root and project-specific styles.yaml files.
        Project-specific styles override root styles when they share the same preset name."""
        root_styles = {}
        project_styles = {}

        # First load root styles
        try:
            with open('styles.yaml', 'r') as file:
                style_data = yaml.safe_load(file)
                root_styles = style_data.get('styles', {})
                log_debug("Loaded root styles from styles.yaml")
        except FileNotFoundError:
            log_debug("No root styles.yaml found")

        # Then load project-specific styles
        project_style_data = self.config_manager.load_yaml_file('styles.yaml', required=False)
        if project_style_data:
            project_styles = project_style_data.get('styles', {})
            log_debug("Loaded project-specific styles from project/styles.yaml")

        # Merge styles, with project styles taking precedence
        self.styles = {**root_styles, **project_styles}

        # Log what happened
        if root_styles and project_styles:
            # Find which styles were overridden
            overridden = set(root_styles.keys()) & set(project_styles.keys())
            if overridden:
                log_debug(f"Project styles override root styles for: {', '.join(overridden)}")
            # Find which styles were only in project
            project_only = set(project_styles.keys()) - set(root_styles.keys())
            if project_only:
                log_debug(f"Styles only in project: {', '.join(project_only)}")
            # Find which styles were only in root
            root_only = set(root_styles.keys()) - set(project_styles.keys())
            if root_only:
                log_debug(f"Styles only in root: {', '.join(root_only)}")
        elif root_styles:
            log_debug("Using only root styles")
        elif project_styles:
            log_debug("Using only project-specific styles")
        else:
            log_warning("No styles found in either root or project. Using empty styles.")

    def resolve_full_path(self, path: str) -> str:
        """Resolve a path using the folder prefix"""
        return resolve_path(path, self.folder_prefix)

    def load_wmts_wms_layers(self):
        wmts_wms_file = os.path.join(self.project_dir, 'wmts_wms_layers.yaml')
        if not os.path.exists(wmts_wms_file):
            return [], []
        
        with open(wmts_wms_file, 'r', encoding='utf-8') as f:
            wmts_wms_config = yaml.safe_load(f) or {}  # Use empty dict if None
        
        wmts_layers = wmts_wms_config.get('wmtsLayers', [])
        wms_layers = wmts_wms_config.get('wmsLayers', [])
        
        return wmts_layers, wms_layers

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

    def load_dxf_operations(self):
        """Initialize DXFProcessor with loaded operations"""
        if 'dxfOperations' in self.project_settings:
            self.dxf_processor = DXFProcessor(self)
            log_debug("DXFProcessor initialized with loaded operations")
        else:
            log_debug("No DXF operations found in project settings")
            self.dxf_processor = None  # Set to None if no operations

class ServiceContainer:
    """Container for managing service dependencies."""
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self._services = {}

    def register(self, service_name, service_instance):
        """Register a service instance."""
        self._services[service_name] = service_instance

    def get(self, service_name):
        """Get a registered service instance."""
        return self._services.get(service_name)

    @staticmethod
    def create_default(project_loader):
        """Create a container with default service configuration."""
        container = ServiceContainer(project_loader)
        
        # Create and register core services
        style_manager = StyleManager(project_loader)
        layer_manager = LayerManager(project_loader, style_manager)
        
        # Register all services
        container.register('style_manager', style_manager)
        container.register('layer_manager', layer_manager)
        
        return container
