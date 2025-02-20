"""Configuration management module."""

import os
import yaml
import jsonschema
from typing import Dict, Any, Optional, Type, TypeVar
from src.core.utils import setup_logger
from src.config.project_config import ProjectConfig
from src.config.style_config import StyleConfig
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
    
    def _load_yaml_file(self, filename: str, required: bool = True) -> dict:
        """Load and parse YAML file."""
        filepath = os.path.join(self.project_dir, filename)
        
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
        required: bool = True
    ) -> dict:
        """Load and validate configuration file."""
        data = self._load_yaml_file(filename, required)
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
    
    def load_project_config(self) -> ProjectConfig:
        """Load project configuration."""
        data = self._load_and_validate(
            'project.yaml',
            project_schema.SCHEMA,
            'project'
        )
        return self._convert_config(data, ProjectConfig)
    
    def load_geometry_layers(self) -> Dict[str, Any]:
        """Load geometry layer configuration."""
        return self._load_and_validate(
            'geom_layers.yaml',
            geometry_layers_schema.SCHEMA,
            'geometry layers',
            required=False
        )
    
    def load_styles(self) -> Dict[str, StyleConfig]:
        """Load style configuration."""
        data = self._load_and_validate(
            'styles.yaml',
            styles_schema.SCHEMA,
            'styles',
            required=False
        )
        
        styles = {}
        for name, style_data in data.get('styles', {}).items():
            try:
                styles[name] = StyleConfig.from_dict(style_data)
            except Exception as e:
                self.logger.warning(f"Failed to load style '{name}': {str(e)}")
                continue
                
        return styles 