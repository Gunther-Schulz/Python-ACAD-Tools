from shapely import MultiLineString
from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np
from src.style_manager import StyleManager
import networkx as nx


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
        
        # Normalize angle to ensure text is never upside down (-90 to 90 degrees)
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        
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

def calculate_label_box(point, width, height, angle, settings=None):
    """Calculate a rotated rectangle representing label bounds."""
    from shapely.affinity import rotate, translate
    
    # Default settings if none provided
    if settings is None:
        settings = {
            'width_factor': 1.3,      # 30% extra width
            'height_factor': 1.5,     # 50% extra height
            'buffer_factor': 0.2,     # 20% text height buffer
        }
    
    # Apply dimension factors
    width *= settings['width_factor']
    height *= settings['height_factor']
    
    # Create basic rectangle
    dx = width / 2
    dy = height / 2
    box = Polygon([
        (-dx, -dy), (dx, -dy),
        (dx, dy), (-dx, dy),
        (-dx, -dy)
    ])
    
    # Rotate and translate to position
    box = rotate(box, angle, origin=(0, 0))
    box = translate(box, point.x, point.y)
    
    # Add padding buffer
    box = box.buffer(height * settings['buffer_factor'])
    
    return box

def check_label_collision(point, label_text, angle, existing_labels, text_height, settings=None):
    """Check if a label position collides with existing labels using rotated boxes."""
    if settings is None:
        settings = {
            'width_factor': 1.3,
            'height_factor': 1.5,
            'buffer_factor': 0.2,
            'collision_margin': 0.25,  # Extra margin for collision detection
        }
    
    # Calculate text dimensions
    text_width = len(label_text) * text_height * 0.6
    
    # Create rotated box for new label
    new_box = calculate_label_box(point, text_width, text_height, angle, settings)
    
    # Add extra buffer for checking
    check_box = new_box.buffer(text_height * settings['collision_margin'])
    
    # Check collision with existing labels
    for existing_label in existing_labels:
        if check_box.intersects(existing_label):
            return True
    return False

def get_best_label_position(geometry, label_text, offset=0, text_height=2.5, existing_labels=None):
    """Find best label position using QGIS labeling engine and collision detection."""
    if existing_labels is None:
        existing_labels = []
    
    if isinstance(geometry, Point):
        if offset == 0:
            return (geometry, label_text, 0)
        return (Point(geometry.x + offset, geometry.y), label_text, 0)
    
    elif isinstance(geometry, LineString):
        # Get all possible positions
        label_length = len(label_text) * text_height * 0.8
        positions = get_line_placement_positions(geometry, label_length, text_height)
        
        # Sort positions by score
        positions.sort(key=lambda x: x[2], reverse=True)
        
        # Try positions until finding one without collision
        for point, angle, score in positions:
            if not check_label_collision(point, label_text, angle, existing_labels, text_height):
                return (point, label_text, angle)
        
        # If all positions collide, return the highest scoring position
        if positions:
            return (positions[0][0], label_text, positions[0][1])
        
        # Fallback to midpoint if no positions found
        point = geometry.interpolate(0.5, normalized=True)
        p1 = geometry.interpolate(0.45, normalized=True)
        p2 = geometry.interpolate(0.55, normalized=True)
        angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        return (point, label_text, angle)
    
    elif isinstance(geometry, Polygon):
        # Get candidate positions
        point = get_polygon_anchor_position(geometry, len(label_text) * text_height * 0.6, text_height)
        
        # Check for collisions and try to adjust if needed
        if check_label_collision(point, label_text, 0, existing_labels, text_height):
            # Try alternative positions within the polygon
            centroid = geometry.centroid
            alternatives = [
                geometry.representative_point(),
                centroid,
                Point(point.x + text_height, point.y),
                Point(point.x - text_height, point.y),
                Point(point.x, point.y + text_height),
                Point(point.x, point.y - text_height)
            ]
            
            for alt_point in alternatives:
                if geometry.contains(alt_point) and not check_label_collision(alt_point, label_text, 0, existing_labels, text_height):
                    point = alt_point
                    break
        
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

def try_resolve_collision(point, angle, existing_labels, text_height, label_text):
    """Try to resolve label collision by moving the label in the optimal direction."""
    # Create rotated box for the new label
    text_width = len(label_text) * text_height * 0.6
    label_box = calculate_label_box(point, text_width, text_height, angle)
    
    # First check if there's a collision
    colliding_labels = [label for label in existing_labels if label.intersects(label_box)]
    
    if not colliding_labels:
        return point, False
    
    # Calculate the main direction of collision
    collision_vectors = []
    for colliding_label in colliding_labels:
        # Get centroid of colliding label
        centroid = colliding_label.centroid
        dx = point.x - centroid.x
        dy = point.y - centroid.y
        collision_vectors.append((dx, dy))
    
    # Calculate average collision vector
    avg_dx = sum(v[0] for v in collision_vectors) / len(collision_vectors)
    avg_dy = sum(v[1] for v in collision_vectors) / len(collision_vectors)
    
    # Determine if collision is more horizontal or vertical
    is_horizontal = abs(avg_dx) > abs(avg_dy)
    
    # Try different offsets based on the collision direction
    offsets = []
    base_offset = text_height * 1.2  # Base offset distance
    
    if is_horizontal:
        # Try horizontal offsets first, then diagonal
        offsets = [
            (math.copysign(base_offset, avg_dx), 0),  # Horizontal
            (math.copysign(base_offset, avg_dx), base_offset/2),  # Diagonal up
            (math.copysign(base_offset, avg_dx), -base_offset/2),  # Diagonal down
        ]
    else:
        # Try vertical offsets first, then diagonal
        offsets = [
            (0, math.copysign(base_offset, avg_dy)),  # Vertical
            (base_offset/2, math.copysign(base_offset, avg_dy)),  # Diagonal right
            (-base_offset/2, math.copysign(base_offset, avg_dy)),  # Diagonal left
        ]
    
    # Try each offset until finding a non-colliding position
    for offset_x, offset_y in offsets:
        new_point = Point(point.x + offset_x, point.y + offset_y)
        new_box = calculate_label_box(new_point, text_width, text_height, angle)
        
        if not any(label.intersects(new_box) for label in existing_labels):
            return new_point, True
    
    # If no resolution found, try larger offsets as last resort
    last_resort_offset = base_offset * 2
    for dx, dy in [(last_resort_offset, 0), (-last_resort_offset, 0), 
                   (0, last_resort_offset), (0, -last_resort_offset)]:
        new_point = Point(point.x + dx, point.y + dy)
        new_box = calculate_label_box(new_point, text_width, text_height, angle)
        
        if not any(label.intersects(new_box) for label in existing_labels):
            return new_point, True
    
    return point, False

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Creates label points along lines using networkx for optimal label placement."""
    
    # Get settings from operation config (keeping existing settings logic)
    label_settings = operation.get('labelSettings', {})
    spacing_settings = {
        'width_factor': label_settings.get('widthFactor', 1.3),
        'height_factor': label_settings.get('heightFactor', 1.5),
        'buffer_factor': label_settings.get('bufferFactor', 0.2),
        'collision_margin': label_settings.get('collisionMargin', 0.25),
    }
    
    global_label_offset = float(label_settings.get('labelOffset', 0))
    
    # Get text style (keeping existing style logic)
    style_manager = StyleManager(project_settings)
    layer_info = next((layer for layer in project_settings.get('geomLayers', []) 
                      if layer.get('name') == layer_name), {})
    style = style_manager.process_layer_style(layer_name, layer_info)
    text_style = style.get('text', {}).copy()
    text_height = text_style.get('height', 2.5)
    
    # Track statistics
    source_layer_counts = {}
    source_layers = operation.get('sourceLayers', [{'name': layer_name}])
    features_list = []
    
    # Create graph for label conflict resolution
    G = nx.Graph()
    
    # Process each source layer
    for source_config in source_layers:
        source_layer_name = source_config.get('name')
        if not source_layer_name:
            continue
            
        label_text = source_config.get('label', '')
        spacing = source_config.get('labelSpacing', 100)
        label_offset = float(source_config.get('labelOffset', global_label_offset))
        
        source_layer_counts[source_layer_name] = 0
        
        # Get source geometry
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, None)
        if source_geometry is None or source_geometry.is_empty:
            continue
        
        # Convert to list of LineStrings
        geometries = [source_geometry] if isinstance(source_geometry, LineString) else list(source_geometry.geoms)
        
        # Generate candidate positions
        candidates = []
        for line in geometries:
            source_layer_counts[source_layer_name] += 1
            
            # Generate evenly spaced candidates along line
            for dist in np.arange(spacing/2, line.length, spacing):
                point = line.interpolate(dist)
                # Calculate angle (similar to existing logic)
                delta = spacing * 0.1
                point_before = line.interpolate(max(0, dist - delta))
                point_after = line.interpolate(min(line.length, dist + delta))
                angle = math.degrees(math.atan2(
                    point_after.y - point_before.y,
                    point_after.x - point_before.x
                ))
                
                # Normalize angle
                if angle > 90: angle -= 180
                elif angle < -90: angle += 180
                
                candidates.append((point, angle, label_text))
        
        # Add nodes and edges to graph for conflict resolution
        for i, (point1, angle1, text1) in enumerate(candidates):
            node_id = f"{source_layer_name}_{i}"
            G.add_node(node_id, pos=point1, angle=angle1, text=text1)
            
            # Add edges between conflicting labels
            for j, (point2, angle2, text2) in enumerate(candidates[i+1:], i+1):
                if check_label_collision(point1, text1, angle1, [calculate_label_box(point2, len(text2) * text_height * 0.6, text_height, angle2)], text_height, spacing_settings):
                    G.add_edge(f"{source_layer_name}_{i}", f"{source_layer_name}_{j}")
    
    # Find maximum independent set for non-conflicting labels
    independent_set = nx.maximal_independent_set(G)
    
    # Create features from selected positions
    for node_id in independent_set:
        node = G.nodes[node_id]
        features_list.append({
            'geometry': node['pos'],
            'properties': {
                'label': node['text'],
                'rotation': node['angle']
            }
        })
    
    # Log statistics (keeping existing warning logic)
    for source_name, count in source_layer_counts.items():
        placed_labels = len([
            f for f in features_list 
            if f['properties']['label'] == next(
                (sl['label'] for sl in source_layers if sl['name'] == source_name), 
                ''
            )
        ])
        
        if placed_labels < count:
            warning_message = (
                f"Only {placed_labels} of {count} possible label positions were used for source layer '{source_name}'. "
                "Check the layer geometry and label spacing settings."
            )
            log_warning(
                format_operation_warning(
                    layer_name,
                    'label_association',
                    warning_message
                )
            )
    
    # Create result GeoDataFrame
    if not features_list:
        return gpd.GeoDataFrame({'geometry': [], 'label': []}, geometry='geometry', crs=crs)
    
    result_gdf = gpd.GeoDataFrame.from_features(features_list, crs=crs)
    result_gdf.attrs['text_style'] = text_style
    
    return result_gdf