import geopandas as gpd
import numpy as np
from shapely.geometry import box, MultiPolygon, Polygon, LineString, Point
from shapely.ops import unary_union
from src.utils import log_info, log_warning, log_debug
from src.operations.common_operations import _process_layer_info, format_operation_warning
from scipy.spatial import distance

def create_envelope_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Creates a minimum-area bounding rectangle (envelope) for each input geometry.
    """
    log_debug(f"Creating envelope layer: {layer_name}")

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
        source_layer_name, values, column_name = _process_layer_info(all_layers, project_settings, crs, layer_info)
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

    log_debug(f"Created envelope layer: {layer_name} with {len(result_geometries)} envelopes")
    return result_gdf

def detect_bend(polygon):
    """
    Simplified bend detection using minimum rotated rectangle.
    """
    min_rect = polygon.minimum_rotated_rectangle
    area_ratio = polygon.area / min_rect.area
    return area_ratio < 0.8

def split_at_bend(polygon):
    """
    Split polygon perpendicular to the segments at the bend point.
    """
    # Get polygon coordinates
    coords = np.array(polygon.exterior.coords)
    vectors = np.diff(coords, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    vectors = vectors / lengths[:, np.newaxis]

    # Calculate angles between segments
    dot_products = np.sum(vectors[:-1] * vectors[1:], axis=1)
    angles = np.arccos(np.clip(dot_products, -1.0, 1.0)) * 180 / np.pi

    # Find the bend point
    bend_idx = np.argmax(angles)
    bend_point = coords[bend_idx + 1]

    # Get directions of segments before and after bend
    dir_before = vectors[bend_idx]
    dir_after = vectors[bend_idx + 1]

    # Calculate perpendicular direction at bend (average of perpendiculars)
    perp_before = np.array([-dir_before[1], dir_before[0]])
    perp_after = np.array([-dir_after[1], dir_after[0]])
    split_direction = (perp_before + perp_after) / 2
    split_direction = split_direction / np.linalg.norm(split_direction)

    # Create a line perpendicular to the bend direction
    line_length = polygon.bounds[2] - polygon.bounds[0] + polygon.bounds[3] - polygon.bounds[1]
    split_line = LineString([
        bend_point - line_length * split_direction,
        bend_point + line_length * split_direction
    ])

    # Split the polygon with this line
    split_poly = polygon.difference(split_line.buffer(0.1))

    if isinstance(split_poly, MultiPolygon):
        polys = list(split_poly.geoms)
        if len(polys) >= 2:
            return polys[0], polys[1]

    # Fallback: split along the perpendicular of the average direction
    return polygon.intersection(box(*polygon.bounds[:2], bend_point[0], polygon.bounds[3])), \
           polygon.intersection(box(bend_point[0], polygon.bounds[1], *polygon.bounds[2:]))

def create_optimal_envelope(polygon, padding=0, min_ratio=None, cap_style='square', recursion_depth=0):
    """
    Optimized envelope creation with bend handling.
    """
    if polygon is None or not polygon.is_valid:
        return None

    # First check min_ratio before doing any bend processing
    min_rect = polygon.minimum_rotated_rectangle
    rect_coords = np.array(min_rect.exterior.coords)
    edges = rect_coords[1:] - rect_coords[:-1]
    edge_lengths = np.sqrt(np.sum(edges**2, axis=1))

    if min_ratio is not None:
        length = max(edge_lengths)
        width = min(edge_lengths)
        ratio = length / width if width > 0 else float('inf')
        if ratio < min_ratio:
            return polygon  # Return original polygon if it doesn't meet min_ratio

    # Limit recursion depth and minimum size
    if recursion_depth > 2 or polygon.area < 1e-6:
        return polygon.minimum_rotated_rectangle

    if detect_bend(polygon):
        part1, part2 = split_at_bend(polygon)
        if part1.is_valid and part2.is_valid:
            envelope1 = create_optimal_envelope(part1, padding, min_ratio, cap_style, recursion_depth + 1)
            envelope2 = create_optimal_envelope(part2, padding, min_ratio, cap_style, recursion_depth + 1)
            if envelope1 and envelope2:
                return unary_union([envelope1, envelope2])

    # Continue with regular envelope creation
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
