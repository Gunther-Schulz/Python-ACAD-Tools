"""Style configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class LayerProperties:
    """Layer properties configuration."""
    color: Optional[str] = None
    linetype: Optional[str] = None
    lineweight: Optional[int] = None
    plot: bool = True
    locked: bool = False
    frozen: bool = False
    is_on: bool = True
    transparency: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> 'LayerProperties':
        """Create LayerProperties from dictionary."""
        return cls(**{k: v for k, v in data.items() if v is not None})

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {k: v for k, v in self.__dict__.items() if v is not None}

@dataclass
class EntityProperties:
    """Entity properties configuration."""
    close: bool = True
    linetype_scale: float = 1.0
    linetype_generation: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> 'EntityProperties':
        """Create EntityProperties from dictionary."""
        return cls(
            close=data.get('close', True),
            linetype_scale=data.get('linetypeScale', 1.0),
            linetype_generation=data.get('linetypeGeneration', False)
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'close': self.close,
            'linetypeScale': self.linetype_scale,
            'linetypeGeneration': self.linetype_generation
        }

@dataclass
class TextProperties:
    """Text properties configuration."""
    height: float = 2.5
    font: str = "Arial"
    style: str = "Standard"
    color: Optional[str] = None
    attachment_point: str = "MIDDLE_LEFT"
    paragraph_align: str = "LEFT"

    @classmethod
    def from_dict(cls, data: dict) -> 'TextProperties':
        """Create TextProperties from dictionary."""
        paragraph = data.get('paragraph', {})
        return cls(
            height=data.get('height', 2.5),
            font=data.get('font', "Arial"),
            style=data.get('style', "Standard"),
            color=data.get('color'),
            attachment_point=data.get('attachmentPoint', "MIDDLE_LEFT"),
            paragraph_align=paragraph.get('align', "LEFT")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            'height': self.height,
            'font': self.font,
            'style': self.style,
            'attachmentPoint': self.attachment_point,
            'paragraph': {
                'align': self.paragraph_align
            }
        }
        if self.color:
            result['color'] = self.color
        return result

@dataclass
class StyleConfig:
    """Style configuration."""
    layer_properties: LayerProperties
    entity_properties: EntityProperties
    text_properties: Optional[TextProperties] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'StyleConfig':
        """Create StyleConfig from dictionary."""
        return cls(
            layer_properties=LayerProperties.from_dict(data.get('layer', {})),
            entity_properties=EntityProperties.from_dict(data.get('entity', {})),
            text_properties=TextProperties.from_dict(data['text']) if 'text' in data else None
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            'layer': self.layer_properties.to_dict(),
            'entity': self.entity_properties.to_dict()
        }
        if self.text_properties:
            result['text'] = self.text_properties.to_dict()
        return result 