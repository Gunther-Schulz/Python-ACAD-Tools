from typing import List, Tuple, Optional, Union, Dict, Any
import numpy as np
from shapely.geometry import (
    LineString, Point, Polygon, MultiPolygon, 
    MultiLineString, GeometryCollection
)
from shapely.ops import unary_union, split
from shapely.affinity import scale, rotate, translate
import math

def buffer_geometry(geom: Union[LineString, Point, Polygon],
                   distance: float,
                   resolution: int = 16,
                   cap_style: int = 1,
                   join_style: int = 1,
                   mitre_limit: float = 5.0) -> Union[Polygon, MultiPolygon]:
    """Create a buffer around a geometry.
    
    Args:
        geom: Input geometry
        distance: Buffer distance
        resolution: Number of segments to approximate curves
        cap_style: End cap style (1=round, 2=flat, 3=square)
        join_style: Join style (1=round, 2=mitre, 3=bevel)
        mitre_limit: Limit for mitre join style
        
    Returns:
        Buffered geometry
    """
    return geom.buffer(
        distance,
        resolution=resolution,
        cap_style=cap_style,
        join_style=join_style,
        mitre_limit=mitre_limit
    )

def smooth_geometry(geom: Union[LineString, Polygon],
                   smoothing: float = 0.5,
                   preserve_topology: bool = True) -> Union[LineString, Polygon]:
    """Smooth a geometry using Chaikin's algorithm.
    
    Args:
        geom: Input geometry
        smoothing: Smoothing factor (0-1)
        preserve_topology: Whether to preserve topology
        
    Returns:
        Smoothed geometry
    """
    if isinstance(geom, LineString):
        return _smooth_linestring(geom, smoothing)
    elif isinstance(geom, Polygon):
        return _smooth_polygon(geom, smoothing, preserve_topology)
    else:
        raise ValueError(f"Unsupported geometry type: {type(geom)}")

def _smooth_linestring(line: LineString, smoothing: float) -> LineString:
    """Smooth a linestring using Chaikin's algorithm.
    
    Args:
        line: Input linestring
        smoothing: Smoothing factor (0-1)
        
    Returns:
        Smoothed linestring
    """
    coords = list(line.coords)
    if len(coords) < 3:
        return line
        
    smooth_coords = []
    smooth_coords.append(coords[0])  # Keep first point
    
    for i in range(len(coords) - 2):
        p0 = coords[i]
        p1 = coords[i + 1]
        p2 = coords[i + 2]
        
        # Calculate new points
        q1 = (
            p0[0] + (p1[0] - p0[0]) * smoothing,
            p0[1] + (p1[1] - p0[1]) * smoothing
        )
        q2 = (
            p1[0] + (p2[0] - p1[0]) * (1 - smoothing),
            p1[1] + (p2[1] - p1[1]) * (1 - smoothing)
        )
        
        smooth_coords.extend([q1, q2])
    
    smooth_coords.append(coords[-1])  # Keep last point
    return LineString(smooth_coords)

def _smooth_polygon(poly: Polygon, smoothing: float, preserve_topology: bool) -> Polygon:
    """Smooth a polygon using Chaikin's algorithm.
    
    Args:
        poly: Input polygon
        smoothing: Smoothing factor (0-1)
        preserve_topology: Whether to preserve topology
        
    Returns:
        Smoothed polygon
    """
    # Smooth exterior ring
    exterior = _smooth_linestring(LineString(poly.exterior.coords), smoothing)
    
    # Smooth interior rings
    interiors = []
    for interior in poly.interiors:
        smooth_interior = _smooth_linestring(LineString(interior.coords), smoothing)
        interiors.append(smooth_interior)
    
    # Create new polygon
    if preserve_topology:
        # Ensure the smoothed polygon doesn't self-intersect
        exterior = _fix_self_intersections(exterior)
        interiors = [_fix_self_intersections(i) for i in interiors]
    
    return Polygon(exterior.coords, [i.coords for i in interiors])

def _fix_self_intersections(line: LineString) -> LineString:
    """Fix self-intersections in a linestring.
    
    Args:
        line: Input linestring
        
    Returns:
        Fixed linestring
    """
    if not line.is_simple:
        # Convert to polygon and back to remove self-intersections
        poly = Polygon(line.coords)
        if poly.is_valid:
            return LineString(poly.exterior.coords)
    return line

def offset_geometry(geom: Union[LineString, Polygon],
                   distance: float,
                   side: str = 'both',
                   resolution: int = 16,
                   join_style: int = 1,
                   mitre_limit: float = 5.0) -> Union[LineString, MultiLineString, Polygon, MultiPolygon]:
    """Create offset geometry.
    
    Args:
        geom: Input geometry
        distance: Offset distance
        side: Offset side ('left', 'right', or 'both')
        resolution: Number of segments to approximate curves
        join_style: Join style (1=round, 2=mitre, 3=bevel)
        mitre_limit: Limit for mitre join style
        
    Returns:
        Offset geometry
    """
    if side.lower() == 'both':
        left = geom.parallel_offset(
            distance, 'left',
            resolution=resolution,
            join_style=join_style,
            mitre_limit=mitre_limit
        )
        right = geom.parallel_offset(
            distance, 'right',
            resolution=resolution,
            join_style=join_style,
            mitre_limit=mitre_limit
        )
        return unary_union([left, right])
    else:
        return geom.parallel_offset(
            distance, side.lower(),
            resolution=resolution,
            join_style=join_style,
            mitre_limit=mitre_limit
        )

def simplify_geometry(geom: Union[LineString, Polygon],
                     tolerance: float,
                     preserve_topology: bool = True) -> Union[LineString, Polygon]:
    """Simplify a geometry using Douglas-Peucker algorithm.
    
    Args:
        geom: Input geometry
        tolerance: Simplification tolerance
        preserve_topology: Whether to preserve topology
        
    Returns:
        Simplified geometry
    """
    return geom.simplify(tolerance, preserve_topology=preserve_topology)

def get_geometry_bounds(geom: Union[LineString, Point, Polygon]) -> Tuple[float, float, float, float]:
    """Get the bounding box of a geometry.
    
    Args:
        geom: Input geometry
        
    Returns:
        Tuple of (minx, miny, maxx, maxy)
    """
    return geom.bounds

def transform_geometry(geom: Union[LineString, Point, Polygon],
                      translation: Optional[Tuple[float, float]] = None,
                      rotation: Optional[float] = None,
                      scale_factors: Optional[Tuple[float, float]] = None,
                      origin: Union[str, Tuple[float, float]] = 'center') -> Union[LineString, Point, Polygon]:
    """Apply transformations to a geometry.
    
    Args:
        geom: Input geometry
        translation: (dx, dy) translation
        rotation: Rotation angle in degrees
        scale_factors: (x_factor, y_factor) scaling
        origin: Origin point for rotation/scaling
        
    Returns:
        Transformed geometry
    """
    result = geom
    
    if scale_factors:
        result = scale(result, scale_factors[0], scale_factors[1], origin=origin)
    
    if rotation:
        result = rotate(result, rotation, origin=origin)
    
    if translation:
        result = translate(result, translation[0], translation[1])
    
    return result 