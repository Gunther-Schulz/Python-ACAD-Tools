"""Text insert configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.config.position_config import Position
from src.core.types import LayerName, StyleName

@dataclass
class TextInsertConfig:
    """Configuration for a text insert."""
    text: str
    position: Position
    style: Optional[StyleName] = None
    layer: Optional[LayerName] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextInsertConfig':
        """Create TextInsertConfig from dictionary."""
        return cls(
            text=data['text'],
            position=Position.from_dict(data['position']),
            style=data.get('style'),
            layer=data.get('layer')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'text': self.text,
            'position': self.position.to_dict()
        }
        if self.style:
            result['style'] = self.style
        if self.layer:
            result['layer'] = self.layer
        return result

@dataclass
class TextInsertsConfig:
    """Configuration for all text inserts."""
    texts: List[TextInsertConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextInsertsConfig':
        """Create TextInsertsConfig from dictionary."""
        return cls(
            texts=[TextInsertConfig.from_dict(text) for text in data.get('texts', [])]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'texts': [text.to_dict() for text in self.texts]
        } 