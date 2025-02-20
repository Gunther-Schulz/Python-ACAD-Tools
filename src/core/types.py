"""Core type definitions for the project."""

from typing import Dict, Any, Optional, List, Union, Protocol, runtime_checkable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from shapely.geometry import base

class GeometryType(Enum):
    """Types of geometry that can be processed."""
    POINT = "point"
    LINESTRING = "linestring"
    POLYGON = "polygon"
    MULTIPOINT = "multipoint"
    MULTILINESTRING = "multilinestring"
    MULTIPOLYGON = "multipolygon"
    GEOMETRYCOLLECTION = "geometrycollection"

def _validate_float(value: Any) -> float:
    """Validate and convert value to float."""
    if not isinstance(value, (int, float)):
        raise TypeError(f"Expected float, got {type(value)}")
    return float(value)

def _validate_str(value: Any) -> str:
    """Validate and convert value to string."""
    if not isinstance(value, str):
        raise TypeError(f"Expected string, got {type(value)}")
    return value

def _validate_dict(value: Any) -> Dict[str, Any]:
    """Validate dictionary."""
    if not isinstance(value, dict):
        raise TypeError(f"Expected dictionary, got {type(value)}")
    return value

@dataclass
class Bounds:
    """Bounding box coordinates."""
    _minx: float = field(init=False, repr=False)
    _miny: float = field(init=False, repr=False)
    _maxx: float = field(init=False, repr=False)
    _maxy: float = field(init=False, repr=False)
    
    def __init__(self, minx: Any, miny: Any, maxx: Any, maxy: Any):
        """Initialize with type validation."""
        self._minx = _validate_float(minx)
        self._miny = _validate_float(miny)
        self._maxx = _validate_float(maxx)
        self._maxy = _validate_float(maxy)
    
    @property
    def minx(self) -> float:
        return self._minx
        
    @property
    def miny(self) -> float:
        return self._miny
        
    @property
    def maxx(self) -> float:
        return self._maxx
        
    @property
    def maxy(self) -> float:
        return self._maxy

@dataclass
class GeometryAttributes:
    """Attributes associated with a geometry."""
    _id: str = field(init=False, repr=False)
    _properties: Dict[str, Any] = field(init=False, repr=False)
    _bounds: Optional[Bounds] = field(init=False, repr=False, default=None)
    
    def __init__(self, id: Any, properties: Any, bounds: Optional[Bounds] = None):
        """Initialize with type validation."""
        self._id = _validate_str(id)
        self._properties = _validate_dict(properties)
        if bounds is not None and not isinstance(bounds, Bounds):
            raise TypeError(f"Expected Bounds or None, got {type(bounds)}")
        self._bounds = bounds
    
    @property
    def id(self) -> str:
        return self._id
        
    @property
    def properties(self) -> Dict[str, Any]:
        return self._properties
        
    @property
    def bounds(self) -> Optional[Bounds]:
        return self._bounds

# New interface protocols
@runtime_checkable
class Geometry(Protocol):
    """Interface for geometry objects."""
    def get_bounds(self) -> tuple[float, float, float, float]: ...
    def get_coordinates(self) -> List[tuple[float, float]]: ...

@runtime_checkable
class GeometrySource(Protocol):
    """Interface for geometry data sources."""
    def read(self) -> 'GeometryData': ...
    def get_metadata(self) -> Dict[str, Any]: ...

@runtime_checkable
class GeometryOperation(Protocol):
    """Interface for geometry operations."""
    def execute(self, geom: Geometry) -> Geometry: ...

@runtime_checkable
class GeometryExporter(Protocol):
    """Interface for geometry exporters."""
    def export(self, geom: 'ProcessedGeometry', export_data: 'ExportData') -> None: ...

# Data transfer objects
@dataclass
class GeometryData:
    """Data transfer object for geometry data."""
    id: str
    geom: Geometry
    metadata: Dict[str, Any]
    source_type: str  # e.g., 'shapefile', 'manual', etc.
    source_crs: str   # Coordinate reference system of source

@dataclass
class ProcessedGeometry:
    """Result of geometry processing."""
    data: GeometryData
    processing_log: List[str]

@dataclass
class ExportData:
    """Export configuration data."""
    id: str
    format_type: str  # 'dxf' or 'shapefile'
    style_id: Optional[str]  # Required for DXF, optional for shapefile
    layer_name: str
    target_crs: Optional[str]  # Required for shapefile
    properties: Dict[str, Any]

# Type aliases for clarity
StyleName = str
LayerName = str
OperationName = str

# Common types used across the project
JsonDict = Dict[str, Any]
PathLike = Union[str, bytes, Path] 