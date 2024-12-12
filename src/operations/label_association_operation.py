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


def get_line_placement_positions(line, text_width, text_height):
    """Get candidate positions along a line with improved angle calculation."""
    positions = []
    line_length = line.length
    
    # Adjust step size based on text dimensions
    step = min(text_width * 0.8, line_length / 2)  # Ensure at least 2 candidates for short lines
    
    # Look-ahead/behind distance for angle calculation
    look_dist = text_width * 0.5  # Use half text width for angle calculation
    
    current_dist = 0
    while current_dist <= line_length:
        point = line.interpolate(current_dist)
        
        # Calculate points before and after for better angle determination
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

def calculate_text_dimensions(label_text, text_style):
    """Calculate actual text dimensions based on style settings."""
    # Get font size from style, with fallbacks
    font_size = text_style.get('height', 2.5)  # Default 2.5 if not specified
    
    # Get font settings that affect width
    font_weight = text_style.get('weight', 'normal')
    font_family = text_style.get('family', 'Arial')
    
    # Width multiplier based on font weight
    weight_factor = 1.0
    if font_weight in ['bold', 'heavy']:
        weight_factor = 1.2
    elif font_weight == 'light':
        weight_factor = 0.9
    
    # Base character width (empirically determined for common fonts)
    char_width_factor = {
        'Arial': 0.6,
        'Helvetica': 0.6,
        'Times New Roman': 0.55,
        'Courier New': 0.65,
        'Verdana': 0.7,
    }.get(font_family, 0.6)  # Default to Arial metrics if font not found
    
    # Calculate dimensions
    text_width = len(label_text) * font_size * char_width_factor * weight_factor
    text_height = font_size
    
    return text_width, text_height

def check_label_collision(point, label_text, angle, existing_labels, text_style, settings=None):
    """Check if a label position collides with existing labels using NetworkX for optimization."""
    if settings is None:
        settings = {
            'width_factor': 1.3,
            'height_factor': 1.5,
            'buffer_factor': 0.2,
            'collision_margin': 0.25,
        }
    
    # Calculate actual text dimensions
    text_width, text_height = calculate_text_dimensions(label_text, text_style)
    
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
    """Try to resolve label collision by moving the label using NetworkX."""
    # Create a conflict graph
    G = nx.Graph()
    
    # Add the new label as node 0
    text_width = len(label_text) * text_height * 0.6
    new_box = calculate_label_box(point, text_width, text_height, angle)
    G.add_node(0, box=new_box, point=point)
    
    # Add existing labels as nodes and create edges for conflicts
    for i, label_box in enumerate(existing_labels, 1):
        G.add_node(i, box=label_box)
        if new_box.intersects(label_box):
            G.add_edge(0, i)
    
    if not G.edges(0):  # No conflicts
        return point, False
    
    # Calculate repulsion vectors using NetworkX's spring_layout
    pos = nx.spring_layout(
        G,
        k=text_height * 2,  # Optimal distance between nodes
        iterations=50,
        pos={i: (n['box'].centroid.x, n['box'].centroid.y) for i, n in G.nodes(data=True)},
        fixed=range(1, len(G.nodes()))  # Keep existing labels fixed
    )
    
    # Get the new position for our label
    new_pos = pos[0]
    new_point = Point(new_pos[0], new_pos[1])
    
    # Verify if new position resolves conflicts
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
    
    # Create a single graph for all labels across all source layers
    collision_graph = nx.Graph()
    label_candidates = []
    node_counter = 0
    
    # Track candidates per layer
    candidate_counts = {}
    
    # Process each source layer to generate candidates
    for source_config in source_layers:
        source_layer_name = source_config.get('name')
        if not source_layer_name:
            continue
            
        label_text = source_config.get('label', '')
        label_offset = float(source_config.get('labelOffset', global_label_offset))
        
        candidate_counts[source_layer_name] = 0
        
        # Get source geometry
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, None)
        if source_geometry is None or source_geometry.is_empty:
            continue

        # Convert to list of geometries
        geometries = []
        if isinstance(source_geometry, (LineString, Point, Polygon)):
            geometries = [source_geometry]
        else:
            geometries = list(source_geometry.geoms)

        # Generate candidates for this layer
        for geom in geometries:
            # Get potential positions based on geometry type
            positions = []
            if isinstance(geom, LineString):
                text_width = len(label_text) * text_height * 0.6
                positions = get_line_placement_positions(geom, text_width, text_height)
                positions = [(pos[0], pos[1], pos[2]) for pos in positions]  # point, angle, score
            elif isinstance(geom, Polygon):
                point = get_polygon_anchor_position(geom, len(label_text) * text_height * 0.6, text_height)
                positions = [(point, 0, 1.0)]  # Single position with 0 rotation
            elif isinstance(geom, Point):
                point, angle = get_point_label_position(geom, label_text, text_height, label_offset)
                positions = [(point, angle, 1.0)]

            # Add nodes to graph for each candidate position
            for pos, angle, score in positions:
                node_id = f"{source_layer_name}_{node_counter}"
                collision_graph.add_node(
                    node_id,
                    pos=pos,
                    angle=angle,
                    text=label_text,
                    score=score,
                    layer=source_layer_name
                )
                label_candidates.append(node_id)
                node_counter += 1
                candidate_counts[source_layer_name] += 1

    # Build edges for collisions between all candidates
    text_boxes = {}
    for node_id in collision_graph.nodes():
        node = collision_graph.nodes[node_id]
        text_width, text_height = calculate_text_dimensions(node['text'], text_style)
        box = calculate_label_box(node['pos'], text_width, text_height, node['angle'], spacing_settings)
        text_boxes[node_id] = box

    # Add edges for colliding labels
    for i, node1_id in enumerate(label_candidates):
        box1 = text_boxes[node1_id]
        for node2_id in label_candidates[i+1:]:
            box2 = text_boxes[node2_id]
            if box1.intersects(box2):
                collision_graph.add_edge(node1_id, node2_id)

    # Create weighted graph for NetworkX with layer information
    weighted_graph = nx.Graph()
    nodes_by_layer = {}
    
    # Group nodes by layer and add to graph
    for node_id in collision_graph.nodes():
        node = collision_graph.nodes[node_id]
        layer_name = node['layer']
        weight = node['score']
        
        weighted_graph.add_node(node_id, 
                              weight=weight,
                              layer=layer_name)
        
        nodes_by_layer.setdefault(layer_name, []).append(node_id)
    
    # Add collision edges
    weighted_graph.add_edges_from(collision_graph.edges())

    # Initialize selection tracking
    selected_nodes = set()
    remaining_nodes = set(weighted_graph.nodes())
    layer_counts = {layer: 0 for layer in nodes_by_layer.keys()}

    # Process nodes layer by layer in rounds
    while remaining_nodes:
        # Sort layers by current label count (ascending) to give priority to underrepresented layers
        layers_by_priority = sorted(nodes_by_layer.keys(), 
                                  key=lambda l: layer_counts[l])
        
        made_selection = False
        
        # Try to select one node from each layer
        for layer in layers_by_priority:
            layer_candidates = set(nodes_by_layer[layer]) & remaining_nodes
            if not layer_candidates:
                continue
                
            # Create subgraph of candidates and their conflicts
            candidate_subgraph = weighted_graph.subgraph(layer_candidates)
            
            if not candidate_subgraph.nodes:
                continue
            
            # Select best candidate based on weight and conflicts
            candidate_scores = {
                n: (weighted_graph.nodes[n]['weight'] / 
                    (1 + sum(1 for neighbor in weighted_graph.neighbors(n) 
                            if neighbor in selected_nodes)))
                for n in candidate_subgraph.nodes
            }
            
            if candidate_scores:
                best_candidate = max(candidate_scores.items(), key=lambda x: x[1])[0]
                
                # Check if adding this candidate would create conflicts
                if not any(neighbor in selected_nodes 
                          for neighbor in weighted_graph.neighbors(best_candidate)):
                    selected_nodes.add(best_candidate)
                    layer_counts[layer] += 1
                    made_selection = True
                    
                    # Remove selected node and update remaining nodes
                    remaining_nodes.remove(best_candidate)
                    remaining_nodes -= set(weighted_graph.neighbors(best_candidate))
        
        # If no selections were made in this round, break to avoid infinite loop
        if not made_selection:
            break

    # Create features from selected positions
    features_list = []
    for node_id in selected_nodes:
        node = collision_graph.nodes[node_id]
        features_list.append({
            'geometry': node['pos'],
            'properties': {
                'label': node['text'],
                'rotation': node['angle'],
                'source_layer': node['layer']
            }
        })

    # Log summary statistics
    for layer, count in candidate_counts.items():
        # Get placed labels for this layer
        placed_labels = len([
            f for f in features_list 
            if f['properties']['source_layer'] == layer
        ])
        
        # Get source geometry using the same method as for candidate generation
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, layer, None)
        total_line_length = 0
        
        if source_geometry is not None and not source_geometry.is_empty:
            # Handle single or multiple geometries
            if isinstance(source_geometry, (LineString, Point, Polygon)):
                geometries = [source_geometry]
            else:
                geometries = list(source_geometry.geoms)
            
            # Calculate total length
            for geom in geometries:
                if isinstance(geom, LineString):
                    total_line_length += geom.length
                elif isinstance(geom, MultiLineString):
                    total_line_length += sum(line.length for line in geom.geoms)
        
        if total_line_length > 0:
            # Calculate labels per unit length (per 100 map units)
            labels_per_length = (placed_labels * 100.0) / total_line_length
            
            log_warning(f"Layer: {layer} - Placed {placed_labels} of {count} candidate positions. "
                       f"Line length: {total_line_length:.1f}, "
                       f"Labels per 100 units: {labels_per_length:.3f}")
        else:
            log_warning(f"Layer: {layer} - Placed {placed_labels} of {count} candidate positions. "
                       f"No line length calculated.")

    # Create result GeoDataFrame
    if not features_list:
        return gpd.GeoDataFrame({'geometry': [], 'label': []}, geometry='geometry', crs=crs)
    
    result_gdf = gpd.GeoDataFrame.from_features(features_list, crs=crs)
    result_gdf.attrs['text_style'] = text_style
    
    return result_gdf