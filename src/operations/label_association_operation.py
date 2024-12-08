from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np

def get_line_placement_positions(line, label_length):
    """Get possible label positions along a line using Mapbox's approach."""
    # Sample points along the line at regular intervals
    line_length = line.length
    step = line_length / 20  # Sample 20 points along the line
    positions = []
    
    current_dist = 0
    while current_dist <= line_length:
        point = line.interpolate(current_dist)
        # Look ahead to get angle
        next_dist = min(current_dist + step, line_length)
        next_point = line.interpolate(next_dist)
        
        angle = math.degrees(math.atan2(
            next_point.y - point.y,
            next_point.x - point.x
        ))
        
        # Check if we have enough space for the label
        space_ahead = line_length - current_dist
        if space_ahead >= label_length:
            positions.append((point, angle))
        
        current_dist += step
    
    return positions

def get_polygon_anchor_position(polygon):
    """Get the best anchor position for a polygon using Mapbox's approach."""
    # Try to find a position that's:
    # 1. Inside the polygon
    # 2. Away from edges
    # 3. Centered in the largest inscribed circle
    
    centroid = polygon.centroid
    if polygon.contains(centroid):
        return centroid
    
    # If centroid is outside, use representative point
    return polygon.representative_point()

def get_best_label_position(geometry, label_text, offset=0):
    """Find best label position using Mapbox-style placement strategies."""
    if isinstance(geometry, Point):
        if offset == 0:
            return (geometry, label_text, 0)
        # For points, offset to the right (Mapbox's default)
        return (Point(geometry.x + offset, geometry.y), label_text, 0)
    
    elif isinstance(geometry, LineString):
        # For lines, try to find the longest straight segment that can fit the label
        label_length = len(label_text) * 0.5  # Approximate length needed
        positions = get_line_placement_positions(geometry, label_length)
        
        if not positions:
            # Fallback to midpoint if no good positions found
            point = geometry.interpolate(0.5, normalized=True)
            p1 = geometry.interpolate(0.45, normalized=True)
            p2 = geometry.interpolate(0.55, normalized=True)
            angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        else:
            # Use the middle position from the candidates
            middle_idx = len(positions) // 2
            point, angle = positions[middle_idx]
        
        # Apply offset perpendicular to line direction
        if offset != 0:
            rad_angle = math.radians(angle)
            dx = -math.sin(rad_angle) * offset
            dy = math.cos(rad_angle) * offset
            point = Point(point.x + dx, point.y + dy)
        
        # Adjust angle for readability
        if abs(angle) > 90:
            angle += 180
        if angle > 180:
            angle -= 360
            
        return (point, label_text, angle)
    
    elif isinstance(geometry, Polygon):
        point = get_polygon_anchor_position(geometry)
        
        if offset != 0:
            # Move point away from centroid
            centroid = geometry.centroid
            if not point.equals(centroid):
                dx = point.x - centroid.x
                dy = point.y - centroid.y
                dist = math.sqrt(dx*dx + dy*dy)
                if dist > 0:
                    point = Point(
                        point.x + (dx/dist * offset),
                        point.y + (dy/dist * offset)
                    )
        
        return (point, label_text, 0)
    
    return None

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Associates labels from a point layer with geometries from another layer."""
    log_debug(f"Creating label association layer: {layer_name}")
    
    # Get operation parameters
    source_layers = operation.get('layers', [layer_name])
    label_layer_name = operation.get('labelLayer')
    label_column = operation.get('labelColumn', 'label')
    label_offset = operation.get('labelOffset', 0)
    
    if not label_layer_name:
        log_warning(format_operation_warning(
            layer_name,
            "labelAssociation",
            "Missing required labelLayer parameter"
        ))
        return None
    
    # Get label layer
    label_layer = all_layers.get(label_layer_name)
    if label_layer is None:
        log_warning(format_operation_warning(
            layer_name,
            "labelAssociation",
            f"Label layer '{label_layer_name}' not found"
        ))
        return None
    
    label_points = []
    
    # Process each source layer
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue
        
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if source_geometry is None:
            continue
        
        # Process each geometry
        if isinstance(source_geometry, (Point, LineString, Polygon)):
            geometries = [source_geometry]
        else:
            geometries = list(source_geometry.geoms)
        
        for geometry in geometries:
            # Find closest label point
            min_dist = float('inf')
            closest_label = None
            
            for idx, label_row in label_layer.iterrows():
                if label_column not in label_row:
                    continue
                
                label_point = label_row.geometry
                dist = geometry.distance(label_point)
                if dist < min_dist:
                    min_dist = dist
                    closest_label = (label_row[label_column], label_point)
            
            if closest_label is None:
                continue
            
            label_text, _ = closest_label
            
            # Get best position for this label
            result = get_best_label_position(geometry, label_text, label_offset)
            if result:
                label_points.append(result)
    
    # Create result GeoDataFrame
    if not label_points:
        return None
    
    result_data = {
        'geometry': [p[0] for p in label_points],
        'label': [p[1] for p in label_points],
        'rotation': [p[2] for p in label_points]
    }
    
    result_gdf = gpd.GeoDataFrame(result_data, crs=crs)
    log_debug(f"Created label association layer with {len(result_gdf)} label points")
    return result_gdf