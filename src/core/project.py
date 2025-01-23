from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
import os

from ..utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class ProjectConfig:
    """Project configuration data class."""
    name: str
    folder_prefix: Path
    dxf_filename: Path
    settings: Dict[str, Any]

class ProjectManager:
    """Handles project loading and configuration management."""
    
    def __init__(self, project_name: str):
        """Initialize project manager.
        
        Args:
            project_name: Name of the project to load
        """
        self.project_name = project_name
        self.config: Optional[ProjectConfig] = None
        self._load_project()
    
    def _load_project(self) -> None:
        """Load project configuration from YAML files."""
        project_dir = Path('projects') / self.project_name
        
        if not project_dir.exists():
            raise ValueError(f"Project directory not found: {project_dir}")
        
        # Load main project settings
        project_file = project_dir / 'project.yaml'
        if not project_file.exists():
            raise ValueError(f"Project configuration file not found: {project_file}")
        
        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                settings = yaml.safe_load(f)
            
            if not settings:
                raise ValueError("Project settings file is empty")
            
            # Expand user path in folder prefix if present
            folder_prefix = settings.get('folderPrefix', '')
            folder_prefix = os.path.expanduser(folder_prefix)
            
            # Construct DXF filename
            dxf_filename = settings.get('dxfFilename', '')
            if not dxf_filename:
                dxf_filename = f"{self.project_name}.dxf"
            
            if folder_prefix:
                dxf_filename = os.path.join(folder_prefix, dxf_filename)
            
            self.config = ProjectConfig(
                name=self.project_name,
                folder_prefix=Path(folder_prefix),
                dxf_filename=Path(dxf_filename),
                settings=settings
            )
            
            logger.info(f"Loaded project configuration for: {self.project_name}")
            
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing project YAML: {e}") from e
        except Exception as e:
            raise ValueError(f"Error loading project: {e}") from e
    
    def get_config(self) -> ProjectConfig:
        """Get project configuration.
        
        Returns:
            ProjectConfig object containing project settings
            
        Raises:
            ValueError: If project configuration hasn't been loaded
        """
        if not self.config:
            raise ValueError("Project configuration not loaded")
        return self.config
    
    def get_additional_config(self, filename: str) -> Dict[str, Any]:
        """Load additional configuration file from project directory.
        
        Args:
            filename: Name of the configuration file (e.g. 'legends.yaml')
            
        Returns:
            Dictionary containing the configuration
            
        Raises:
            ValueError: If file doesn't exist or has invalid format
        """
        config_file = Path('projects') / self.project_name / filename
        
        if not config_file.exists():
            raise ValueError(f"Configuration file not found: {config_file}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration YAML: {e}") from e
        except Exception as e:
            raise ValueError(f"Error loading configuration: {e}") from e 