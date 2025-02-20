"""Configuration management module."""

import os
import yaml
import jsonschema
from typing import Dict, Any, Optional, Type, TypeVar, List, Set
from pathlib import Path
from src.core.utils import setup_logger
from src.config.project_config import ProjectConfig
from src.config.style_config import StyleConfig
from src.config.geometry_layer_config import GeometryLayerConfig
from src.config.schemas import (
    project_schema,
    geometry_layers_schema,
    styles_schema,
    additional_schemas
)
from src.config.schemas.validators import (
    ValidationError,
    validate_file_path,
    validate_style_references,
    validate_viewport_references,
    validate_layer_dependencies,
    validate_operation_parameters
)
from src.config.legend_config import LegendsConfig
from src.config.viewport_config import ViewportsConfig
from src.config.block_insert_config import BlockInsertsConfig
from src.config.text_insert_config import TextInsertsConfig
from src.config.path_array_config import PathArraysConfig
from src.config.web_service_config import WebServicesConfig

T = TypeVar('T')

# Define deprecated fields and their messages
DEPRECATED_FIELDS = {
    'geom_layers': {
        'labels': 'Use simpleLabelColumn instead',
        'label': 'Use simpleLabelColumn instead for simple text labels',
        'simpleLabel': 'Use simpleLabelColumn instead'
    },
    'geom_layers.yaml': {
        'old_field_name': ('Use new_field_name instead. This field will be removed in version X.Y.Z.', 'new_field_name'),
        'another_old_field': ('This field is deprecated and will be removed in version X.Y.Z.', None)
    }
}

class ConfigError(Exception):
    """Base class for configuration errors."""
    pass

class ConfigValidationError(ConfigError):
    """Configuration validation error."""
    pass

class ConfigFileNotFoundError(ConfigError):
    """Configuration file not found error."""
    pass

class ConfigManager:
    """Manages loading and validation of configuration files."""
    
    def __init__(self, project_dir: str):
        """Initialize with project directory.
        
        Args:
            project_dir: Absolute path to project directory
        """
        self.project_dir = Path(project_dir)
        self.logger = setup_logger(f"config_manager.{self.project_dir.name}")
        
        # Store root directory for global configurations
        self.root_dir = self.project_dir.parent.parent
        
        # Cache for loaded configurations
        self._style_cache: Optional[Dict[str, StyleConfig]] = None
        self._viewport_cache: Optional[Dict[str, Any]] = None
    
    def _load_yaml_file(self, filepath: Path, required: bool = True) -> dict:
        """Load and parse YAML file."""
        if not filepath.exists():
            if required:
                msg = f"Required config file not found: {filepath.relative_to(self.root_dir)}"
                self.logger.error(msg)
                raise ConfigFileNotFoundError(msg)
            self.logger.debug(f"Optional config file not found: {filepath.relative_to(self.root_dir)}")
            return {}
            
        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)
                if data is None:  # Empty file or only comments
                    self.logger.debug(f"Empty config file: {filepath.relative_to(self.root_dir)}")
                    return {}
                return data
        except yaml.YAMLError as e:
            msg = f"Error parsing YAML file {filepath.relative_to(self.root_dir)}: {str(e)}"
            self.logger.error(msg)
            raise ConfigError(msg) from e
    
    def _validate_config(self, data: dict, schema: dict, config_name: str) -> None:
        """Validate configuration against schema."""
        try:
            jsonschema.validate(data, schema)
        except jsonschema.exceptions.ValidationError as e:
            msg = f"Invalid {config_name} configuration: {str(e)}"
            self.logger.error(msg)
            raise ConfigValidationError(msg) from e
    
    def _check_deprecated_fields(self, data: dict, config_type: str) -> None:
        """Check for deprecated fields and log warnings."""
        if config_type not in DEPRECATED_FIELDS:
            return
            
        deprecated = DEPRECATED_FIELDS[config_type]
        for field, message in deprecated.items():
            if isinstance(data, dict) and field in data:
                self.logger.warning(f"Deprecated field '{field}': {message}")
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and field in item:
                        self.logger.warning(f"Deprecated field '{field}': {message}")
    
    def _load_and_validate(
        self,
        filename: str,
        schema: dict,
        config_name: str,
        required: bool = True,
        from_project: bool = True
    ) -> dict:
        """Load and validate configuration file."""
        filepath = self.project_dir / filename if from_project else self.root_dir / filename
        data = self._load_yaml_file(filepath, required)
        if data:  # Only validate non-empty configurations
            self._validate_config(data, schema, config_name)
        return data
    
    def _convert_config(
        self,
        data: dict,
        config_class: Type[T],
        folder_prefix: Optional[str] = None
    ) -> T:
        """Convert dictionary to configuration object."""
        try:
            return config_class.from_dict(data, folder_prefix)
        except (KeyError, ValueError, TypeError) as e:
            msg = f"Error converting to {config_class.__name__}: {str(e)}"
            self.logger.error(msg)
            raise ConfigError(msg) from e
    
    def _merge_style_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two style configurations, with override taking precedence."""
        merged = base.copy()
        
        for key, value in override.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, dict) and isinstance(merged[key], dict):
                merged[key] = self._merge_style_configs(merged[key], value)
            else:
                merged[key] = value
                
        return merged
    
    def _validate_project_paths(self, data: dict) -> None:
        """Validate paths in project configuration."""
        # Validate DXF file path
        validate_file_path(
            data['dxfFilename'],
            self.project_dir,
            must_exist=False,
            allowed_extensions={'.dxf'},
        )
        
        # Validate template if specified
        if 'template' in data:
            validate_file_path(
                data['template'],
                self.project_dir,
                must_exist=True,
                allowed_extensions={'.dxf'},
            )
        
        # Validate shapefile output directory if specified
        if 'shapefileOutputDir' in data:
            validate_file_path(
                data['shapefileOutputDir'],
                self.project_dir,
                must_exist=False,
                path_type="directory"
            )
    
    def _validate_geometry_layer_paths(self, data: dict) -> None:
        """Validate paths in geometry layer configuration."""
        for layer in data.get('geomLayers', []):
            if 'shapeFile' in layer:
                validate_file_path(
                    layer['shapeFile'],
                    self.project_dir,
                    must_exist=True,
                    allowed_extensions={'.shp'},
                )
    
    def _validate_cross_references(self, geometry_layers: List[Dict[str, Any]]) -> None:
        """Validate cross-references between configurations."""
        # Get available styles
        styles = self.load_styles()
        available_styles = set(styles.keys())
        
        # Get available viewports
        viewports = self.load_viewports()
        available_viewports = {vp.name for vp in viewports.viewports}
        
        # Validate style references
        validate_style_references(geometry_layers, available_styles)
        
        # Validate viewport references
        validate_viewport_references(geometry_layers, available_viewports)
        
        # Validate layer dependencies
        validate_layer_dependencies(geometry_layers)
        
        # Validate operation parameters
        validate_operation_parameters(geometry_layers)
    
    def load_project_config(self) -> ProjectConfig:
        """Load project configuration."""
        data = self._load_and_validate(
            'project.yaml',
            project_schema.SCHEMA,
            'project'
        )
        self._validate_project_paths(data)
        return self._convert_config(data, ProjectConfig)
    
    def load_geometry_layers(self) -> List[GeometryLayerConfig]:
        """Load geometry layer configuration."""
        data = self._load_and_validate(
            'geom_layers.yaml',
            geometry_layers_schema.SCHEMA,
            'geometry layers',
            required=False
        )
        
        if not data:
            return []
        
        self._validate_geometry_layer_paths(data)
        self._validate_cross_references(data.get('geomLayers', []))
        
        layers = []
        for layer_data in data.get('geomLayers', []):
            try:
                layer = GeometryLayerConfig.from_dict(layer_data)
                layers.append(layer)
            except Exception as e:
                self.logger.warning(f"Failed to load layer '{layer_data.get('name', 'unknown')}': {str(e)}")
                continue
                
        return layers
    
    def load_styles(self) -> Dict[str, StyleConfig]:
        """Load and merge global and project-specific style configurations."""
        # Load global styles first (from root directory)
        global_data = self._load_and_validate(
            'styles.yaml',
            styles_schema.SCHEMA,
            'global styles',
            required=False,
            from_project=False
        )
        
        # Load project-specific styles
        project_data = self._load_and_validate(
            'styles.yaml',
            styles_schema.SCHEMA,
            'project styles',
            required=False
        )
        
        # Start with global styles
        styles = {}
        for name, style_data in global_data.get('styles', {}).items():
            try:
                styles[name] = StyleConfig.from_dict(style_data)
            except Exception as e:
                self.logger.warning(f"Failed to load global style '{name}': {str(e)}")
                continue
        
        # Merge with project-specific styles
        for name, style_data in project_data.get('styles', {}).items():
            try:
                if name in styles:
                    # Merge with existing global style
                    merged_data = self._merge_style_configs(
                        styles[name].to_dict(),
                        style_data
                    )
                    styles[name] = StyleConfig.from_dict(merged_data)
                else:
                    # Add new project-specific style
                    styles[name] = StyleConfig.from_dict(style_data)
            except Exception as e:
                self.logger.warning(f"Failed to load project style '{name}': {str(e)}")
                continue
                
        return styles
    
    def load_legends(self) -> LegendsConfig:
        """Load legends configuration."""
        data = self._load_and_validate(
            'legends.yaml',
            additional_schemas.LEGENDS_SCHEMA,
            'legends',
            required=False
        )
        return LegendsConfig.from_dict(data)
    
    def load_viewports(self) -> ViewportsConfig:
        """Load viewports configuration."""
        data = self._load_and_validate(
            'viewports.yaml',
            additional_schemas.VIEWPORTS_SCHEMA,
            'viewports',
            required=False
        )
        return ViewportsConfig.from_dict(data)
    
    def load_block_inserts(self) -> BlockInsertsConfig:
        """Load block inserts configuration."""
        data = self._load_and_validate(
            'block_inserts.yaml',
            additional_schemas.BLOCK_INSERTS_SCHEMA,
            'block inserts',
            required=False
        )
        return BlockInsertsConfig.from_dict(data)
    
    def load_text_inserts(self) -> TextInsertsConfig:
        """Load text inserts configuration."""
        data = self._load_and_validate(
            'text_inserts.yaml',
            additional_schemas.TEXT_INSERTS_SCHEMA,
            'text inserts',
            required=False
        )
        return TextInsertsConfig.from_dict(data)
    
    def load_path_arrays(self) -> PathArraysConfig:
        """Load path arrays configuration."""
        data = self._load_and_validate(
            'path_arrays.yaml',
            additional_schemas.PATH_ARRAYS_SCHEMA,
            'path arrays',
            required=False
        )
        return PathArraysConfig.from_dict(data)
    
    def load_web_services(self) -> WebServicesConfig:
        """Load web services configuration."""
        data = self._load_and_validate(
            'web_services.yaml',
            additional_schemas.WEB_SERVICES_SCHEMA,
            'web services',
            required=False
        )
        return WebServicesConfig.from_dict(data)
    
    def load_wmts_wms_layers(self) -> Dict[str, Any]:
        """Load WMTS/WMS layers configuration."""
        return self._load_and_validate(
            'wmts_wms_layers.yaml',
            additional_schemas.WMTS_WMS_LAYERS_SCHEMA,
            'WMTS/WMS layers',
            required=False
        ) 