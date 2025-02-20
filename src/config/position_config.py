"""Position configuration module."""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Position:
    """Configuration for a position."""
    x: float
    y: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create Position from dictionary."""
        return cls(
            x=float(data['x']),
            y=float(data['y'])
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'x': self.x,
            'y': self.y
        } 