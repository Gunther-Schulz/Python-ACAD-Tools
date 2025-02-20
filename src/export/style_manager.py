"""Style management for export."""

from typing import Dict, Any, Optional

class StyleManager:
    """Manages style application."""
    
    def __init__(self, style_configs: Dict[str, Any]):
        """Initialize with style configurations."""
        self.style_configs = style_configs
    
    def get_style(self, style_name: str) -> Optional[Dict[str, Any]]:
        """Get style by name."""
        return self.style_configs.get(style_name) 