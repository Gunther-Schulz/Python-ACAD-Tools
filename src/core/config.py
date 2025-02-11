import os
import yaml
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from pathlib import Path

@dataclass
class GlobalConfig:
    folder_prefix: str
    log_file: str

@dataclass
class ProjectConfig:
    crs: str
    dxf_filename: str
    template_dxf: Optional[str]
    export_format: str
    dxf_version: str
    shapefile_output_dir: Optional[str]
    geom_layers: List[Dict[str, Any]]
    legends: List[Dict[str, Any]]
    viewports: List[Dict[str, Any]]
    block_inserts: List[Dict[str, Any]]
    text_inserts: List[Dict[str, Any]]
    path_arrays: List[Dict[str, Any]]
    wmts_layers: List[Dict[str, Any]]
    wms_layers: List[Dict[str, Any]]
    styles: Dict[str, Any]
    dxf_operations: Optional[Dict[str, Any]]

class ConfigManager:
    def __init__(self, project_name: str):
        """Initialize the configuration manager for a specific project.
        
        Args:
            project_name: Name of the project to load configuration for
        """
        self.project_name = project_name
        self.project_dir = Path('projects') / project_name
        self.global_config = self._load_global_config()
        self.project_config = self._load_project_config()
        self.color_mapping = self._load_color_mapping()
        self.styles = self._load_styles()

    def _load_yaml_file(self, filepath: Union[str, Path], required: bool = True) -> Dict:
        """Load and parse a YAML file.
        
        Args:
            filepath: Path to the YAML file
            required: Whether the file must exist
            
        Returns:
            Parsed YAML content as dictionary
            
        Raises:
            ValueError: If required file doesn't exist
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
                return data if data is not None else {}
        except FileNotFoundError:
            if required:
                raise ValueError(f"Required config file not found: {filepath}")
            return {}

    def _load_global_config(self) -> GlobalConfig:
        """Load global configuration from projects.yaml"""
        data = self._load_yaml_file('projects.yaml')
        return GlobalConfig(
            folder_prefix=data.get('folderPrefix', ''),
            log_file=data.get('logFile', './log.txt')
        )

    def _load_project_config(self) -> ProjectConfig:
        """Load project specific configuration from all config files"""
        # Load main project settings
        main_settings = self._load_yaml_file(self.project_dir / 'project.yaml')
        
        # Load modular configurations
        geom_layers = self._load_yaml_file(self.project_dir / 'geom_layers.yaml', required=False)
        legends = self._load_yaml_file(self.project_dir / 'legends.yaml', required=False)
        viewports = self._load_yaml_file(self.project_dir / 'viewports.yaml', required=False)
        block_inserts = self._load_yaml_file(self.project_dir / 'block_inserts.yaml', required=False)
        text_inserts = self._load_yaml_file(self.project_dir / 'text_inserts.yaml', required=False)
        path_arrays = self._load_yaml_file(self.project_dir / 'path_arrays.yaml', required=False)
        wmts_wms = self._load_yaml_file(self.project_dir / 'wmts_wms_layers.yaml', required=False)
        dxf_operations = self._load_yaml_file(self.project_dir / 'dxf_operations.yaml', required=False)

        # Validate layer names for uniqueness
        self._validate_layer_names(geom_layers.get('geomLayers', []))

        # Create output directory if specified
        shapefile_output_dir = self.resolve_path(main_settings.get('shapefileOutputDir', ''))
        if shapefile_output_dir:
            os.makedirs(shapefile_output_dir, exist_ok=True)

        return ProjectConfig(
            crs=main_settings['crs'],
            dxf_filename=self.resolve_path(main_settings['dxfFilename']),
            template_dxf=self.resolve_path(main_settings.get('template', '')) if main_settings.get('template') else None,
            export_format=main_settings.get('exportFormat', 'dxf'),
            dxf_version=main_settings.get('dxfVersion', 'R2010'),
            shapefile_output_dir=shapefile_output_dir,
            geom_layers=self._process_geom_layers(geom_layers.get('geomLayers', [])),
            legends=legends.get('legends', []),
            viewports=viewports.get('viewports', []),
            block_inserts=block_inserts.get('blockInserts', []),
            text_inserts=text_inserts.get('textInserts', []),
            path_arrays=path_arrays.get('pathArrays', []),
            wmts_layers=wmts_wms.get('wmtsLayers', []),
            wms_layers=wmts_wms.get('wmsLayers', []),
            styles=main_settings.get('styles', {}),
            dxf_operations=dxf_operations.get('dxfOperations') if dxf_operations else None
        )

    def _load_color_mapping(self) -> Dict[str, Dict[str, int]]:
        """Load color mapping from aci_colors.yaml"""
        try:
            color_data = self._load_yaml_file('aci_colors.yaml')
            return {
                'name_to_aci': {item['name'].lower(): item['aciCode'] for item in color_data},
                'aci_to_name': {item['aciCode']: item['name'] for item in color_data}
            }
        except (FileNotFoundError, ValueError):
            # Fallback to default color mapping
            default_mapping = {'white': 7, 'red': 1, 'yellow': 2, 'green': 3, 
                             'cyan': 4, 'blue': 5, 'magenta': 6}
            return {
                'name_to_aci': default_mapping,
                'aci_to_name': {v: k for k, v in default_mapping.items()}
            }

    def _load_styles(self) -> Dict[str, Any]:
        """Load styles from root styles.yaml"""
        try:
            style_data = self._load_yaml_file('styles.yaml')
            return style_data.get('styles', {})
        except (FileNotFoundError, ValueError):
            return self.project_config.styles

    def _validate_layer_names(self, layers: List[Dict[str, Any]]) -> None:
        """Validate layer names for uniqueness"""
        layer_names = {}
        for idx, layer in enumerate(layers):
            name = layer.get('name')
            if name in layer_names:
                raise ValueError(
                    f"Duplicate layer name found: '{name}' at positions {layer_names[name]} and {idx}"
                )
            layer_names[name] = idx

    def _process_geom_layers(self, layers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process geometry layers, resolving paths and validating operations"""
        for layer in layers:
            if 'shapeFile' in layer:
                layer['shapeFile'] = self.resolve_path(layer['shapeFile'])
            if 'operations' in layer:
                layer['operations'] = self._validate_operations(layer['operations'], layer.get('name', 'Unknown'))
        return layers

    def _validate_operations(self, operations: List[Dict[str, Any]], layer_name: str) -> List[Dict[str, Any]]:
        """Validate layer operations"""
        valid_operations = []
        for operation in operations:
            if isinstance(operation, dict) and 'type' in operation:
                valid_operations.append(operation)
            else:
                raise ValueError(f"Invalid operation found in layer '{layer_name}': {operation}")
        return valid_operations

    def resolve_path(self, path: str) -> str:
        """Resolve a path using the folder prefix"""
        if not path:
            return path
        return os.path.expanduser(os.path.join(self.global_config.folder_prefix, path))

    def get_style(self, style_name: Union[str, Dict]) -> Dict[str, Any]:
        """Get a style by name from the loaded styles"""
        if isinstance(style_name, dict):
            return style_name
        return self.styles.get(style_name, {})

    def get_color_code(self, color_name: str) -> Optional[int]:
        """Get ACI color code from color name"""
        return self.color_mapping['name_to_aci'].get(color_name.lower())

    def get_color_name(self, color_code: int) -> Optional[str]:
        """Get color name from ACI color code"""
        return self.color_mapping['aci_to_name'].get(color_code) 