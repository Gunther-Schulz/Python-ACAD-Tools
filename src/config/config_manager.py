"""Configuration management module."""

import os
import yaml
import jsonschema
from typing import Dict, Any, Optional, Type, TypeVar, List
from pathlib import Path
from src.core.utils import setup_logger
from src.config.project_config import ProjectConfig
from src.config.style_config import StyleConfig
from src.config.geometry_layer_config import GeometryLayerConfig
from src.config.schemas import (
    project_schema,
    geometry_layers_schema,
    styles_schema
)

T = TypeVar('T')

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
        """Initialize with project directory."""
        self.project_dir = project_dir
        self.logger = setup_logger(f"config_manager.{os.path.basename(project_dir)}")
        
        # Store root directory for global configurations
        self.root_dir = str(Path(project_dir).parent.parent)
    
    def _load_yaml_file(self, filepath: str, required: bool = True) -> dict:
        """Load and parse YAML file."""
        if not os.path.exists(filepath):
            if required:
                msg = f"Required config file not found: {filepath}"
                self.logger.error(msg)
                raise ConfigFileNotFoundError(msg)
            self.logger.debug(f"Optional config file not found: {filepath}")
            return {}
            
        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)
                if data is None:  # Empty file or only comments
                    self.logger.debug(f"Empty config file: {filepath}")
                    return {}
                return data
        except yaml.YAMLError as e:
            msg = f"Error parsing YAML file {filepath}: {str(e)}"
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
    
    def _load_and_validate(
        self,
        filename: str,
        schema: dict,
        config_name: str,
        required: bool = True,
        from_project: bool = True
    ) -> dict:
        """Load and validate configuration file."""
        filepath = os.path.join(self.project_dir if from_project else self.root_dir, filename)
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
    
    def load_project_config(self) -> ProjectConfig:
        """Load project configuration."""
        data = self._load_and_validate(
            'project.yaml',
            project_schema.SCHEMA,
            'project'
        )
        return self._convert_config(data, ProjectConfig)
    
    def load_geometry_layers(self) -> List[GeometryLayerConfig]:
        """Load geometry layer configuration."""
        data = self._load_and_validate(
            'geom_layers.yaml',
            geometry_layers_schema.SCHEMA,
            'geometry layers',
            required=False
        )
        
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