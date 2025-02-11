from typing import List, Tuple, Optional, Union, Dict, Any
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import transform
from shapely.affinity import rotate, translate
import math

def create_path_array(base_path: LineString, 
                     spacing: float,
                     count: int,
                     offset_direction: str = 'right',
                     start_offset: float = 0.0,
                     end_offset: float = 0.0) -> List[LineString]:
    """Create an array of parallel paths from a base path.
    
    Args:
        base_path: Base path to create array from
        spacing: Spacing between paths
        count: Number of paths to create
        offset_direction: Direction to offset ('left' or 'right')
        start_offset: Offset at start of path
        end_offset: Offset at end of path
        
    Returns:
        List of parallel paths
    """
    paths = []
    direction = 1 if offset_direction.lower() == 'right' else -1
    
    for i in range(count):
        offset = i * spacing * direction
        if offset == 0:
            paths.append(base_path)
            continue
            
        # Create offset path
        offset_path = _create_offset_path(base_path, offset, start_offset, end_offset)
        paths.append(offset_path)
    
    return paths

def _create_offset_path(base_path: LineString, 
                       offset: float,
                       start_offset: float = 0.0,
                       end_offset: float = 0.0) -> LineString:
    """Create a single offset path with optional start/end offsets.
    
    Args:
        base_path: Base path to offset
        offset: Distance to offset
        start_offset: Offset at start of path
        end_offset: Offset at end of path
        
    Returns:
        Offset path
    """
    coords = list(base_path.coords)
    if len(coords) < 2:
        return base_path
        
    # Calculate perpendicular vectors for each segment
    segments = []
    perp_vectors = []
    
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        
        # Calculate segment vector and perpendicular
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.sqrt(dx*dx + dy*dy)
        
        if length > 0:
            # Normalize and get perpendicular
            dx, dy = dx/length, dy/length
            perp_x, perp_y = -dy, dx
            segments.append((p1, p2))
            perp_vectors.append((perp_x, perp_y))
    
    # Create offset points with interpolated offsets
    new_coords = []
    
    for i in range(len(coords)):
        if i == 0:  # Start point
            perp = perp_vectors[0]
            offset_dist = offset + start_offset
        elif i == len(coords) - 1:  # End point
            perp = perp_vectors[-1]
            offset_dist = offset + end_offset
        else:  # Middle points - average perpendiculars
            perp1 = perp_vectors[i-1]
            perp2 = perp_vectors[i]
            perp = (
                (perp1[0] + perp2[0])/2,
                (perp1[1] + perp2[1])/2
            )
            # Normalize the averaged vector
            length = math.sqrt(perp[0]*perp[0] + perp[1]*perp[1])
            if length > 0:
                perp = (perp[0]/length, perp[1]/length)
            offset_dist = offset
        
        # Create offset point
        new_x = coords[i][0] + perp[0] * offset_dist
        new_y = coords[i][1] + perp[1] * offset_dist
        new_coords.append((new_x, new_y))
    
    return LineString(new_coords)

def create_path_array_along_curve(base_path: LineString,
                                guide_curve: LineString,
                                count: int,
                                spacing: float,
                                interpolate: bool = True) -> List[LineString]:
    """Create an array of paths that follow a guide curve.
    
    Args:
        base_path: Base path to array
        guide_curve: Curve to follow
        count: Number of paths to create
        spacing: Spacing between paths
        interpolate: Whether to interpolate path shape between base and guide
        
    Returns:
        List of paths following the guide curve
    """
    paths = []
    
    # Get base path properties
    base_start = Point(base_path.coords[0])
    base_end = Point(base_path.coords[-1])
    base_vector = (base_end.x - base_start.x, base_end.y - base_start.y)
    base_length = math.sqrt(base_vector[0]**2 + base_vector[1]**2)
    
    for i in range(count):
        if i == 0:
            paths.append(base_path)
            continue
            
        # Calculate position along guide curve
        distance = i * spacing
        if distance >= guide_curve.length:
            break
            
        # Get point and direction on guide curve
        point = guide_curve.interpolate(distance)
        direction = _get_direction_at_point(guide_curve, distance)
        
        if interpolate:
            # Create interpolated path
            t = distance / guide_curve.length
            path = _interpolate_path(base_path, point, direction, t)
        else:
            # Transform base path to new position
            path = _transform_path(base_path, point, direction)
            
        paths.append(path)
    
    return paths

def _get_direction_at_point(curve: LineString, distance: float) -> float:
    """Get the direction angle at a point along a curve.
    
    Args:
        curve: Curve to get direction from
        distance: Distance along curve
        
    Returns:
        Direction angle in radians
    """
    # Get points before and after the target point
    point = curve.interpolate(distance)
    before = curve.interpolate(max(0, distance - 0.1))
    after = curve.interpolate(min(curve.length, distance + 0.1))
    
    # Calculate direction vector
    dx = after.x - before.x
    dy = after.y - before.y
    
    return math.atan2(dy, dx)

def _interpolate_path(base_path: LineString,
                     target_point: Point,
                     target_angle: float,
                     t: float) -> LineString:
    """Interpolate a path between its base position and a target.
    
    Args:
        base_path: Path to interpolate
        target_point: Target position
        target_angle: Target angle
        t: Interpolation factor (0-1)
        
    Returns:
        Interpolated path
    """
    # Get base path properties
    base_start = Point(base_path.coords[0])
    base_angle = math.atan2(
        base_path.coords[-1][1] - base_start.y,
        base_path.coords[-1][0] - base_start.x
    )
    
    # Interpolate position and angle
    dx = target_point.x - base_start.x
    dy = target_point.y - base_start.y
    angle_diff = (target_angle - base_angle + math.pi) % (2*math.pi) - math.pi
    
    # Create transformed path
    path = translate(base_path, dx*t, dy*t)
    path = rotate(path, angle_diff*t, origin='start')
    
    return path

def _transform_path(path: LineString,
                   target_point: Point,
                   target_angle: float) -> LineString:
    """Transform a path to a new position and orientation.
    
    Args:
        path: Path to transform
        target_point: Target position
        target_angle: Target angle
        
    Returns:
        Transformed path
    """
    # Get base path properties
    base_start = Point(path.coords[0])
    base_angle = math.atan2(
        path.coords[-1][1] - base_start.y,
        path.coords[-1][0] - base_start.x
    )
    
    # Calculate transformation
    dx = target_point.x - base_start.x
    dy = target_point.y - base_start.y
    angle_diff = target_angle - base_angle
    
    # Apply transformation
    new_path = translate(path, dx, dy)
    new_path = rotate(new_path, math.degrees(angle_diff), origin='start')
    
    return new_path 