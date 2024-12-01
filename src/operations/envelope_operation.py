import geopandas as gpd
import numpy as np
from shapely.geometry import box, MultiPolygon, Polygon, LineString, Point
from shapely.ops import unary_union
from src.utils import log_info, log_warning
from src.operations.common_operations import _process_layer_info, format_operation_warning
from scipy.spatial import distance

def create_envelope_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Creates a minimum-area bounding rectangle (envelope) for each input geometry.
    """
    log_info(f"Creating envelope layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]
    
    padding = operation.get('padding', 0)
    min_ratio = operation.get('minRatio', None)
    cap_style = operation.get('capStyle', 'square').lower()
    
    if cap_style not in ['square', 'round']:
        log_warning(f"Invalid capStyle '{cap_style}', using 'square'")
        cap_style = 'square'
    
    result_geometries = []
    
    # Process each input layer
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]
        if source_gdf.empty:
            continue
            
        # Process each geometry
        for geom in source_gdf.geometry:
            if isinstance(geom, MultiPolygon):
                for part in geom.geoms:
                    envelope = create_optimal_envelope(part, padding, min_ratio, cap_style)
                    if envelope:
                        result_geometries.append(envelope)
            else:
                envelope = create_optimal_envelope(geom, padding, min_ratio, cap_style)
                if envelope:
                    result_geometries.append(envelope)
    
    if not result_geometries:
        log_warning(format_operation_warning(
            layer_name,
            "envelope",
            "No geometries found to create envelopes"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None
    
    result_gdf = gpd.GeoDataFrame(geometry=result_geometries, crs=crs)
    all_layers[layer_name] = result_gdf
    
    log_info(f"Created envelope layer: {layer_name} with {len(result_geometries)} envelopes")
    return result_gdf

def detect_bend(polygon, bend_threshold=20):
    """
    Optimized bend detection focusing on major structural bends.
    """
    coords = np.array(polygon.exterior.coords)
    
    # Calculate vectors and lengths
    vectors = np.diff(coords, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    total_length = np.sum(lengths)
    
    # Quick exit if we have very small segments
    if np.any(lengths < 1e-10):
        return False
        
    # Only consider segments that are major parts of the shape (at least 20% of total length)
    significant_mask = lengths > (total_length * 0.2)
    significant_vectors = vectors[significant_mask]
    
    if len(significant_vectors) < 2:
        return False
    
    # Normalize significant vectors
    significant_vectors = significant_vectors / np.linalg.norm(significant_vectors, axis=1)[:, np.newaxis]
    
    # Calculate angles between major segments
    angles = []
    for i in range(len(significant_vectors)-1):
        dot_product = np.dot(significant_vectors[i], significant_vectors[i+1])
        angle = np.arccos(np.clip(dot_product, -1.0, 1.0)) * 180 / np.pi
        angles.append(angle)
    
    if not angles:
        return False
    
    max_angle = max(angles)
    print(f"Max angle between major segments: {max_angle}")
    
    # Look for angles close to 90 degrees (typical for L-shaped bends)
    return abs(max_angle - 90) < 30  # Detect angles between 60 and 120 degrees

def split_at_bend(polygon):
    """
    Optimized polygon splitting.
    """
    coords = np.array(polygon.exterior.coords)
    vectors = np.diff(coords, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    vectors = vectors / lengths[:, np.newaxis]
    
    dot_products = np.sum(vectors[:-1] * vectors[1:], axis=1)
    angles = np.arccos(np.clip(dot_products, -1.0, 1.0)) * 180 / np.pi
    
    bend_idx = np.argmax(angles) + 1
    
    # Create polygons directly without buffering
    points1 = coords[:bend_idx + 2]
    points2 = coords[bend_idx:]
    
    # Create polygons directly without convex hull
    poly1 = Polygon(points1)
    poly2 = Polygon(points2)
    
    # If either polygon is invalid, try to fix it
    if not poly1.is_valid or not poly2.is_valid:
        # Try using the original polygon's buffer to create valid parts
        line1 = LineString(points1)
        line2 = LineString(points2)
        buffer_distance = polygon.area / (2 * polygon.length)
        poly1 = line1.buffer(buffer_distance)
        poly2 = line2.buffer(buffer_distance)
    
    return poly1, poly2

def create_optimal_envelope(polygon, padding=0, min_ratio=None, cap_style='square'):
    """
    Optimized envelope creation with bend handling.
    """
    if polygon is None or not polygon.is_valid:
        return None
    
    # First check for major bends before any other processing
    if polygon.area / polygon.convex_hull.area < 0.98:
        has_bend = detect_bend(polygon)
        print(f"Convexity ratio: {polygon.area / polygon.convex_hull.area}, Has bend: {has_bend}")
        if has_bend:
            part1, part2 = split_at_bend(polygon)
            envelope1 = create_optimal_envelope(part1, padding, min_ratio, cap_style)
            envelope2 = create_optimal_envelope(part2, padding, min_ratio, cap_style)
            if envelope1 and envelope2:
                return unary_union([envelope1, envelope2])
            else:
                print("Splitting failed, using original polygon")
                return polygon.minimum_rotated_rectangle
    
    # Get the minimum rotated rectangle and continue with regular envelope creation
    min_rect = polygon.minimum_rotated_rectangle
    min_rect_coords = np.array(min_rect.exterior.coords)
    
    # Calculate the orientation from the minimum rotated rectangle
    edges = min_rect_coords[1:] - min_rect_coords[:-1]
    edge_lengths = np.sqrt(np.sum(edges**2, axis=1))
    
    # Check ratio if min_ratio is not None
    if min_ratio is not None:
        length = max(edge_lengths)
        width = min(edge_lengths)
        ratio = length / width if width > 0 else float('inf')
        if ratio < min_ratio:
            return polygon
    
    longest_idx = np.argmax(edge_lengths)
    
    # Get the exact direction from the longest edge
    direction = edges[longest_idx] / edge_lengths[longest_idx]
    perpendicular = np.array([-direction[1], direction[0]])
    
    center = np.array([polygon.centroid.x, polygon.centroid.y])
    original_coords = np.array(polygon.exterior.coords)
    coords_centered = original_coords - center
    
    # Calculate dimensions
    proj_main = np.dot(coords_centered, direction)
    proj_perp = np.dot(coords_centered, perpendicular)
    
    half_width = (np.max(proj_main) - np.min(proj_main)) / 2 + padding
    half_height = (np.max(proj_perp) - np.min(proj_perp)) / 2 + padding
    
    if cap_style == 'round':
        # Create a rectangle slightly shorter than the full length
        rect_width = half_width - half_height  # Reduce rectangle width by radius
        rect_corners = [
            center + rect_width * direction + half_height * perpendicular,
            center + rect_width * direction - half_height * perpendicular,
            center - rect_width * direction - half_height * perpendicular,
            center - rect_width * direction + half_height * perpendicular
        ]
        rect = Polygon(rect_corners)
        
        # Create circles at the ends
        right_circle = Point(center + rect_width * direction).buffer(half_height)
        left_circle = Point(center - rect_width * direction).buffer(half_height)
        
        # Union of rectangle and circles
        return unary_union([rect, right_circle, left_circle])
    else:  # square ends (default)
        corners = [
            center + half_width * direction + half_height * perpendicular,
            center + half_width * direction - half_height * perpendicular,
            center - half_width * direction - half_height * perpendicular,
            center - half_width * direction + half_height * perpendicular
        ]
        return Polygon(corners)