"""Base geometry types and interfaces."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Protocol
from shapely.geometry import base as shapely_base

@dataclass
class GeometryMetadata:
    """Metadata for geometry objects."""
    source_type: str  # e.g., 'shapefile', 'manual', etc.
    source_crs: Optional[str] = None  # Coordinate reference system
    attributes: Dict[str, Any] = field(default_factory=dict)
    operations_log: List[str] = field(default_factory=list)

@dataclass
class GeometryData:
    """Pure geometry data with metadata."""
    id: str
    geometry: shapely_base.BaseGeometry
    metadata: GeometryMetadata

    def clone(self) -> 'GeometryData':
        """Create a deep copy of the geometry data."""
        from copy import deepcopy
        return GeometryData(
            id=self.id,
            geometry=shapely_base.BaseGeometry(self.geometry),  # Creates new geometry
            metadata=deepcopy(self.metadata)
        )

class GeometryValidator(Protocol):
    """Protocol for geometry validation."""
    def validate(self, geometry: shapely_base.BaseGeometry) -> bool: ...
    def fix(self, geometry: shapely_base.BaseGeometry) -> shapely_base.BaseGeometry: ...
    def get_validation_errors(self) -> List[str]: ...

class GeometryError(Exception):
    """Base class for geometry-related errors."""
    pass

class InvalidGeometryError(GeometryError):
    """Raised when geometry is invalid."""
    pass

class GeometryOperationError(GeometryError):
    """Raised when a geometry operation fails."""
    pass 