"""Legend configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.config.position_config import Position
from src.core.types import StyleName

@dataclass
class LegendConfig:
    """Configuration for a legend."""
    name: str
    position: Position
    style: Optional[StyleName] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LegendConfig':
        """Create LegendConfig from dictionary."""
        return cls(
            name=data['name'],
            position=Position.from_dict(data['position']),
            style=data.get('style')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'name': self.name,
            'position': self.position.to_dict()
        }
        if self.style:
            result['style'] = self.style
        return result

@dataclass
class LegendsConfig:
    """Configuration for all legends."""
    legends: List[LegendConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LegendsConfig':
        """Create LegendsConfig from dictionary."""
        return cls(
            legends=[LegendConfig.from_dict(legend) for legend in data.get('legends', [])]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'legends': [legend.to_dict() for legend in self.legends]
        } 