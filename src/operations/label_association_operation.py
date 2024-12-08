from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np
from shapely.prepared import prep

def safe_distance(geom1, geom2):
    """Calculate distance between geometries with error handling."""
    try:
        if not (geom1.is_valid and geom2.is_valid):
            return float('inf')
        if geom1.is_empty or geom2.is_empty:
            return float('inf')
        dist = geom1.distance(geom2)
        return dist if not np.isnan(dist) else float('inf')
    except Exception:
        return float('inf')

def create_label_points_for_line(line, label_text, label_spacing=None, offset=0):
    """Create points along a line for label placement with optional spacing and offset."""
    if label_spacing is None:
        # If no spacing specified, just use the midpoint
        point = line.interpolate(0.5, normalized=True)
        mid_distance = line.length / 2
        p1 = line.interpolate(mid_distance - 0.1)
        p2 = line.interpolate(mid_distance + 0.1)
        angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        
        # Apply offset perpendicular to line direction
        if offset != 0:
            dx = -(p2.y - p1.y) * offset / math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
            dy = (p2.x - p1.x) * offset / math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
            point = Point(point.x + dx, point.y + dy)
            
        return [(point, label_text, angle)]
    
    # Calculate points along the line at specified intervals
    length = line.length
    current_distance = 0
    points = []
    
    while current_distance <= length:
        point = line.interpolate(current_distance)
        
        # Calculate angle at this point by looking slightly ahead and behind
        look_distance = min(0.1, label_spacing / 10)  # Use smaller of 0.1 or 1/10th of spacing
        p1 = line.interpolate(max(0, current_distance - look_distance))
        p2 = line.interpolate(min(length, current_distance + look_distance))
        
        # Calculate angle based on the local line direction
        angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        
        # Apply offset perpendicular to line direction
        if offset != 0:
            dx = -(p2.y - p1.y) * offset / math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
            dy = (p2.x - p1.x) * offset / math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
            point = Point(point.x + dx, point.y + dy)
        
        # Adjust angle if it's upside down (keep text readable)
        if angle < -90 or angle > 90:
            angle += 180
            if angle > 180:
                angle -= 360
        
        points.append((point, label_text, angle))
        current_distance += label_spacing
    
    return points

def create_point_label(point, label_text, offset=0):
    """Create a label point for a point geometry with offset."""
    if offset == 0:
        return (point, label_text, 0)
    
    # Place label to the right of the point by default
    new_point = Point(point.x + offset, point.y)
    return (new_point, label_text, 0)

def create_polygon_label(polygon, label_text, offset=0):
    """Create a label point for a polygon geometry with offset."""
    # Get the base point inside the polygon
    point = polygon.representative_point()
    
    if offset == 0:
        return (point, label_text, 0)
    
    # If offset is requested, move the point in the direction of the polygon's center
    centroid = polygon.centroid
    if point.equals(centroid):
        # If representative point is at centroid, offset to the right
        return (Point(point.x + offset, point.y), label_text, 0)
    
    # Calculate direction vector from centroid to representative point
    dx = point.x - centroid.x
    dy = point.y - centroid.y
    distance = math.sqrt(dx*dx + dy*dy)
    
    # Normalize and apply offset
    if distance > 0:
        dx = dx/distance * offset
        dy = dy/distance * offset
        new_point = Point(point.x + dx, point.y + dy)
        # Check if new point is still inside polygon
        if not polygon.contains(new_point):
            return (point, label_text, 0)
        return (new_point, label_text, 0)
    
    return (point, label_text, 0)

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Associates labels from a point layer with geometries from another layer."""
    log_debug(f"Creating label association layer: {layer_name}")
    
    # Get operation parameters
    source_layers = operation.get('layers', [layer_name])
    label_layer_name = operation.get('labelLayer')
    label_column = operation.get('labelColumn', 'label')
    label_spacing = operation.get('labelSpacing')  # For line labels
    label_offset = operation.get('labelOffset', 0)  # New offset parameter
    
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
    
    # Create a GeoDataFrame to store label points
    label_points = []
    
    # Process each source layer
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue
            
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if source_geometry is None:
            continue
            
        # Process each geometry in the source layer
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
                if not isinstance(label_point, Point) or not label_point.is_valid or label_point.is_empty:
                    continue
                    
                dist = safe_distance(geometry, label_point)
                if dist < min_dist:
                    min_dist = dist
                    closest_label = (label_row[label_column], label_point)
            
            if closest_label is None:
                continue
                
            label_text, label_point = closest_label
            
            # Create label points based on geometry type
            if isinstance(geometry, LineString) and label_spacing is not None:
                new_points = create_label_points_for_line(geometry, label_text, label_spacing, label_offset)
                label_points.extend(new_points)
            elif isinstance(geometry, Polygon):
                label_points.append(create_polygon_label(geometry, label_text, label_offset))
            elif isinstance(geometry, Point):
                label_points.append(create_point_label(geometry, label_text, label_offset))
            else:
                point = geometry.interpolate(0.5, normalized=True)
                label_points.append((point, label_text, 0))
    
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