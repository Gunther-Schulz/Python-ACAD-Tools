"""
Project configuration and management.
"""
import os
from pathlib import Path
from typing import Dict, Any
from .exceptions import ProjectError
from ..utils.path import resolve_path
from ..utils.yaml_utils import load_yaml_file, load_yaml_with_key
from ..utils.logging import log_warning, log_info, log_debug


class Project:
    """Handles project configuration and management."""

    def __init__(self, project_name: str):
        """
        Initialize a new project.

        Args:
            project_name: Name of the project to load
        """
        self.project_name = project_name
        self.project_dir = os.path.join('projects', self.project_name)
        self.settings = {}  # Store all settings in a single dictionary

        # Validate project directory exists
        if not os.path.exists(self.project_dir):
            raise ProjectError(f"Project directory not found: {self.project_dir}")

        # Initialize settings
        self.folder_prefix = ""
        self.log_file = "./log.txt"
        self.dxf_filename = ""
        self.template_dxf = None
        self.export_format = "dxf"
        self.dxf_version = "R2010"
        self.shapefile_output_dir = ""
        self.crs = None
        self.name_to_aci = {}
        self.aci_to_name = {}
        self.styles = {}
        self.dxf_processor = None

        # Load all configurations
        self.load_global_settings()
        self.load_project_settings()
        self.load_color_mapping()
        self.load_styles()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from project settings using dictionary-style access.

        Args:
            key: Key to look up
            default: Default value if key not found

        Returns:
            Value from settings or default
        """
        return self.settings.get(key, default)

    def load_global_settings(self) -> None:
        """Load global settings from projects.yaml"""
        data = load_yaml_file('projects.yaml')
        self.folder_prefix = data.get('folderPrefix', '')
        self.log_file = data.get('logFile', './log.txt')
        log_info(f"Loaded global settings from projects.yaml")

    def load_project_settings(self) -> None:
        """Load project specific settings from modular config files"""
        # Load main project settings
        main_settings = load_yaml_file(
            os.path.join(self.project_dir, 'project.yaml')
        )

        # Load additional configurations with defaults
        geom_layers = load_yaml_with_key(
            os.path.join(self.project_dir, 'geom_layers.yaml'),
            'geomLayers',
            required=False,
            default=[]
        )
        legends = load_yaml_with_key(
            os.path.join(self.project_dir, 'legends.yaml'),
            'legends',
            required=False,
            default=[]
        )
        viewports = load_yaml_with_key(
            os.path.join(self.project_dir, 'viewports.yaml'),
            'viewports',
            required=False,
            default=[]
        )
        block_inserts = load_yaml_with_key(
            os.path.join(self.project_dir, 'block_inserts.yaml'),
            'blockInserts',
            required=False,
            default=[]
        )
        text_inserts = load_yaml_with_key(
            os.path.join(self.project_dir, 'text_inserts.yaml'),
            'textInserts',
            required=False,
            default=[]
        )
        path_arrays = load_yaml_with_key(
            os.path.join(self.project_dir, 'path_arrays.yaml'),
            'pathArrays',
            required=False,
            default=[]
        )
        wmts_wms_layers = load_yaml_file(
            os.path.join(self.project_dir, 'wmts_wms_layers.yaml'),
            required=False,
            default={}
        )

        # Merge all configurations
        self.settings = {
            **main_settings,
            'geomLayers': geom_layers,
            'legends': legends,
            'viewports': viewports,
            'blockInserts': block_inserts,
            'textInserts': text_inserts,
            'pathArrays': path_arrays,
            'wmtsLayers': wmts_wms_layers.get('wmtsLayers', []),
            'wmsLayers': wmts_wms_layers.get('wmsLayers', [])
        }

        # Process core settings
        self.crs = self.settings['crs']
        self.dxf_filename = self.resolve_full_path(
            self.settings['dxfFilename']
        )
        self.template_dxf = self.resolve_full_path(
            self.settings.get('template', '')
        ) if self.settings.get('template') else None
        self.export_format = self.settings.get('exportFormat', 'dxf')
        self.dxf_version = self.settings.get('dxfVersion', 'R2010')

        # Create output directory if it doesn't exist
        self.shapefile_output_dir = self.resolve_full_path(
            self.settings.get('shapefileOutputDir', '')
        )
        if self.shapefile_output_dir:
            os.makedirs(self.shapefile_output_dir, exist_ok=True)

        # Process layer operations
        for layer in self.settings.get('geomLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
            if 'shapeFile' in layer:
                layer['shapeFile'] = self.resolve_full_path(
                    layer['shapeFile']
                )

        # Process WMTS/WMS layers operations
        for layer in self.settings.get('wmtsLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
                for operation in layer['operations']:
                    operation['type'] = 'wmts'

        for layer in self.settings.get('wmsLayers', []):
            if 'operations' in layer:
                self.process_operations(layer)
                for operation in layer['operations']:
                    operation['type'] = 'wms'

    def load_color_mapping(self) -> None:
        """Load color mapping from aci_colors.yaml"""
        try:
            data = load_yaml_file('aci_colors.yaml', required=False)
            if data:
                self.name_to_aci = {
                    item['name'].lower(): item['aciCode']
                    for item in data
                }
                self.aci_to_name = {
                    item['aciCode']: item['name']
                    for item in data
                }
            else:
                # Use default color mapping
                self.name_to_aci = {
                    'white': 7, 'red': 1, 'yellow': 2, 'green': 3,
                    'cyan': 4, 'blue': 5, 'magenta': 6
                }
                self.aci_to_name = {
                    v: k for k, v in self.name_to_aci.items()
                }
                log_warning(
                    "Using default color mapping due to missing aci_colors.yaml"
                )
        except ProjectError:
            # Use default color mapping
            self.name_to_aci = {
                'white': 7, 'red': 1, 'yellow': 2, 'green': 3,
                'cyan': 4, 'blue': 5, 'magenta': 6
            }
            self.aci_to_name = {
                v: k for k, v in self.name_to_aci.items()
            }
            log_warning(
                "Using default color mapping due to missing aci_colors.yaml"
            )

    def load_styles(self) -> None:
        """Load styles from root styles.yaml"""
        try:
            self.styles = load_yaml_with_key(
                'styles.yaml',
                'styles',
                required=False,
                default={}
            )
        except ProjectError:
            log_warning(
                "styles.yaml not found in root directory. "
                "Using project-specific styles."
            )
            self.styles = self.project_settings.get('styles', {})

    def get_style(self, style_name: str) -> Dict[str, Any]:
        """
        Get a style by name from the loaded styles.

        Args:
            style_name: Name of the style to retrieve

        Returns:
            Style dictionary
        """
        if isinstance(style_name, dict):
            return style_name
        return self.styles.get(style_name, {})

    def resolve_full_path(self, path: str) -> str:
        """
        Resolve a path using the folder prefix.

        Args:
            path: Path to resolve

        Returns:
            Resolved path
        """
        return resolve_path(path, self.folder_prefix)

    def process_operations(self, layer: Dict[str, Any]) -> None:
        """
        Process and validate operations in a layer.

        Args:
            layer: Layer configuration dictionary
        """
        if 'operations' in layer:
            new_operations = []
            for operation in layer['operations']:
                if isinstance(operation, dict) and 'type' in operation:
                    new_operations.append(operation)
                else:
                    layer_name = layer.get('name', 'Unknown')
                    raise ProjectError(
                        f"Invalid operation found in layer '{layer_name}': "
                        f"{operation}"
                    )
            layer['operations'] = new_operations

        # Process shapeFile paths
        if 'shapeFile' in layer:
            layer['shapeFile'] = self.resolve_full_path(layer['shapeFile'])
