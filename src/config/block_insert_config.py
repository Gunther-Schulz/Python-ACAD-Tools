"""Block insert configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.config.position_config import Position
from src.core.types import LayerName

@dataclass
class BlockInsertConfig:
    """Configuration for a block insert."""
    name: str
    position: Position
    scale: float = 1.0
    rotation: float = 0.0
    layer: Optional[LayerName] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BlockInsertConfig':
        """Create BlockInsertConfig from dictionary."""
        return cls(
            name=data['name'],
            position=Position.from_dict(data['position']),
            scale=float(data.get('scale', 1.0)),
            rotation=float(data.get('rotation', 0.0)),
            layer=data.get('layer')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'name': self.name,
            'position': self.position.to_dict(),
            'scale': self.scale,
            'rotation': self.rotation
        }
        if self.layer:
            result['layer'] = self.layer
        return result

@dataclass
class BlockInsertsConfig:
    """Configuration for all block inserts."""
    blocks: List[BlockInsertConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BlockInsertsConfig':
        """Create BlockInsertsConfig from dictionary."""
        return cls(
            blocks=[BlockInsertConfig.from_dict(block) for block in data.get('blocks', [])]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'blocks': [block.to_dict() for block in self.blocks]
        } 