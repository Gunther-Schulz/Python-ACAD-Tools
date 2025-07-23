import yaml
import os
from src.utils import log_info, log_warning, log_error, resolve_path, log_debug
from src.dxf_processor import DXFProcessor
import traceback

class ProjectLoader:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.project_dir = os.path.join('projects', self.project_name)
        self.project_settings = {}
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

    def load_project_settings(self):
        """Load project specific settings from modular config files"""
        # Load main project settings
        main_settings = self.load_yaml_file('project.yaml', required=True)

        # Load additional configurations
        geom_layers = self.load_yaml_file('geom_layers.yaml', required=False) or {}
        legends = self.load_yaml_file('legends.yaml', required=False) or {}
        viewports = self.load_yaml_file('viewports.yaml', required=False) or {}
        block_inserts = self.load_yaml_file('block_inserts.yaml', required=False) or {}
        text_inserts = self.load_yaml_file('text_inserts.yaml', required=False)
        if text_inserts:
            log_debug(f"Loaded {len(text_inserts.get('textInserts', []))} text inserts from text_inserts.yaml")
        else:
            log_debug("No text inserts found in text_inserts.yaml")
        path_arrays = self.load_yaml_file('path_arrays.yaml', required=False) or {}
        wmts_wms_layers = self.load_yaml_file('wmts_wms_layers.yaml', required=False) or {}

        # Extract global viewport settings with defaults (new generalized format only)
        viewport_discovery = viewports.get('discovery', False)
        viewport_deletion_policy = viewports.get('deletion_policy', 'auto')
        viewport_layer = viewports.get('layer', 'VIEWPORTS')
        viewport_sync = viewports.get('sync', 'skip')

        # Extract global text insert settings with defaults
        text_sync = text_inserts.get('sync', 'push') if text_inserts else 'push'
        text_discovery = text_inserts.get('discovery', False) if text_inserts else False
        text_deletion_policy = text_inserts.get('deletion_policy', 'auto') if text_inserts else 'auto'

        # Extract global auto sync conflict resolution setting
        auto_conflict_resolution = main_settings.get('auto_conflict_resolution', 'prompt')

        # Validate deletion policies for both entity types
        valid_deletion_policies = {'auto', 'confirm', 'ignore'}
        if viewport_deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid viewport_deletion_policy '{viewport_deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using 'auto'.")
            viewport_deletion_policy = 'auto'

        if text_deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid text_deletion_policy '{text_deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using 'auto'.")
            text_deletion_policy = 'auto'

        # Validate auto conflict resolution policy
        valid_conflict_policies = {'prompt', 'yaml_wins', 'dxf_wins', 'skip'}
        if auto_conflict_resolution not in valid_conflict_policies:
            log_warning(f"Invalid auto_conflict_resolution '{auto_conflict_resolution}'. "
                       f"Valid values are: {', '.join(valid_conflict_policies)}. Using 'prompt'.")
            auto_conflict_resolution = 'prompt'

        # Validate viewport layer
        if not isinstance(viewport_layer, str) or not viewport_layer.strip():
            log_warning(f"Invalid viewport layer '{viewport_layer}'. Must be a non-empty string. Using 'VIEWPORTS'.")
            viewport_layer = 'VIEWPORTS'

        # Validate sync directions for both entity types
        valid_sync_values = {'push', 'pull', 'skip', 'auto'}
        if viewport_sync not in valid_sync_values:
            log_warning(f"Invalid global viewport sync value '{viewport_sync}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using 'skip'.")
            viewport_sync = 'skip'

        if text_sync not in valid_sync_values:
            log_warning(f"Invalid global text sync value '{text_sync}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using 'skip'.")
            text_sync = 'skip'

        # Extract CRS - handle both 'crs' and 'projectCrs' keys for compatibility
        if 'crs' in main_settings:
            self.crs = main_settings['crs']
        elif 'projectCrs' in main_settings:
            self.crs = main_settings['projectCrs']
        else:
            log_error("No CRS specified in project settings. Please add 'crs' or 'projectCrs' to project.yaml")
            raise ValueError("Missing CRS in project settings")

        # Check for duplicate layer names
        layer_names = {}
        for idx, layer in enumerate(geom_layers.get('geomLayers', [])):
            name = layer.get('name')
            if name in layer_names:
                log_warning(f"Duplicate layer name found: '{name}' at positions {layer_names[name]} and {idx}. "
                           f"The first definition will be used, subsequent definitions will be ignored.")
            else:
                layer_names[name] = idx

        # Merge all settings
        self.project_settings = {
            **main_settings,
            'geomLayers': geom_layers.get('geomLayers', []),
            'legends': legends.get('legends', []),
            'viewports': viewports.get('viewports', []),
            'blockInserts': block_inserts.get('blockInserts', []),
            'textInserts': text_inserts.get('textInserts', []) if text_inserts else [],
            'pathArrays': path_arrays.get('pathArrays', []),
            'wmtsLayers': wmts_wms_layers.get('wmtsLayers', []),
            'wmsLayers': wmts_wms_layers.get('wmsLayers', []),

            # Global entity settings (generalized format)
            'viewport_discovery': viewport_discovery,
            'viewport_deletion_policy': viewport_deletion_policy,
            'viewport_layer': viewport_layer,
            'viewport_sync': viewport_sync,
            'text_sync': text_sync,
            'text_discovery': text_discovery,
            'text_deletion_policy': text_deletion_policy,

            # Auto sync settings
            'auto_conflict_resolution': auto_conflict_resolution,
        }

        # Process core settings
        # Extract DXF filename - handle both 'dxfFilename' and 'dxfFile' keys for compatibility
        if 'dxfFilename' in self.project_settings:
            dxf_file_key = 'dxfFilename'
        elif 'dxfFile' in self.project_settings:
            dxf_file_key = 'dxfFile'
        else:
            log_error("No DXF file specified in project settings. Please add 'dxfFilename' or 'dxfFile' to project.yaml")
            raise ValueError("Missing DXF file in project settings")

        self.dxf_filename = resolve_path(self.project_settings[dxf_file_key], self.folder_prefix)
        self.template_dxf = resolve_path(self.project_settings.get('template', ''), self.folder_prefix) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Create output directory if it doesn't exist
        self.shapefile_output_dir = self.resolve_full_path(self.project_settings.get('shapefileOutputDir', ''))
        if self.shapefile_output_dir:
            os.makedirs(self.shapefile_output_dir, exist_ok=True)

        # Load WMTS/WMS layers
        wmts_layers, wms_layers = self.load_wmts_wms_layers()
        self.project_settings['wmtsLayers'] = wmts_layers
        self.project_settings['wmsLayers'] = wms_layers

        # Process layer operations
        for layer in self.project_settings.get('geomLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
            if 'shapeFile' in layer:
                layer['shapeFile'] = self.resolve_full_path(layer['shapeFile'])

        # Process WMTS/WMS layers operations
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

        # Load DXF operations settings
        dxf_operations_path = os.path.join(self.project_dir, 'dxf_operations.yaml')
        if os.path.exists(dxf_operations_path):
            with open(dxf_operations_path, 'r', encoding='utf-8') as f:
                dxf_operations_settings = yaml.safe_load(f)
                if dxf_operations_settings and 'dxfOperations' in dxf_operations_settings:
                    self.project_settings['dxfOperations'] = dxf_operations_settings['dxfOperations']
                    log_debug(f"Loaded DXF operations: {len(dxf_operations_settings['dxfOperations'].get('extracts', []))} extracts, "
                             f"{len(dxf_operations_settings['dxfOperations'].get('transfers', []))} transfers")

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
        log_debug(f"Retrieved style for '{style_name}': {style}")
        return style

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
            log_info("No DXF operations found in project settings")
            self.dxf_processor = None  # Set to None if no operations

    def write_yaml_file(self, filename, data):
        """Write data to a YAML file in the project directory with atomic operations"""
        import tempfile
        import shutil

        filepath = os.path.join(self.project_dir, filename)

        try:
            # Create temporary file in the same directory for atomic write
            temp_fd = None
            temp_path = None

            temp_fd, temp_path = tempfile.mkstemp(
                prefix=f".{filename}.tmp.",
                suffix=".yaml",
                dir=self.project_dir
            )
            os.close(temp_fd)  # Close file descriptor, we'll write using our method

            # Write to temporary file
            with open(temp_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            # Atomic move to final location
            if os.name == 'nt':  # Windows
                if os.path.exists(filepath):
                    os.remove(filepath)
                shutil.move(temp_path, filepath)
            else:  # Unix-like systems
                os.rename(temp_path, filepath)

            log_debug(f"Successfully wrote YAML file: {filepath}")
            return True

        except Exception as e:
            # Clean up temporary file if something went wrong
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    log_debug(f"Cleaned up temporary file: {temp_path}")
                except:
                    log_warning(f"Could not clean up temporary file: {temp_path}")

            log_error(f"Failed to write YAML file {filepath}: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")
            return False
