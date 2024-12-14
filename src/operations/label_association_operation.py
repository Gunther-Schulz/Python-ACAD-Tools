from shapely import MultiLineString
from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning, log_info
import math
import numpy as np
from src.style_manager import StyleManager
import networkx as nx


def get_line_placement_positions(line, text_width, text_height, step=None):
    """Get candidate positions along a line with improved angle calculation."""
    positions = []
    line_length = line.length
    
    # Use provided step if specified, otherwise calculate default
    if step is None:
        step = min(text_width * 0.8, line_length / 2)  # Default calculation
    
    # Ensure step is not larger than line length
    step = min(step, line_length)
    
    # Look-ahead/behind distance for angle calculation
    look_dist = text_width * 0.5
    
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
    
    # Handle offset as tuple (x,y) or single value
    offset_x = offset[0] if isinstance(offset, (tuple, list)) else offset
    offset_y = offset[1] if isinstance(offset, (tuple, list)) and len(offset) > 1 else offset
    
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
    if offset_x == 0 and offset_y == 0:
        offset_x = offset_y = text_height * 0.5
    
    for angle, (dx, dy) in zip(angles, base_offsets):
        # Calculate position with separate x and y offsets
        x = point.x + dx * offset_x
        y = point.y + dy * offset_y
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

def _initialize_label_settings(operation, project_settings, layer_name):
    """Initialize and return label settings from operation config."""
    label_settings = operation.get('labelSettings', {})
    show_log = operation.get('showLog', False)
    
    # Get style settings
    style_manager = StyleManager(project_settings)
    style, _ = style_manager.get_style('leitung')
    text_style = style.get('text', {}) if style else {}
    text_height = float(text_style.get('height', 1.5))
    
    if show_log:
        log_info(f"""
Style Resolution Debug:
├─ Layer Name: {layer_name}
├─ Base Style: {style}
└─ Text Style: {text_style}
Final Text Height: {text_height} (from style)
""")
    
    # Compile spacing settings
    spacing_settings = {
        'width_factor': label_settings.get('widthFactor', 1.3),
        'height_factor': label_settings.get('heightFactor', 1.5),
        'buffer_factor': label_settings.get('bufferFactor', text_height * 0.5),
        'collision_margin': label_settings.get('collisionMargin', text_height * 0.25),
        'label_spacing': label_settings.get('labelSpacing', None)
    }
    
    # Handle labelOffset which can be a number, dict, or list
    label_offset = label_settings.get('labelOffset', 0)
    offset_x, offset_y = _get_offset_values(label_offset)
    
    return {
        'text_style': text_style,
        'text_height': text_height,
        'spacing_settings': spacing_settings,
        'show_log': show_log,
        'avoid_all_geometries': label_settings.get('avoidAllGeometries', False),
        'avoid_layers': label_settings.get('avoidLayers', []),
        'global_label_offset_x': offset_x,
        'global_label_offset_y': offset_y
    }

def _collect_geometries_to_avoid(all_layers, project_settings, crs, avoid_all_geometries, avoid_layers, show_log):
    """Collect geometries that labels should avoid."""
    geometries_to_avoid = {}
    
    if avoid_all_geometries:
        for layer_info in project_settings.get('geomLayers', []):
            layer_to_check = layer_info.get('name')
            if layer_to_check:
                geom = _get_filtered_geometry(all_layers, project_settings, crs, layer_to_check, None)
                if geom is not None and not geom.is_empty:
                    line_geometry = convert_to_line_geometry(geom)
                    if line_geometry is not None:
                        geometries_to_avoid[layer_to_check] = line_geometry
    elif avoid_layers:
        for layer_to_check in avoid_layers:
            geom = _get_filtered_geometry(all_layers, project_settings, crs, layer_to_check, None)
            if geom is not None and not geom.is_empty:
                line_geometry = convert_to_line_geometry(geom)
                if line_geometry is not None:
                    geometries_to_avoid[layer_to_check] = line_geometry
                    if show_log:
                        log_info(f"Adding layer {layer_to_check} to avoidance list")
    
    return geometries_to_avoid

def _generate_label_candidates(source_layers, all_layers, project_settings, crs, settings):
    """Generate label candidates for all source layers."""
    collision_graph = nx.Graph()
    # Store settings and other necessary data in the graph
    collision_graph.graph['settings'] = settings
    collision_graph.graph['source_layers'] = source_layers
    collision_graph.graph['source_geometries'] = {}
    collision_graph.graph['geometries_to_avoid'] = {}
    
    label_candidates = []
    node_counter = 0
    candidate_counts = {}
    source_geometries = {}
    
    for source_config in source_layers:
        source_layer_name = source_config.get('name')
        if not source_layer_name:
            continue
            
        # Get label text or column name
        label_text = source_config.get('label', '')
        label_column = source_config.get('labelColumn', None)
        
        layer_offset = source_config.get('labelOffset', {
            'x': settings['global_label_offset_x'],
            'y': settings['global_label_offset_y']
        })
        offset_x, offset_y = _get_offset_values(layer_offset, 
                                              default_offset=settings['global_label_offset_x'])
        
        candidate_counts[source_layer_name] = 0
        
        # Get and process source geometry
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, None)
        if source_geometry is None or source_geometry.is_empty:
            continue
            
        # If using labelColumn, get the corresponding GeoDataFrame
        if label_column:
            source_gdf = all_layers.get(source_layer_name)
            if source_gdf is not None and label_column in source_gdf.columns:
                # Process each geometry with its corresponding label
                for idx, row in source_gdf.iterrows():
                    geom = row.geometry
                    if geom is None or geom.is_empty:
                        continue
                    
                    feature_label = str(row[label_column])
                    line_geom = convert_to_line_geometry(geom)
                    if line_geom is None:
                        continue
                        
                    positions = _get_positions_for_geometry(line_geom, feature_label, 
                                                         settings['text_height'], 
                                                         settings['spacing_settings'], 
                                                         (offset_x, offset_y))
                    
                    for pos, angle, score in positions:
                        node_id = f"{source_layer_name}_{node_counter}"
                        collision_graph.add_node(
                            node_id,
                            pos=pos,
                            angle=angle,
                            text=feature_label,
                            score=score,
                            layer=source_layer_name,
                            offset_x=offset_x,
                            offset_y=offset_y
                        )
                        label_candidates.append(node_id)
                        node_counter += 1
                        candidate_counts[source_layer_name] += 1
                continue
        
        # Original functionality for non-labelColumn cases
        source_geometry = convert_to_line_geometry(source_geometry)
        if source_geometry is None:
            continue
            
        source_geometries[source_layer_name] = source_geometry
        collision_graph.graph['source_geometries'][source_layer_name] = source_geometry
        
        # Generate candidates for each geometry
        geometries = [source_geometry] if isinstance(source_geometry, (LineString, Point, Polygon)) else list(source_geometry.geoms)
        
        for geom in geometries:
            positions = _get_positions_for_geometry(geom, label_text, settings['text_height'], 
                                                 settings['spacing_settings'], (offset_x, offset_y))
            
            for pos, angle, score in positions:
                node_id = f"{source_layer_name}_{node_counter}"
                collision_graph.add_node(
                    node_id,
                    pos=pos,
                    angle=angle,
                    text=label_text,
                    score=score,
                    layer=source_layer_name,
                    offset_x=offset_x,
                    offset_y=offset_y
                )
                label_candidates.append(node_id)
                node_counter += 1
                candidate_counts[source_layer_name] += 1
    
    return collision_graph, label_candidates, candidate_counts, source_geometries

def _get_positions_for_geometry(geom, label_text, text_height, spacing_settings, label_offset):
    """Get label positions for a specific geometry."""
    positions = []
    text_width = len(label_text) * text_height * 0.6
    
    if isinstance(geom, LineString):
        step = float(spacing_settings['label_spacing']) if spacing_settings['label_spacing'] else text_width * 0.8
        positions = get_line_placement_positions(geom, text_width, text_height, step)
        positions = [(pos[0], pos[1], pos[2]) for pos in positions]
    elif isinstance(geom, MultiLineString):
        for line in geom.geoms:
            line_positions = get_line_placement_positions(line, text_width, text_height)
            positions.extend([(pos[0], pos[1], pos[2]) for pos in line_positions])
    elif isinstance(geom, Polygon):
        point = get_polygon_anchor_position(geom, text_width, text_height)
        positions = [(point, 0, 1.0)]
    elif isinstance(geom, Point):
        point, angle = get_point_label_position(geom, label_text, text_height, label_offset)
        positions = [(point, angle, 1.0)]
    
    return positions

def _build_collision_network(collision_graph, label_candidates, settings, source_layers, source_geometries, geometries_to_avoid):
    """Build a NetworkX graph representing all collision relationships."""
    G = nx.Graph()
    text_boxes = {}
    
    # Add all label candidates as nodes
    for node_id in label_candidates:
        node = collision_graph.nodes[node_id]
        text_width = len(node['text']) * settings['text_height'] * 0.6
        
        # Get layer-specific offset
        layer_config = next((l for l in source_layers if l['name'] == node['layer']), {})
        layer_offset = layer_config.get('labelOffset', {
            'x': settings['global_label_offset_x'],
            'y': settings['global_label_offset_y']
        })
        offset_x, offset_y = _get_offset_values(layer_offset)
        
        # Apply offset to position
        point = node['pos']
        angle = node['angle']
        if offset_x != 0 or offset_y != 0:
            point = _apply_offset_to_point(point, offset_x, offset_y, angle)
        
        # Create label box
        box = calculate_label_box(point, text_width, settings['text_height'], angle, settings['spacing_settings'])
        text_boxes[node_id] = box
        
        # Store adjusted position
        node['adjusted_pos'] = point
        
        # Add node to graph with initial score
        base_score = node['score']
        G.add_node(node_id, 
                  weight=base_score,
                  box=box,
                  layer=node['layer'],
                  text=node['text'])
        
        # Check geometry intersections
        buffer_distance = settings['text_height'] * settings['spacing_settings']['buffer_factor']
        
        # Check source geometry intersections
        source_geom = source_geometries.get(node['layer'])
        if source_geom:
            intersection_score = _calculate_geometry_intersection_score(box, source_geom, buffer_distance)
            G.nodes[node_id]['weight'] *= intersection_score
        
        # Check avoided geometries intersections
        if geometries_to_avoid:
            for avoid_layer, avoid_geom in geometries_to_avoid.items():
                if avoid_layer != node['layer']:
                    intersection_score = _calculate_geometry_intersection_score(box, avoid_geom, buffer_distance)
                    G.nodes[node_id]['weight'] *= intersection_score
    
    # Add edges for label-label collisions
    for i, node1_id in enumerate(label_candidates):
        box1 = text_boxes[node1_id]
        for node2_id in label_candidates[i+1:]:
            box2 = text_boxes[node2_id]
            if box1.intersects(box2):
                # Calculate intersection area relative to box areas
                intersection_area = box1.intersection(box2).area
                union_area = box1.area + box2.area - intersection_area
                overlap_ratio = intersection_area / union_area
                G.add_edge(node1_id, node2_id, weight=overlap_ratio)
    
    return G, text_boxes

def _calculate_geometry_intersection_score(box, geometry, buffer_distance):
    """Calculate a score based on how much a label box intersects with geometry."""
    if geometry is None:
        return 1.0
    
    # Buffer the geometry for more conservative collision detection
    buffered_geom = geometry.buffer(buffer_distance)
    
    if box.intersects(buffered_geom):
        intersection = box.intersection(buffered_geom)
        intersection_ratio = intersection.area / box.area
        # Return a score between 0 and 1, where 0 means complete overlap
        return max(0.0, 1.0 - intersection_ratio * 2)
    return 1.0

def _select_optimal_labels(G, settings):
    """Select optimal label positions using NetworkX's maximum independent set."""
    selected_nodes = set()
    remaining_nodes = set(G.nodes())
    
    while remaining_nodes:
        # Calculate scores for remaining nodes
        node_scores = {}
        for node in remaining_nodes:
            base_weight = G.nodes[node]['weight']
            # Penalize nodes that conflict with already selected nodes
            conflict_penalty = sum(G.edges[node, selected]['weight'] 
                                 for selected in selected_nodes 
                                 if G.has_edge(node, selected))
            node_scores[node] = base_weight * (1.0 - conflict_penalty)
        
        if not node_scores:
            break
            
        # Select the node with highest score
        best_node = max(node_scores.items(), key=lambda x: x[1])[0]
        selected_nodes.add(best_node)
        
        # Remove the selected node and its neighbors from consideration
        remaining_nodes.remove(best_node)
        remaining_nodes -= set(G.neighbors(best_node))
    
    return selected_nodes

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Creates label points along lines using networkx for optimal label placement."""
    # Initialize settings
    settings = _initialize_label_settings(operation, project_settings, layer_name)
    
    # Get geometries to avoid
    geometries_to_avoid = _collect_geometries_to_avoid(
        all_layers, project_settings, crs, 
        settings['avoid_all_geometries'], 
        settings['avoid_layers'], 
        settings['show_log']
    )
    
    # Generate candidates
    source_layers = operation.get('sourceLayers', [{'name': layer_name}])
    collision_graph, label_candidates, candidate_counts, source_geometries = _generate_label_candidates(
        source_layers, all_layers, project_settings, crs, settings
    )
    
    # Build collision network
    G, text_boxes = _build_collision_network(
        collision_graph, label_candidates, settings,
        source_layers, source_geometries, geometries_to_avoid
    )
    
    # Select optimal labels
    selected_nodes = _select_optimal_labels(G, settings)
    
    # Create features from selected positions
    features_list = _create_features_from_selected_nodes(collision_graph, selected_nodes)
    
    # Log statistics if needed
    if settings['show_log']:
        _log_label_statistics(features_list, candidate_counts, all_layers, project_settings, crs, settings)
    
    # Create and return result GeoDataFrame
    if not features_list:
        return gpd.GeoDataFrame({'geometry': [], 'label': []}, geometry='geometry', crs=crs)
    
    result_gdf = gpd.GeoDataFrame.from_features(features_list, crs=crs)
    result_gdf.attrs['text_style'] = settings['text_style']
    
    return result_gdf

def convert_to_line_geometry(geometry):
    """Convert various geometry types to line geometry."""
    if geometry is None:
        return None
    
    if isinstance(geometry, (LineString, MultiLineString)):
        return geometry
    elif isinstance(geometry, Point):
        return geometry  # Keep points as-is
    elif isinstance(geometry, Polygon):
        return geometry.exterior  # Convert polygon to its boundary
    elif isinstance(geometry, MultiPolygon):
        lines = [poly.exterior for poly in geometry.geoms]
        return MultiLineString(lines)
    return None

def _get_offset_values(offset_config, default_offset=0):
    """Convert offset config to x,y values."""
    if isinstance(offset_config, (int, float)):
        # If single number, use it for both x and y
        return float(offset_config), float(offset_config)
    elif isinstance(offset_config, dict):
        # Get x and y values from dict, default to 0 if not specified
        return float(offset_config.get('x', 0)), float(offset_config.get('y', 0))
    elif isinstance(offset_config, (list, tuple)) and len(offset_config) >= 2:
        # If list/tuple with at least 2 values, use first two as x,y
        return float(offset_config[0]), float(offset_config[1])
    else:
        # Default fallback
        return float(default_offset), float(default_offset)

def _apply_offset_to_point(point, offset_x, offset_y, angle=None):
    """Apply x,y offset to point, considering rotation angle.
    
    Args:
        point: The base point to offset
        offset_x: Offset along text direction (positive = right, negative = left)
        offset_y: Offset perpendicular to text (positive = up, negative = down)
        angle: Text rotation angle in degrees
    """
    if angle is not None:
        # Convert angle to radians
        angle_rad = math.radians(angle)
        # Calculate rotated offsets
        # x offset along text direction
        # y offset perpendicular to text direction
        rotated_x = offset_x * math.cos(angle_rad) - offset_y * math.sin(angle_rad)
        rotated_y = offset_x * math.sin(angle_rad) + offset_y * math.cos(angle_rad)
        return Point(point.x + rotated_x, point.y + rotated_y)
    else:
        # Without rotation, x is horizontal and y is vertical
        return Point(point.x + offset_x, point.y + offset_y)

def _create_features_from_selected_nodes(collision_graph, selected_nodes):
    """Create features from selected positions."""
    features_list = []
    for node_id in selected_nodes:
        node = collision_graph.nodes[node_id]
        # Use the already offset-adjusted position
        point = node['adjusted_pos']
        angle = node['angle']
        
        features_list.append({
            'geometry': point,
            'properties': {
                'label': node['text'],
                'rotation': angle,
                'source_layer': node['layer']
            }
        })

    return features_list

def _log_label_statistics(features_list, candidate_counts, all_layers, project_settings, crs, settings):
    """Log label statistics if needed."""
    if settings['show_log']:
        for layer, count in candidate_counts.items():
            placed_labels = len([
                f for f in features_list 
                if f['properties']['source_layer'] == layer
            ])
            
            source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, layer, None)
            total_line_length = 0
            
            if source_geometry is not None and not source_geometry.is_empty:
                if isinstance(source_geometry, (LineString, Point, Polygon)):
                    geometries = [source_geometry]
                else:
                    geometries = list(source_geometry.geoms)
                
                for geom in geometries:
                    if isinstance(geom, LineString):
                        total_line_length += geom.length
                    elif isinstance(geom, MultiLineString):
                        total_line_length += sum(line.length for line in geom.geoms)
            
            if total_line_length > 0:
                labels_per_length = (placed_labels * 100.0) / total_line_length
                log_info(f"""
Layer: {layer}
├─ Placed Labels: {placed_labels}/{count} candidates
├─ Line Length: {total_line_length:.1f} units
└─ Density: {labels_per_length:.2f} labels per 100 units
""")
            else:
                log_info(f"""
Layer: {layer}
├─ Placed Labels: {placed_labels}/{count} candidates
└─ No line length calculated
""")