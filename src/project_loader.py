import yaml
import os
from src.utils import log_info, log_warning, log_error, resolve_path, log_debug
import traceback

# Default values for project settings
DEFAULT_DELETION_POLICY = 'confirm'
DEFAULT_SYNC_DIRECTION = 'skip'
DEFAULT_CONFLICT_RESOLUTION = 'prompt'
DEFAULT_VIEWPORT_LAYER = 'VIEWPORTS'
DEFAULT_TEXT_LAYER = 'Plantext'
DEFAULT_BLOCK_LAYER = 'BLOCKS'

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
                data = yaml.safe_load(file)
                if data is None:  # File is empty or contains only comments
                    log_debug(f"File {filename} is empty or contains only comments")
                    return {}
                return data
        elif required:
            raise ValueError(f"Required config file not found: {filepath}")
        return {}

    def load_project_settings(self):
        """Load project specific settings from the new folder structure"""
        # Load main project settings (stays at root)
        main_settings = self.load_yaml_file('project.yaml', required=True)

        # Allow projects to opt out of the global folder prefix
        if not main_settings.get('useFolderPrefix', True):
            self.folder_prefix = ''
            log_debug("Project opted out of folderPrefix")

        # Load root level geom_layers.yaml (main file)
        geom_layers = self.load_yaml_file('geom_layers.yaml', required=False) or {}

        # Load additional layer files from layers/ directory
        layers_dir = os.path.join(self.project_dir, 'layers')
        if os.path.isdir(layers_dir):
            import glob
            layer_files = sorted(glob.glob(os.path.join(layers_dir, '*.yaml')))
            for layer_file in layer_files:
                filename = os.path.relpath(layer_file, self.project_dir)
                extra_layers = self.load_yaml_file(filename, required=False) or {}
                extra_list = extra_layers.get('geomLayers', [])
                if extra_list:
                    if 'geomLayers' not in geom_layers:
                        geom_layers['geomLayers'] = []
                    geom_layers['geomLayers'].extend(extra_list)
                    log_debug(f"Loaded {len(extra_list)} layers from {filename}")
                # Also collect templates and apply entries from layer files
                for key in ('templates', 'apply'):
                    extra_items = extra_layers.get(key, [])
                    if extra_items:
                        if key not in geom_layers:
                            geom_layers[key] = []
                        geom_layers[key].extend(extra_items)

        # Expand templates
        geom_layers['geomLayers'] = self._expand_templates(geom_layers)

        # Load generated/ folder configurations (traditional push/skip only)
        legends = self.load_yaml_file('generated/legends.yaml', required=False) or {}
        path_arrays = self.load_yaml_file('generated/path_arrays.yaml', required=False) or {}
        block_placements = self.load_yaml_file('generated/block_placements.yaml', required=False) or {}
        wmts_wms_layers = self.load_yaml_file('generated/wmts_wms_layers.yaml', required=False) or {}

        # Load interactive/ folder configurations (auto sync mode content)
        viewports = self.load_yaml_file('interactive/viewports.yaml', required=False) or {}
        block_inserts = self.load_yaml_file('interactive/block_inserts.yaml', required=False) or {}
        text_inserts = self.load_yaml_file('interactive/text_inserts.yaml', required=False)
        if text_inserts:
            log_debug(f"Loaded {len(text_inserts.get('texts', []))} text inserts from interactive/text_inserts.yaml")
        else:
            log_debug("No text inserts found in interactive/text_inserts.yaml")

        # Extract global sync setting to use as default for entity-specific settings
        global_sync = main_settings.get('sync', 'skip')  # Global sync setting from project.yaml

                # Extract layer-based discovery settings - this is the only discovery control
        viewport_discovery_layers = viewports.get('discover_untracked_layers', []) if viewports else []
        text_discovery_layers = text_inserts.get('discover_untracked_layers', []) if text_inserts else []
        block_discovery_layers = block_inserts.get('discover_untracked_layers', []) if block_inserts else []

        # Extract global viewport settings with defaults (inheriting global sync)
        viewport_deletion_policy = viewports.get('deletion_policy', DEFAULT_DELETION_POLICY)
        viewport_default_layer = viewports.get('default_layer', DEFAULT_VIEWPORT_LAYER)
        viewport_sync = viewports.get('sync', global_sync)  # Inherit global sync setting

        # Extract global text insert settings with defaults (inheriting global sync)
        text_sync = text_inserts.get('sync', global_sync) if text_inserts else global_sync
        text_deletion_policy = text_inserts.get('deletion_policy', DEFAULT_DELETION_POLICY) if text_inserts else DEFAULT_DELETION_POLICY
        # Add support for global default layer for text inserts
        text_default_layer = text_inserts.get('default_layer', DEFAULT_TEXT_LAYER) if text_inserts else DEFAULT_TEXT_LAYER

        # Extract global block insert settings with defaults (inheriting global sync)
        block_sync = block_inserts.get('sync', global_sync) if block_inserts else global_sync
        block_deletion_policy = block_inserts.get('deletion_policy', DEFAULT_DELETION_POLICY) if block_inserts else DEFAULT_DELETION_POLICY
        # Add support for global default layer for block inserts
        block_default_layer = block_inserts.get('default_layer', DEFAULT_BLOCK_LAYER) if block_inserts else DEFAULT_BLOCK_LAYER

        # Extract global auto sync conflict resolution setting
        auto_conflict_resolution = main_settings.get('autoConflictResolution', DEFAULT_CONFLICT_RESOLUTION)

        # Validate deletion policies for both entity types
        valid_deletion_policies = {'auto', 'confirm', 'ignore'}
        if viewport_deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid viewport_deletion_policy '{viewport_deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using '{DEFAULT_DELETION_POLICY}'.")
            viewport_deletion_policy = DEFAULT_DELETION_POLICY

        if text_deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid text_deletion_policy '{text_deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using '{DEFAULT_DELETION_POLICY}'.")
            text_deletion_policy = DEFAULT_DELETION_POLICY

        # Validate auto conflict resolution policy
        valid_conflict_policies = {'prompt', 'yaml_wins', 'dxf_wins', 'skip'}
        if auto_conflict_resolution not in valid_conflict_policies:
            log_warning(f"Invalid auto_conflict_resolution '{auto_conflict_resolution}'. "
                       f"Valid values are: {', '.join(valid_conflict_policies)}. Using '{DEFAULT_CONFLICT_RESOLUTION}'.")
            auto_conflict_resolution = DEFAULT_CONFLICT_RESOLUTION

        # Validate viewport layer
        if not isinstance(viewport_default_layer, str) or not viewport_default_layer.strip():
            log_warning(f"Invalid viewport default layer '{viewport_default_layer}'. Must be a non-empty string. Using '{DEFAULT_VIEWPORT_LAYER}'.")
            viewport_default_layer = DEFAULT_VIEWPORT_LAYER

        # Validate sync directions for both entity types
        valid_sync_values = {'push', 'pull', 'skip', 'auto'}
        if viewport_sync not in valid_sync_values:
            log_warning(f"Invalid global viewport sync value '{viewport_sync}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using '{DEFAULT_SYNC_DIRECTION}'.")
            viewport_sync = DEFAULT_SYNC_DIRECTION

        if text_sync not in valid_sync_values:
            log_warning(f"Invalid global text sync value '{text_sync}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using '{DEFAULT_SYNC_DIRECTION}'.")
            text_sync = DEFAULT_SYNC_DIRECTION

        if block_sync not in valid_sync_values:
            log_warning(f"Invalid global block sync value '{block_sync}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using '{DEFAULT_SYNC_DIRECTION}'.")
            block_sync = DEFAULT_SYNC_DIRECTION

        # Validate discovery layers settings
        def validate_discovery_layers(layers, entity_type):
            if layers == 'all':
                return 'all'
            elif isinstance(layers, list) and all(isinstance(layer, str) for layer in layers):
                return layers
            else:
                log_warning(f"Invalid {entity_type}_discovery_layers '{layers}'. "
                           f"Must be 'all' or a list of layer names. Using 'all'.")
                return 'all'

        viewport_discovery_layers = validate_discovery_layers(viewport_discovery_layers, 'viewport')
        text_discovery_layers = validate_discovery_layers(text_discovery_layers, 'text')
        block_discovery_layers = validate_discovery_layers(block_discovery_layers, 'block')

        # Extract CRS
        if 'crs' in main_settings:
            self.crs = main_settings['crs']
        else:
            log_error("No CRS specified in project settings. Please add 'crs' to project.yaml")
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

        # Expand 'hatch' property into synthetic applyHatch layers
        expanded_layers = []
        for layer in geom_layers.get('geomLayers', []):
            expanded_layers.append(layer)
            if 'hatch' in layer:
                for hatch_entry in layer['hatch']:
                    hatch_style = hatch_entry.get('style')
                    if hatch_style:
                        hatch_layer_name = hatch_entry.get('name', f"{layer['name']} Schraffur")
                        synthetic_layer = {
                            'name': hatch_layer_name,
                            'style': hatch_style,
                            'applyHatch': {
                                'layers': [layer['name']]
                            },
                        }
                        # Inherit sync from parent layer
                        if 'sync' in layer:
                            synthetic_layer['sync'] = layer['sync']
                        expanded_layers.append(synthetic_layer)
                        log_debug(f"Expanded hatch property on '{layer['name']}' into layer '{hatch_layer_name}'")
        geom_layers['geomLayers'] = expanded_layers

        # Load reducedDxf from separate file if it exists, otherwise use project.yaml
        reduced_dxf_config = self.load_yaml_file('reduced_dxf.yaml', required=False) or {}
        if 'reducedDxf' in reduced_dxf_config:
            main_settings['reducedDxf'] = reduced_dxf_config['reducedDxf']
            log_debug("Loaded reducedDxf config from reduced_dxf.yaml")

        # Merge all settings
        self.project_settings = {
            **main_settings,
            'geomLayers': geom_layers.get('geomLayers', []),
            'legends': self._apply_legend_defaults(legends),
            'viewports': viewports.get('viewports', []),
            'blocks': block_inserts.get('blocks', []),
            'texts': text_inserts.get('texts', []) if text_inserts else [],
            'pathArrays': path_arrays.get('pathArrays', []),
            'blockPlacements': block_placements.get('blockPlacements', []),
            'wmtsLayers': wmts_wms_layers.get('wmtsLayers', []),
            'wmsLayers': wmts_wms_layers.get('wmsLayers', []),

            # Global entity settings (generalized format)
            'viewport_deletion_policy': viewport_deletion_policy,
            'viewport_default_layer': viewport_default_layer,
            'viewport_sync': viewport_sync,
            'text_sync': text_sync,
            'text_deletion_policy': text_deletion_policy,
            'text_default_layer': text_default_layer,
            'block_sync': block_sync,
            'block_deletion_policy': block_deletion_policy,
            'block_discover_untracked_layers': block_discovery_layers,
            'block_default_layer': block_default_layer,
            'text_discover_untracked_layers': text_discovery_layers,
            'viewport_discover_untracked_layers': viewport_discovery_layers,

            # Auto sync settings
            'autoConflictResolution': auto_conflict_resolution,
        }

        # Process core settings
        # Extract DXF filename
        if 'dxfFilename' in self.project_settings:
            dxf_file_key = 'dxfFilename'
        else:
            log_error("No DXF file specified in project settings. Please add 'dxfFilename' to project.yaml")
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
        wmts_wms_file = os.path.join(self.project_dir, 'generated/wmts_wms_layers.yaml')
        if not os.path.exists(wmts_wms_file):
            return [], []

        with open(wmts_wms_file, 'r', encoding='utf-8') as f:
            wmts_wms_config = yaml.safe_load(f) or {}  # Use empty dict if None

        wmts_layers = wmts_wms_config.get('wmtsLayers', [])
        wms_layers = wmts_wms_config.get('wmsLayers', [])

        return wmts_layers, wms_layers

    def _apply_legend_defaults(self, legends_data):
        """Apply legendDefaults to each legend config. Each legend can override."""
        import copy
        legends_list = legends_data.get('legends', [])
        defaults = legends_data.get('legendDefaults', {})
        if not defaults:
            return legends_list

        result = []
        for legend in legends_list:
            merged = copy.deepcopy(defaults)
            # Deep merge: legend values override defaults
            for key, value in legend.items():
                if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
            result.append(merged)
            log_debug(f"Applied legend defaults to '{legend.get('name', legend.get('id', 'unnamed'))}'")

        return result

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

    def _expand_templates(self, geom_layers):
        """Expand template applications into concrete layers."""
        import copy

        # Collect templates from all loaded YAML data
        templates = {}

        # 1. Load tool-level templates from templates/ directory next to src/
        tool_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tool_templates_dir = os.path.join(tool_dir, 'templates')
        if os.path.isdir(tool_templates_dir):
            import glob as glob_mod
            for tpl_file in sorted(glob_mod.glob(os.path.join(tool_templates_dir, '*.yaml'))):
                tpl_data = None
                with open(tpl_file, 'r') as f:
                    tpl_data = yaml.safe_load(f)
                if tpl_data and 'templates' in tpl_data:
                    for tpl in tpl_data['templates']:
                        templates[tpl['name']] = tpl
                        log_debug(f"Loaded tool template '{tpl['name']}' from {tpl_file}")

        # 2. Load project-level templates from templates.yaml
        project_templates = self.load_yaml_file('templates.yaml', required=False) or {}
        for tpl in project_templates.get('templates', []):
            templates[tpl['name']] = tpl
            log_debug(f"Loaded project template '{tpl['name']}'")

        # 3. Collect inline templates from geomLayers data
        for tpl in geom_layers.get('templates', []):
            templates[tpl['name']] = tpl
            log_debug(f"Loaded inline template '{tpl['name']}'")

        if not templates:
            return geom_layers.get('geomLayers', [])

        # Process apply blocks
        all_layers = []
        for item in geom_layers.get('geomLayers', []):
            all_layers.append(item)

        # Process apply entries
        for apply_entry in geom_layers.get('apply', []):
            template_name = apply_entry.get('template')
            if template_name not in templates:
                log_warning(f"Template '{template_name}' not found, skipping")
                continue

            template = templates[template_name]
            params = apply_entry.get('params', {})

            # Handle 'each' for looping over a list
            each_values = apply_entry.get('each')
            if each_values:
                # 'each' provides a list of values for the first param
                each_param = template.get('params', [None])[0] if template.get('params') else None
                if each_param:
                    for val in each_values:
                        loop_params = {**params, each_param: val}
                        expanded = self._substitute_template(template, loop_params)
                        all_layers.extend(expanded)
                        log_debug(f"Expanded template '{template_name}' with {each_param}={val}: {len(expanded)} layers")
            else:
                expanded = self._substitute_template(template, params)
                all_layers.extend(expanded)
                log_debug(f"Expanded template '{template_name}': {len(expanded)} layers")

        return all_layers

    def _substitute_template(self, template, params):
        """Deep-substitute ${param} placeholders in a template's layers."""
        import copy
        import json

        layers = template.get('layers', [])
        # Serialize to JSON, substitute, deserialize
        layers_json = json.dumps(layers)

        for key, value in params.items():
            placeholder = '${' + key + '}'
            if isinstance(value, str):
                layers_json = layers_json.replace(placeholder, value)
            elif isinstance(value, list):
                json_list = json.dumps(value)
                # Replace standalone value: "${parcels}" -> ["1","2"]
                layers_json = layers_json.replace(f'"{placeholder}"', json_list)
                # Also replace within strings (e.g., in names)
                layers_json = layers_json.replace(placeholder, str(value))
            elif isinstance(value, (int, float, bool)):
                # For numeric/bool values, replace standalone string with raw value
                # e.g., "distance": "${inset_distance}" -> "distance": -5
                json_value = json.dumps(value)
                layers_json = layers_json.replace(f'"{placeholder}"', json_value)
                # Also replace within strings (e.g., in names)
                layers_json = layers_json.replace(placeholder, str(value))
            else:
                layers_json = layers_json.replace(placeholder, str(value))

        try:
            result = json.loads(layers_json)
        except json.JSONDecodeError as e:
            log_error(f"Template substitution produced invalid JSON: {e}")
            log_error(f"Result was: {layers_json[:500]}")
            return []

        return result

    def write_yaml_file(self, filename, data):
        """Write data to a YAML file in the project directory with atomic operations"""
        import tempfile
        import shutil

        filepath = os.path.join(self.project_dir, filename)
        target_dir = os.path.dirname(filepath)
        target_basename = os.path.basename(filepath)

        try:
            # Ensure target directory exists
            if target_dir and not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            # Create temporary file in the same directory for atomic write
            temp_fd = None
            temp_path = None

            temp_fd, temp_path = tempfile.mkstemp(
                prefix=f".{target_basename}.tmp.",
                suffix=".yaml",
                dir=target_dir or self.project_dir  # Use target dir or fallback to project_dir
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
