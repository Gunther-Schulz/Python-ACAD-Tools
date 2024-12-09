from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np
from src.style_manager import StyleManager

def get_line_placement_positions(line, label_length, text_height=2.5):
    """Get possible label positions along a line with improved corner handling."""
    line_length = line.length
    
    # Calculate step size based on text height
    step = max(text_height, line_length / 20)  # Use text height as minimum step
    
    # Calculate actual space needed for text
    # Typical width-to-height ratio is around 0.6 for most fonts
    # Add some padding (1.2) to ensure text doesn't crowd corners
    text_width = label_length * text_height * 0.6 * 1.2
    
    positions = []
    current_dist = text_width / 2  # Start half text width from the start
    
    while current_dist <= (line_length - text_width / 2):  # Stop half text width from the end
        point = line.interpolate(current_dist)
        
        # Look both ahead and behind to detect corners
        look_dist = max(text_width / 2, step)  # Use half text width as minimum look distance
        behind_dist = max(0, current_dist - look_dist)
        ahead_dist = min(line_length, current_dist + look_dist)
        
        point_behind = line.interpolate(behind_dist)
        point_ahead = line.interpolate(ahead_dist)
        
        # Calculate angles between segments
        angle_diff = 0  # Default to 0 for start/end points
        if behind_dist < current_dist and ahead_dist > current_dist:
            angle1 = math.atan2(point.y - point_behind.y, point.x - point_behind.x)
            angle2 = math.atan2(point_ahead.y - point.y, point_ahead.x - point.x)
            angle_diff = abs(math.degrees(angle2 - angle1))
            
            # Skip corners (where angle difference is significant)
            if angle_diff > 30:  # Adjust this threshold as needed
                current_dist += step
                continue
        
        # Use the ahead point for angle calculation
        angle = math.degrees(math.atan2(
            point_ahead.y - point.y,
            point_ahead.x - point.x
        ))
        
        # Check if we have enough straight space for the label
        space_ahead = line_length - current_dist
        if space_ahead >= text_width / 2:  # Only need half text width ahead since we're centered
            # Calculate a score for this position
            score = 1.0
            if angle_diff < 10:  # Very straight
                score += 2.0
            elif angle_diff < 20:  # Mostly straight
                score += 1.0
            
            # Prefer middle sections of the line
            relative_pos = current_dist / line_length
            if 0.3 <= relative_pos <= 0.7:
                score += 1.0
                
            positions.append((point, angle, score))
        
        current_dist += step
    
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

def get_best_label_position(geometry, label_text, offset=0, text_height=2.5):
    """Find best label position using improved corner handling."""
    if isinstance(geometry, Point):
        if offset == 0:
            return (geometry, label_text, 0)
        return (Point(geometry.x + offset, geometry.y), label_text, 0)
    
    elif isinstance(geometry, LineString):
        # Adjust label length based on text height and character count
        # This is an approximation - adjust multiplier as needed for your font
        label_length = len(label_text) * text_height * 0.8  # 0.8 is character width to height ratio
        positions = get_line_placement_positions(geometry, label_length)
        
        if not positions:
            # Fallback to midpoint if no good positions found
            point = geometry.interpolate(0.5, normalized=True)
            p1 = geometry.interpolate(0.45, normalized=True)
            p2 = geometry.interpolate(0.55, normalized=True)
            angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        else:
            # Use the position with the highest score
            point, angle, _ = max(positions, key=lambda x: x[2])
        
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
    static_label = operation.get('label')
    
    # Only get label layer info if we're not using a static label
    if static_label is None:
        label_layer_name = operation.get('labelLayer', layer_name)
        label_column = operation.get('labelColumn', 'label')
        
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
    
    label_offset = operation.get('labelOffset', 0)
    
    # Get label spacing parameter (1.0 means space between labels equals label width)
    label_spacing = operation.get('labelSpacing', 1.0)
    log_debug(f"Label spacing from config: {label_spacing}")
    
    # Get style information using StyleManager
    style_manager = StyleManager(project_settings)
    layer_info = next((layer for layer in project_settings.get('geomLayers', []) 
                      if layer.get('name') == layer_name), {})
    style = style_manager.process_layer_style(layer_name, layer_info)
    text_style = style.get('text', {}).copy()  # Make a copy of text style
    text_height = text_style.get('height', 2.5)  # Default text height if not specified
    
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
            if static_label is not None:
                label_text = static_label
            else:
                # Find closest label point (existing logic)
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
            
            result = get_best_label_position(geometry, label_text, label_offset, text_height)
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
    
    # Store the text style in the GeoDataFrame's metadata
    # This will be used by dxf_exporter.py when creating the MTEXT entities
    result_gdf.attrs['text_style'] = text_style
    
    log_debug(f"Created label association layer with {len(result_gdf)} label points")
    return result_gdf