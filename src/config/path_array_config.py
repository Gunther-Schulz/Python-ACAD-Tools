"""Path array configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.core.types import LayerName

@dataclass
class PathArrayConfig:
    """Configuration for a path array."""
    name: str
    path: str
    block: str
    spacing: float
    align: bool = True
    layer: Optional[LayerName] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PathArrayConfig':
        """Create PathArrayConfig from dictionary."""
        return cls(
            name=data['name'],
            path=data['path'],
            block=data['block'],
            spacing=float(data['spacing']),
            align=bool(data.get('align', True)),
            layer=data.get('layer')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'name': self.name,
            'path': self.path,
            'block': self.block,
            'spacing': self.spacing,
            'align': self.align
        }
        if self.layer:
            result['layer'] = self.layer
        return result

@dataclass
class PathArraysConfig:
    """Configuration for all path arrays."""
    path_arrays: List[PathArrayConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PathArraysConfig':
        """Create PathArraysConfig from dictionary."""
        return cls(
            path_arrays=[PathArrayConfig.from_dict(array) for array in data.get('pathArrays', [])]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pathArrays': [array.to_dict() for array in self.path_arrays]
        } 