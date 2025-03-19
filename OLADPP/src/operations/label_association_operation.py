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
    """Get candidate positions along a line with improved corner detection using NetworkX."""
    positions = []
    line_length = line.length
    
    # Use provided step if specified, otherwise calculate default
    if step is None:
        step = min(text_width * 0.8, line_length / 2)
    
    # Ensure step is not larger than line length
    step = min(step, line_length)
    
    # Create a graph to analyze line topology
    G = nx.Graph()
    coords = list(line.coords)
    for i in range(len(coords)-1):
        segment = LineString([coords[i], coords[i+1]])
        G.add_edge(i, i+1, 
                  weight=segment.length,
                  geometry=segment)
    
    current_dist = 0
    while current_dist <= line_length:
        point = line.interpolate(current_dist)
        
        # Calculate space ahead for label placement
        space_ahead = line_length - current_dist
        
        # Find nearest line segment using NetworkX
        nearest_vertex = min(range(len(coords)), 
                           key=lambda i: Point(coords[i]).distance(point))
        
        # Get local line context using NetworkX neighborhood
        local_context = nx.ego_graph(G, nearest_vertex, radius=2)
        
        # Calculate angle using local context
        angle = _calculate_local_angle(point, local_context, coords)
        
        # Normalize angle
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        
        # Calculate corner penalty using NetworkX path analysis
        corner_penalty = _calculate_corner_penalty(G, point, coords, text_width)
        
        # Calculate curvature score using NetworkX
        curvature_score = _calculate_curvature_score(local_context, coords)
        
        # Calculate final position score
        score = 1.0 + curvature_score
        
        # Penalize positions near corners
        score -= corner_penalty
        
        # Prefer middle sections
        relative_pos = current_dist / line_length
        if 0.3 <= relative_pos <= 0.7:
            score += 1.0
        
        # Only add position if score is acceptable and there's enough space
        if score > 0.3 and space_ahead >= text_width / 2:
            positions.append((point, angle, score))
        
        current_dist += step
    
    return positions

def _calculate_local_angle(point, local_context, coords):
    """Calculate angle at a point using local network context."""
    edges = list(local_context.edges(data=True))
    if not edges:
        return 0
    
    # Get nearby segments
    segments = [edge[2]['geometry'] for edge in edges]
    
    # Find closest segment
    closest_segment = min(segments, key=lambda s: s.distance(point))
    
    # Calculate angle along closest segment
    coords = list(closest_segment.coords)
    return math.degrees(math.atan2(
        coords[-1][1] - coords[0][1],
        coords[-1][0] - coords[0][0]
    ))

def _calculate_corner_penalty(G, point, coords, text_width):
    """Calculate corner penalty using NetworkX path analysis."""
    corner_penalty = 0
    
    # Find vertices within text_width distance
    nearest_vertex = min(range(len(coords)), 
                        key=lambda i: Point(coords[i]).distance(point))
    
    # Use NetworkX to find nearby vertices
    nearby_vertices = nx.single_source_dijkstra_path_length(G, nearest_vertex, 
                                                          cutoff=text_width)
    
    for v in nearby_vertices:
        if v > 0 and v < len(coords)-1:
            # Get local subgraph for angle calculation
            local_graph = nx.ego_graph(G, v, radius=1)
            if len(local_graph) >= 3:
                # Calculate angle at vertex
                prev_point = coords[v-1]
                curr_point = coords[v]
                next_point = coords[v+1]
                angle = _calculate_vertex_angle(prev_point, curr_point, next_point)
                
                if angle < 150:  # Angle threshold for corners
                    dist_to_corner = Point(coords[v]).distance(point)
                    # Progressive penalty based on distance and angle
                    angle_factor = (150 - angle) / 150  # More penalty for sharper angles
                    distance_factor = max(0, 1 - (dist_to_corner / text_width))
                    corner_penalty += angle_factor * distance_factor
    
    return corner_penalty

def _calculate_curvature_score(local_context, coords):
    """Calculate curvature score using NetworkX local structure analysis."""
    if len(local_context) < 3:
        return 0
    
    # Calculate average angle change between consecutive segments
    angles = []
    edges = list(local_context.edges())
    for i in range(len(edges)-1):
        if edges[i][1] == edges[i+1][0]:  # Connected segments
            v1 = edges[i]
            v2 = edges[i+1]
            angle = _calculate_vertex_angle(
                coords[v1[0]], 
                coords[v1[1]], 
                coords[v2[1]]
            )
            angles.append(angle)
    
    if not angles:
        return 0
    
    # Convert angles to curvature score
    avg_angle = sum(angles) / len(angles)
    if avg_angle > 170:  # Nearly straight
        return 2.0
    elif avg_angle > 150:  # Slightly curved
        return 1.0
    else:  # Significantly curved
        return 0.0

def _calculate_vertex_angle(p1, p2, p3):
    """Calculate angle at vertex p2 in degrees."""
    v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
    v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
    
    dot_product = np.dot(v1, v2)
    norms = np.linalg.norm(v1) * np.linalg.norm(v2)
    
    if norms == 0:
        return 180
    
    cos_angle = dot_product / norms
    cos_angle = min(1.0, max(-1.0, cos_angle))  # Ensure domain of arccos
    
    return math.degrees(math.acos(cos_angle))

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

def get_point_label_position(point, label_text, text_height, offset=0, point_position=None):
    """Get best label position for a point using Mapbox's approach."""
    # Try multiple positions around the point
    candidates = []
    
    # Calculate text dimensions
    text_width = len(label_text) * text_height * 0.6
    
    # Handle offset as tuple (x,y) or single value
    offset_x = offset[0] if isinstance(offset, (tuple, list)) else offset
    offset_y = offset[1] if isinstance(offset, (tuple, list)) and len(offset) > 1 else offset
    
    # Define possible positions (clockwise from right)
    POSITION_MAP = {
        "right": (0, (1, 0)),      # 0 degrees
        "top-right": (45, (1, 1)),
        "top": (90, (0, 1)),
        "top-left": (135, (-1, 1)),
        "left": (180, (-1, 0)),
        "bottom-left": (225, (-1, -1)),
        "bottom": (270, (0, -1)),
        "bottom-right": (315, (1, -1))
    }
    
    # Default offset distance based on text height if not specified
    if offset_x == 0 and offset_y == 0:
        offset_x = offset_y = text_height * 0.5
    
    if point_position and point_position.lower() in POSITION_MAP:  # Make case-insensitive
        # Use only the specified position
        angle, (dx, dy) = POSITION_MAP[point_position.lower()]
        # Apply offset to create adjusted position
        adjusted_pos = _apply_offset_to_point(point, dx * offset_x, dy * offset_y, angle)
        candidates.append((adjusted_pos, angle, 2.0))  # Higher score for specified position
    else:
        # Use all positions if no override
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
        
        for angle, (dx, dy) in zip(angles, base_offsets):
            # Use the existing offset application function
            adjusted_pos = _apply_offset_to_point(point, dx * offset_x, dy * offset_y, angle)
            
            score = 1.0
            if dx > 0:  # Right side
                score += 0.5
            if dy > 0:  # Top half
                score += 0.3
                
            candidates.append((adjusted_pos, angle, score))
    
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

def _initialize_label_settings(operation, project_loader, layer_name):
    """Initialize and return label settings from operation config."""
    label_settings = operation.get('labelSettings', {})
    show_log = operation.get('showLog', False)
    
    # Get style settings
    style_manager = StyleManager(project_loader)
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

def _should_add_label(feature_row):
    """Check if label should be added based on add_label column.
    
    Args:
        feature_row: pandas Series containing feature attributes
        
    Returns:
        bool: True if label should be added, False otherwise
    """
    # If add_label column doesn't exist in the Series, always add label
    if 'add_label' not in feature_row.index:
        return True
        
    try:
        # Convert to int in case it's a string or float
        add_label_value = int(feature_row['add_label'])
        return add_label_value == 1
    except (ValueError, TypeError):
        # If conversion fails, default to True
        return True

def _generate_label_candidates(source_layers, all_layers, project_settings, crs, settings):
    """Generate label candidates for all source layers."""
    collision_graph = nx.Graph()
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
        point_position = source_config.get('pointPosition', None)
        
        layer_offset = source_config.get('labelOffset', {
            'x': settings['global_label_offset_x'],
            'y': settings['global_label_offset_y']
        })
        
        candidate_counts[source_layer_name] = 0
        
        # Get source geometry and GeoDataFrame
        source_gdf = all_layers.get(source_layer_name)
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, None)
        
        if source_geometry is None or source_geometry.is_empty:
            continue
            
        source_geometries[source_layer_name] = source_geometry
        collision_graph.graph['source_geometries'][source_layer_name] = source_geometry
        
        # If using labelColumn, process each feature individually
        if label_column and source_gdf is not None and label_column in source_gdf.columns:
            for idx, row in source_gdf.iterrows():
                # Check if label should be added for this feature
                if not _should_add_label(row):
                    continue
                    
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                
                feature_label = str(row[label_column])
                line_geom = convert_to_line_geometry(geom)
                if line_geom is None:
                    continue
                    
                # Get offset values for this specific feature
                offset_x, offset_y = _get_offset_values(layer_offset, 
                                                      settings['global_label_offset_x'],
                                                      feature_row=row)
                
                positions = _get_positions_for_geometry(line_geom, feature_label, 
                                                     settings['text_height'], 
                                                     settings['spacing_settings'], 
                                                     (offset_x, offset_y),
                                                     point_position)
                
                for pos, angle, score, box in positions:
                    node_id = f"{source_layer_name}_{node_counter}"
                    collision_graph.add_node(
                        node_id,
                        pos=pos,
                        angle=angle,
                        text=feature_label,
                        score=score,
                        layer=source_layer_name,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        box=box
                    )
                    label_candidates.append(node_id)
                    node_counter += 1
                    candidate_counts[source_layer_name] += 1
                    
        else:
            # Process geometry without per-feature attributes
            offset_x, offset_y = _get_offset_values(layer_offset, settings['global_label_offset_x'])
            
            geometries = [source_geometry] if isinstance(source_geometry, (LineString, Point, Polygon)) else list(source_geometry.geoms)
            
            for geom in geometries:
                line_geom = convert_to_line_geometry(geom)
                if line_geom is None:
                    continue
                    
                positions = _get_positions_for_geometry(line_geom, label_text, 
                                                     settings['text_height'], 
                                                     settings['spacing_settings'], 
                                                     (offset_x, offset_y),
                                                     point_position)
                
                for pos, angle, score, box in positions:
                    node_id = f"{source_layer_name}_{node_counter}"
                    collision_graph.add_node(
                        node_id,
                        pos=pos,
                        angle=angle,
                        text=label_text,
                        score=score,
                        layer=source_layer_name,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        box=box
                    )
                    label_candidates.append(node_id)
                    node_counter += 1
                    candidate_counts[source_layer_name] += 1
    
    return collision_graph, label_candidates, candidate_counts, source_geometries

def _get_positions_for_geometry(geom, label_text, text_height, spacing_settings, label_offset, point_position=None):
    """Get label positions for a specific geometry."""
    positions = []
    text_width = len(label_text) * text_height * 0.6
    
    if isinstance(geom, Point):
        point, angle = get_point_label_position(geom, label_text, text_height, label_offset, point_position)
        # Create text box for collision detection
        box = calculate_label_box(point, text_width, text_height, angle)
        positions = [(point, angle, 1.0, box)]  # Include text box in return value
    elif isinstance(geom, LineString):
        step = float(spacing_settings['label_spacing']) if spacing_settings['label_spacing'] else text_width * 0.8
        line_positions = get_line_placement_positions(geom, text_width, text_height, step)
        positions = [(pos[0], pos[1], pos[2], calculate_label_box(pos[0], text_width, text_height, pos[1])) 
                    for pos in line_positions]
    elif isinstance(geom, MultiLineString):
        for line in geom.geoms:
            line_positions = get_line_placement_positions(line, text_width, text_height)
            positions.extend([(pos[0], pos[1], pos[2], calculate_label_box(pos[0], text_width, text_height, pos[1])) 
                            for pos in line_positions])
    elif isinstance(geom, Polygon):
        point = get_polygon_anchor_position(geom, text_width, text_height)
        box = calculate_label_box(point, text_width, text_height, 0)
        positions = [(point, 0, 1.0, box)]
    
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
    
    corner_penalty = 0  # Initialize corner_penalty for all cases
    
    # Create a graph for analyzing line topology
    if isinstance(geometry, (LineString, MultiLineString)):
        G = nx.Graph()
        if isinstance(geometry, LineString):
            coords = list(geometry.coords)
        else:
            coords = [c for line in geometry.geoms for c in line.coords]
            
        for i in range(len(coords)-1):
            G.add_edge(i, i+1, weight=Point(coords[i]).distance(Point(coords[i+1])))
        
        # Find corners
        corners = []
        for i in range(1, len(coords)-1):
            angle = _calculate_vertex_angle(coords[i-1], coords[i], coords[i+1])
            if angle < 150:  # Angle threshold for corners
                corners.append(Point(coords[i]))
        
        # Calculate corner proximity penalty
        for corner in corners:
            dist = corner.distance(box.centroid)
            if dist < buffer_distance * 2:  # Increased buffer for corners
                corner_penalty += max(0, 1 - (dist / (buffer_distance * 2)))
    
    # Buffer the geometry for collision detection
    buffered_geom = geometry.buffer(buffer_distance)
    
    if box.intersects(buffered_geom):
        intersection = box.intersection(buffered_geom)
        intersection_ratio = intersection.area / box.area
        # Include corner penalty in final score
        return max(0.0, 1.0 - (intersection_ratio * 2 + corner_penalty))
    
    return 1.0 - min(1.0, corner_penalty)  # Still apply corner penalty even without intersection

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

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation, project_loader):
    """Create label association layer."""
    try:
        # Get style settings
        style_manager = StyleManager(project_loader)
        style_name = operation.get('style')  # First try operation style
        base_style = style_manager.get_style(style_name) if style_name else {}
        
        if not base_style:
            # Try to get style from layer configuration
            layer_config = next((layer for layer in project_settings.get('layers', []) 
                              if layer.get('name') == layer_name), {})
            style_name = layer_config.get('style')
            base_style = style_manager.get_style(style_name) if style_name else {}
        
        text_style = base_style[0].get('text', {}) if isinstance(base_style, tuple) else base_style.get('text', {})
        
        # Debug style resolution
        log_info(f"""
Style Resolution Debug:
├─ Layer Name: {layer_name}
├─ Base Style: {style_name}
└─ Text Style: {text_style}""")
        
        # Get text height from style or default
        text_height = text_style.get('height', 1.5)
        log_info(f"Final Text Height: {text_height} (from style)")
        
        settings = {
            'text_height': text_height,
            'text_style': text_style,
            'spacing_settings': operation.get('spacing', {}),
            'global_label_offset_x': operation.get('labelOffsetX', 0),
            'global_label_offset_y': operation.get('labelOffsetY', 0),
            'show_log': operation.get('showLog', False)
        }
        
        # Initialize settings
        settings = _initialize_label_settings(operation, project_loader, layer_name)
        
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
    except Exception as e:
        log_warning(f"Error creating label association layer: {str(e)}")
        return gpd.GeoDataFrame({'geometry': [], 'label': []}, geometry='geometry', crs=crs)

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

def _parse_offset_expression(expression, feature_row):
    """Parse an offset expression that may include column names and arithmetic.
    
    Args:
        expression: String expression like "-(Krone_R) + 0.5" or "Krone_R * 2"
        feature_row: Row from GeoDataFrame containing column values
    """
    if not isinstance(expression, str):
        return expression
        
    try:
        # Handle negative values at start of expression
        expression = expression.replace("-(", "-1*(")
        
        # Split the expression into tokens, preserving operators
        tokens = []
        current_token = ""
        operators = {'+', '-', '*', '/', '(', ')'}
        
        for char in expression:
            if char.isspace():
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
            elif char in operators:
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
                tokens.append(char)
            else:
                current_token += char
        if current_token:
            tokens.append(current_token)
        
        # Replace column names with their values
        for i, token in enumerate(tokens):
            if token not in operators and not any(c in token for c in '0123456789.'):
                # This token is likely a column name
                try:
                    tokens[i] = str(float(feature_row[token.strip()]))
                except (KeyError, ValueError):
                    return 0  # Return 0 if column not found
        
        # Reconstruct and evaluate the expression
        expression = ''.join(tokens)
        return float(eval(expression))
        
    except (SyntaxError, NameError, TypeError, ZeroDivisionError):
        log_warning(f"Error parsing offset expression: {expression}")
        return 0

def _get_offset_values(offset_config, default_offset=0, feature_row=None):
    """Convert offset config to x,y values.
    
    Args:
        offset_config: Number, dict with x/y values or column names/expressions, or list/tuple
        default_offset: Default offset value if not specified
        feature_row: Optional row from GeoDataFrame for column-based offsets
    """
    # Handle dictionary configuration
    if isinstance(offset_config, dict):
        x_value = offset_config.get('x', 0)
        y_value = offset_config.get('y', 0)
        
        # Get x offset (either from expression/column or direct value)
        if isinstance(x_value, str) and feature_row is not None:
            x_offset = _parse_offset_expression(x_value, feature_row)
        else:
            try:
                x_offset = float(x_value) if x_value is not None else 0
            except (ValueError, TypeError):
                x_offset = 0
            
        # Get y offset (either from expression/column or direct value)
        if isinstance(y_value, str) and feature_row is not None:
            y_offset = _parse_offset_expression(y_value, feature_row)
        else:
            try:
                y_offset = float(y_value) if y_value is not None else 0
            except (ValueError, TypeError):
                y_offset = 0
            
        return x_offset, y_offset
    
    # Handle simple numeric value
    if isinstance(offset_config, (int, float)):
        return float(offset_config), float(offset_config)
    
    # Handle list/tuple
    if isinstance(offset_config, (list, tuple)) and len(offset_config) >= 2:
        return float(offset_config[0]), float(offset_config[1])
    
    # Default case
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