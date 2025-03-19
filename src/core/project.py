"""
Project configuration and management for OLADPP.
"""
import os
import yaml
import logging
from typing import Dict, Any, Optional, List, Tuple
from .exceptions import ProjectError

# Configure logging
logger = logging.getLogger(__name__)


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

        # Validate project directory exists
        if not os.path.exists(self.project_dir):
            raise ProjectError(f"Project directory not found: {self.project_dir}")

        # Initialize settings
        self.project_settings = {}
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

    def load_global_settings(self) -> None:
        """Load global settings from projects.yaml"""
        try:
            with open('projects.yaml', 'r') as file:
                data = yaml.safe_load(file)
                self.folder_prefix = data.get('folderPrefix', '')
                self.log_file = data.get('logFile', './log.txt')
                logger.info(f"Loaded global settings from projects.yaml")
        except FileNotFoundError:
            raise ProjectError("Global settings file (projects.yaml) not found in root directory")
        except yaml.YAMLError as e:
            raise ProjectError(f"Error parsing projects.yaml: {str(e)}")

    def load_yaml_file(self, filename: str, required: bool = True) -> Dict[str, Any]:
        """
        Helper to load YAML files from project directory.

        Args:
            filename: Name of the YAML file to load
            required: Whether the file is required

        Returns:
            Dictionary containing the YAML data
        """
        filepath = os.path.join(self.project_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as file:
                    data = yaml.safe_load(file)
                    if data is None:  # File is empty or contains only comments
                        logger.debug(f"File {filename} is empty or contains only comments")
                        return {}
                    logger.info(f"Loaded {filename}")
                    return data
            except yaml.YAMLError as e:
                raise ProjectError(f"Error parsing {filename}: {str(e)}")
        elif required:
            raise ProjectError(f"Required config file not found: {filepath}")
        logger.debug(f"Optional file not found: {filepath}")
        return {}

    def load_project_settings(self) -> None:
        """Load project specific settings from modular config files"""
        # Load main project settings
        main_settings = self.load_yaml_file('project.yaml', required=True)

        # Load additional configurations
        geom_layers = self.load_yaml_file('geom_layers.yaml', required=False) or {}
        legends = self.load_yaml_file('legends.yaml', required=False) or {}
        viewports = self.load_yaml_file('viewports.yaml', required=False) or {}
        block_inserts = self.load_yaml_file('block_inserts.yaml', required=False) or {}
        text_inserts = self.load_yaml_file('text_inserts.yaml', required=False)
        path_arrays = self.load_yaml_file('path_arrays.yaml', required=False) or {}
        wmts_wms_layers = self.load_yaml_file('wmts_wms_layers.yaml', required=False) or {}

        # Merge all configurations
        self.project_settings = {
            **main_settings,
            'geomLayers': geom_layers.get('geomLayers', []),
            'legends': legends.get('legends', []),
            'viewports': viewports.get('viewports', []),
            'blockInserts': block_inserts.get('blockInserts', []),
            'textInserts': text_inserts.get('textInserts', []),
            'pathArrays': path_arrays.get('pathArrays', []),
            'wmtsLayers': wmts_wms_layers.get('wmtsLayers', []),
            'wmsLayers': wmts_wms_layers.get('wmsLayers', [])
        }

        # Process core settings
        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(self.project_settings['dxfFilename'])
        self.template_dxf = self.resolve_full_path(self.project_settings.get('template', '')) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Create output directory if it doesn't exist
        self.shapefile_output_dir = self.resolve_full_path(self.project_settings.get('shapefileOutputDir', ''))
        if self.shapefile_output_dir:
            os.makedirs(self.shapefile_output_dir, exist_ok=True)

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

    def load_color_mapping(self) -> None:
        """Load color mapping from aci_colors.yaml"""
        try:
            with open('aci_colors.yaml', 'r') as file:
                color_data = yaml.safe_load(file)
                self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
                self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}
                logger.info("Loaded color mapping from aci_colors.yaml")
        except FileNotFoundError:
            logger.warning("aci_colors.yaml not found in root directory. Using default color mapping.")
            self.name_to_aci = {'white': 7, 'red': 1, 'yellow': 2, 'green': 3, 'cyan': 4, 'blue': 5, 'magenta': 6}
            self.aci_to_name = {v: k for k, v in self.name_to_aci.items()}
        except yaml.YAMLError as e:
            raise ProjectError(f"Error parsing aci_colors.yaml: {str(e)}")

    def load_styles(self) -> None:
        """Load styles from root styles.yaml"""
        try:
            with open('styles.yaml', 'r') as file:
                style_data = yaml.safe_load(file)
                self.styles = style_data.get('styles', {})
                logger.info("Loaded styles from styles.yaml")
        except FileNotFoundError:
            logger.warning("styles.yaml not found in root directory. Using project-specific styles.")
            self.styles = self.project_settings.get('styles', {})
        except yaml.YAMLError as e:
            raise ProjectError(f"Error parsing styles.yaml: {str(e)}")

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
        if not path:
            return ""
        return os.path.join(self.folder_prefix, path)

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
                    raise ProjectError(f"Invalid operation found in layer '{layer_name}': {operation}")
            layer['operations'] = new_operations
