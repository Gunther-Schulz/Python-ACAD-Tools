"""Viewport configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.config.position_config import Position

@dataclass
class ViewportConfig:
    """Configuration for a viewport."""
    name: str
    center: Position
    scale: float
    rotation: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ViewportConfig':
        """Create ViewportConfig from dictionary."""
        return cls(
            name=data['name'],
            center=Position.from_dict(data['center']),
            scale=float(data['scale']),
            rotation=float(data.get('rotation', 0.0))
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'center': self.center.to_dict(),
            'scale': self.scale,
            'rotation': self.rotation
        }

@dataclass
class ViewportsConfig:
    """Configuration for all viewports."""
    viewports: List[ViewportConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ViewportsConfig':
        """Create ViewportsConfig from dictionary."""
        return cls(
            viewports=[ViewportConfig.from_dict(viewport) for viewport in data.get('viewports', [])]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'viewports': [viewport.to_dict() for viewport in self.viewports]
        } 