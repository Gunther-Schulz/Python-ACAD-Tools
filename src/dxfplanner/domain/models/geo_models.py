from pydantic import BaseModel, Field
from typing import List, Dict, Any, Union, Optional

from .common import Coordinate, BoundingBox # Assuming common.py is in the same directory

# --- Basic Geometric Primitives (can be used as types for GeoFeature.geometry) ---
class PointGeo(BaseModel):
    """Represents a single geographic point."""
    # Could directly use Coordinate type, or embed for specific geo-point properties if any
    # For simplicity, let's assume a GeoFeature with a Point geometry might just store coordinates directly
    # or use this if Point-specific attributes/methods arise beyond just coordinates.
    # This model might be redundant if GeoFeature's geometry for points is just List[float, float]
    # However, having explicit Point/Polyline/Polygon types for GeoFeature.geometry is cleaner.
    type: str = Field("Point", const=True) # GeoJSON-like type discriminator
    coordinates: Coordinate # A single coordinate for a point

class PolylineGeo(BaseModel):
    """Represents a geographic polyline (linestring)."""
    type: str = Field("LineString", const=True)
    coordinates: List[Coordinate] # A list of coordinates forming the line

class PolygonGeo(BaseModel):
    """Represents a geographic polygon."""
    type: str = Field("Polygon", const=True)
    # Exterior ring and optional interior rings (holes)
    # Each ring is a list of coordinates, and the first and last points should be the same.
    coordinates: List[List[Coordinate]]

# --- More Complex Geometries (Optional, depending on data sources) ---
class MultiPointGeo(BaseModel):
    type: str = Field("MultiPoint", const=True)
    coordinates: List[Coordinate]

class MultiPolylineGeo(BaseModel):
    type: str = Field("MultiLineString", const=True)
    coordinates: List[List[Coordinate]]

class MultiPolygonGeo(BaseModel):
    type: str = Field("MultiPolygon", const=True)
    coordinates: List[List[List[Coordinate]]]

class GeometryCollectionGeo(BaseModel):
    type: str = Field("GeometryCollection", const=True)
    geometries: List[Union[PointGeo, PolylineGeo, PolygonGeo, MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo]]

# Union type for any valid GeoJSON-like geometry object
AnyGeoGeometry = Union[
    PointGeo, PolylineGeo, PolygonGeo,
    MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo,
    GeometryCollectionGeo
]

# --- GeoFeature Model ---
class GeoFeature(BaseModel):
    """
    Represents a GeoJSON-like Feature object, containing geometry and properties.
    This will be the primary model for representing features read from geodata sources.
    """
    type: str = Field("Feature", const=True)
    geometry: AnyGeoGeometry # The actual geometry object
    properties: Dict[str, Any] = Field(default_factory=dict) # Attributes of the feature
    id: Optional[Union[str, int]] = None # Optional feature identifier
    bbox: Optional[BoundingBox] = None # Optional bounding box for the feature

    # Example: Convenience property to get a specific attribute
    # def get_attribute(self, key: str, default: Any = None) -> Any:
    #     return self.properties.get(key, default)

# If we need a collection of features (e.g. a FeatureCollection)
class GeoFeatureCollection(BaseModel):
    """
    Represents a GeoJSON-like FeatureCollection.
    """
    type: str = Field("FeatureCollection", const=True)
    features: List[GeoFeature]
    bbox: Optional[BoundingBox] = None # Optional bounding box for the entire collection
    # crs: Optional[Dict[str, Any]] = None # Optional CRS information, though often handled externally
