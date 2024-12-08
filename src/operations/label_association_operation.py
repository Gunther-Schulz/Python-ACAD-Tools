from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np
from src.style_manager import StyleManager

def get_line_placement_positions(line, label_length, text_height=2.5, label_spacing=1.0):
    """Calculate label positions along a line with controlled spacing between labels."""
    log_debug(f"get_line_placement_positions called with label_spacing: {label_spacing}")
    
    line_length = line.length
    text_width = label_length * text_height * 0.6
    step = text_width * (1 + label_spacing)  # Space between labels
    
    log_debug(f"Spacing calculation details:")
    log_debug(f"  text_width: {text_width}")
    log_debug(f"  label_spacing: {label_spacing}")
    log_debug(f"  step size: {step}")
    
    positions = []
    current_dist = text_width/2
    
    while current_dist <= (line_length - text_width/2):
        point = line.interpolate(current_dist)
        
        # Look ahead and behind to detect corners
        look_dist = text_width/4
        behind_dist = max(0, current_dist - look_dist)
        ahead_dist = min(line_length, current_dist + look_dist)
        
        point_behind = line.interpolate(behind_dist)
        point_ahead = line.interpolate(ahead_dist)
        
        # Calculate angle for this segment
        angle = math.degrees(math.atan2(
            point_ahead.y - point.y,
            point_ahead.x - point.x
        ))
        
        # Calculate angles between segments
        angle_diff = 0
        if behind_dist < current_dist and ahead_dist > current_dist:
            angle1 = math.atan2(point.y - point_behind.y, point.x - point_behind.x)
            angle2 = math.atan2(point_ahead.y - point.y, point_ahead.x - point.x)
            angle_diff = abs(math.degrees(angle2 - angle1))
        
        # Skip corners
        if angle_diff > 30:
            current_dist += step/2  # Skip shorter distance at corners
            continue
            
        # Score this position
        score = 1.0
        if angle_diff < 10:
            score += 2.0
        elif angle_diff < 20:
            score += 1.0
            
        # Prefer middle sections
        relative_pos = current_dist / line_length
        if 0.3 <= relative_pos <= 0.7:
            score += 1.0
            
        positions.append((point, angle, score))
        current_dist += step  # Move to next position using label spacing
    
    return positions

def get_polygon_anchor_position(polygon, text_width, text_height):
    """Get the best anchor position for a polygon using Mapbox's approach."""
    # Try multiple candidate positions and score them
    candidates = []
    
    # 1. Try centroid
    centroid = polygon.centroid
    if polygon.contains(centroid):
        score = 1.0
        # Bonus for being far from edges
        min_dist_to_boundary = polygon.boundary.distance(centroid)
        score += min_dist_to_boundary / (text_width * 0.5)  # Scale by text size
        candidates.append((centroid, score))
    
    # 2. Try pole of inaccessibility (point furthest from boundary)
    try:
        from shapely.ops import polylabel
        pole = polylabel(polygon, tolerance=text_height/10)
        if polygon.contains(pole):
            score = 1.5  # Higher base score than centroid
            min_dist_to_boundary = polygon.boundary.distance(pole)
            score += min_dist_to_boundary / (text_width * 0.5)
            candidates.append((pole, score))
    except Exception:
        pass
    
    # 3. Try representative point as fallback
    rep_point = polygon.representative_point()
    if polygon.contains(rep_point):
        score = 0.5  # Lower base score
        min_dist_to_boundary = polygon.boundary.distance(rep_point)
        score += min_dist_to_boundary / (text_width * 0.5)
        candidates.append((rep_point, score))
    
    # 4. Try points along major axis using oriented envelope
    try:
        # Get oriented envelope (minimum rotated rectangle)
        mbr = polygon.minimum_rotated_rectangle  # New Shapely way
        if mbr is None:  # Fallback for older Shapely versions
            mbr = polygon.envelope
            
        coords = list(mbr.exterior.coords)
        
        # Calculate lengths of rectangle sides
        side1 = LineString([coords[0], coords[1]])
        side2 = LineString([coords[1], coords[2]])
        
        # Determine major axis
        if side1.length > side2.length:
            major_axis = [coords[0], coords[1]]
        else:
            major_axis = [coords[1], coords[2]]
        
        # Try points along major axis
        for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
            x = major_axis[0][0] + t * (major_axis[1][0] - major_axis[0][0])
            y = major_axis[0][1] + t * (major_axis[1][1] - major_axis[0][1])
            point = Point(x, y)
            if polygon.contains(point):
                score = 0.8  # Medium base score
                min_dist_to_boundary = polygon.boundary.distance(point)
                score += min_dist_to_boundary / (text_width * 0.5)
                candidates.append((point, score))
    except Exception as e:
        log_debug(f"Error calculating major axis points: {str(e)}")
        pass
    
    if not candidates:
        # Ultimate fallback: use centroid regardless of containment
        return polygon.centroid
    
    # Return the position with highest score
    return max(candidates, key=lambda x: x[1])[0]

def get_point_label_position(point, label_text, text_height, offset=0):
    """Get best label position for a point using Mapbox's approach."""
    # Try multiple positions around the point
    candidates = []
    
    # Calculate text dimensions
    text_width = len(label_text) * text_height * 0.6
    
    # Define possible positions (clockwise from right)
    angles = [0, 45, 90, 135, 180, 225, 270, 315]
    base_offsets = [
        (1, 0),    # Right
        (1, 1),    # Top-right
        (0, 1),    # Top
        (-1, 1),   # Top-left
        (-1, 0),   # Left
        (-1, -1),  # Bottom-left
        (0, -1),   # Bottom
        (1, -1),   # Bottom-right
    ]
    
    # Default offset distance based on text height if not specified
    if offset == 0:
        offset = text_height * 0.5
    
    for angle, (dx, dy) in zip(angles, base_offsets):
        # Calculate position
        x = point.x + dx * offset
        y = point.y + dy * offset
        candidate = Point(x, y)
        
        # Score based on position (prefer right side, then top, etc.)
        score = 1.0
        if dx > 0:  # Right side
            score += 0.5
        if dy > 0:  # Top half
            score += 0.3
            
        candidates.append((candidate, angle, score))
    
    # Return the position with highest score
    best_candidate = max(candidates, key=lambda x: x[2])
    return (best_candidate[0], best_candidate[1])

def get_best_label_position(geometry, label_text, offset=0, text_height=2.5, label_spacing=1.0):
    """Find best label position using improved corner handling."""
    if isinstance(geometry, LineString):
        label_length = len(label_text) * text_height * 0.8
        positions = get_line_placement_positions(
            geometry, 
            label_length, 
            text_height=text_height,
            label_spacing=label_spacing
        )
        
        if not positions:
            # Fallback to midpoint
            point = geometry.interpolate(0.5, normalized=True)
            p1 = geometry.interpolate(0.45, normalized=True)
            p2 = geometry.interpolate(0.55, normalized=True)
            angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
            return [(point, label_text, angle)]  # Return as list for consistency
        
        # Return ALL positions, not just the best one
        result_positions = []
        for point, angle, score in positions:
            # Apply offset if needed
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
                
            result_positions.append((point, label_text, angle))
            
        return result_positions
    
    # For Point and Polygon, return single position as list
    elif isinstance(geometry, Point):
        # ... existing Point code ...
        return [(point, label_text, 0)]
    
    elif isinstance(geometry, Polygon):
        # ... existing Polygon code ...
        return [(point, label_text, 0)]
    
    return None

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Associates labels from a point layer with geometries from another layer."""
    log_debug(f"Creating label association layer: {layer_name}")
    
    # Get operation parameters
    source_layers = operation.get('layers', [layer_name])
    label_layer_name = operation.get('labelLayer')
    label_column = operation.get('labelColumn', 'label')
    label_offset = operation.get('labelOffset', 0)
    
    # Get label spacing parameter (1.0 means space between labels equals label width)
    label_spacing = operation.get('labelSpacing', 1.0)
    log_debug(f"Label spacing from config: {label_spacing}")
    
    # Get style information using StyleManager
    style_manager = StyleManager(project_settings)
    layer_info = next((layer for layer in project_settings.get('geomLayers', []) 
                      if layer.get('name') == layer_name), {})
    style = style_manager.process_layer_style(layer_name, layer_info)
    text_height = style.get('text', {}).get('height', 2.5)  # Default text height if not specified
    
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
            
            # Get best position(s) for this label
            results = get_best_label_position(
                geometry, 
                label_text, 
                label_offset, 
                text_height, 
                label_spacing=label_spacing
            )
            
            if results:
                label_points.extend(results)  # Add all positions for line labels
    
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