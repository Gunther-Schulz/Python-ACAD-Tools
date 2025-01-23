from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

from ..utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class StyleConfig:
    """Style configuration."""
    color: Optional[str] = None
    linetype: Optional[str] = None
    lineweight: Optional[float] = None
    plot: bool = True
    locked: bool = False
    frozen: bool = False
    is_on: bool = True
    transparency: float = 0.0

@dataclass
class LegendConfig:
    """Legend configuration."""
    id: str
    title: str
    subtitle: Optional[str] = None
    max_width: float = 160.0
    title_spacing: float = 0.0
    subtitle_spacing: float = 4.0
    group_spacing: float = 3.0
    group_title_spacing: float = 2.0
    group_subtitle_spacing: float = 3.0
    item_spacing: float = 4.0
    position: Dict[str, float] = None
    title_text_style: Dict[str, Any] = None
    title_subtitle_style: Dict[str, Any] = None
    group_text_style: Dict[str, Any] = None
    subtitle_text_style: Dict[str, Any] = None
    item_text_style: Dict[str, Any] = None
    groups: List[Dict[str, Any]] = None

class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, project_dir: Path):
        """Initialize configuration manager.
        
        Args:
            project_dir: Project directory containing configuration files
        """
        self.project_dir = project_dir
        self.style_configs: Dict[str, StyleConfig] = {}
        self.legend_configs: Dict[str, LegendConfig] = {}
    
    def load_styles(self, filename: str = 'styles.yaml') -> Dict[str, StyleConfig]:
        """Load style configurations.
        
        Args:
            filename: Name of the styles configuration file
            
        Returns:
            Dictionary of style configurations
            
        Raises:
            ValueError: If file doesn't exist or has invalid format
        """
        config_file = self.project_dir / filename
        
        if not config_file.exists():
            raise ValueError(f"Style configuration file not found: {config_file}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config or not isinstance(config, dict):
                raise ValueError("Invalid style configuration format")
            
            # Parse style configurations
            for name, style_data in config.items():
                self.style_configs[name] = StyleConfig(
                    color=style_data.get('color'),
                    linetype=style_data.get('linetype'),
                    lineweight=style_data.get('lineweight'),
                    plot=style_data.get('plot', True),
                    locked=style_data.get('locked', False),
                    frozen=style_data.get('frozen', False),
                    is_on=style_data.get('is_on', True),
                    transparency=style_data.get('transparency', 0.0)
                )
            
            logger.info(f"Loaded {len(self.style_configs)} style configurations")
            return self.style_configs
            
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing style YAML: {e}") from e
        except Exception as e:
            raise ValueError(f"Error loading style configurations: {e}") from e
    
    def load_legends(self, filename: str = 'legends.yaml') -> Dict[str, LegendConfig]:
        """Load legend configurations.
        
        Args:
            filename: Name of the legends configuration file
            
        Returns:
            Dictionary of legend configurations
            
        Raises:
            ValueError: If file doesn't exist or has invalid format
        """
        config_file = self.project_dir / filename
        
        if not config_file.exists():
            raise ValueError(f"Legend configuration file not found: {config_file}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config or 'legends' not in config:
                raise ValueError("Invalid legend configuration format")
            
            # Parse legend configurations
            for legend_data in config['legends']:
                if 'id' not in legend_data:
                    continue
                    
                legend_id = legend_data['id']
                self.legend_configs[legend_id] = LegendConfig(
                    id=legend_id,
                    title=legend_data.get('title', ''),
                    subtitle=legend_data.get('subtitle'),
                    max_width=legend_data.get('max_width', 160.0),
                    title_spacing=legend_data.get('title_spacing', 0.0),
                    subtitle_spacing=legend_data.get('subtitle_spacing', 4.0),
                    group_spacing=legend_data.get('group_spacing', 3.0),
                    group_title_spacing=legend_data.get('group_title_spacing', 2.0),
                    group_subtitle_spacing=legend_data.get('group_subtitle_spacing', 3.0),
                    item_spacing=legend_data.get('item_spacing', 4.0),
                    position=legend_data.get('position'),
                    title_text_style=legend_data.get('titleTextStyle'),
                    title_subtitle_style=legend_data.get('titleSubtitleStyle'),
                    group_text_style=legend_data.get('groupTextStyle'),
                    subtitle_text_style=legend_data.get('subtitleTextStyle'),
                    item_text_style=legend_data.get('itemTextStyle'),
                    groups=legend_data.get('groups', [])
                )
            
            logger.info(f"Loaded {len(self.legend_configs)} legend configurations")
            return self.legend_configs
            
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing legend YAML: {e}") from e
        except Exception as e:
            raise ValueError(f"Error loading legend configurations: {e}") from e
    
    def get_style(self, name: str) -> Optional[StyleConfig]:
        """Get style configuration by name.
        
        Args:
            name: Name of the style
            
        Returns:
            Style configuration or None if not found
        """
        return self.style_configs.get(name)
    
    def get_legend(self, legend_id: str) -> Optional[LegendConfig]:
        """Get legend configuration by ID.
        
        Args:
            legend_id: ID of the legend
            
        Returns:
            Legend configuration or None if not found
        """
        return self.legend_configs.get(legend_id) 