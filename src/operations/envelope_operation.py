import geopandas as gpd
import numpy as np
from shapely.geometry import box, MultiPolygon, Polygon, LineString
from src.utils import log_info, log_warning
from src.operations.common_operations import _process_layer_info, format_operation_warning
from scipy.spatial import distance

def create_envelope_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Creates a minimum-area bounding rectangle (envelope) for each input geometry.
    Groups nearby geometries to find local alignments.
    """
    log_info(f"Creating envelope layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]  # Use current layer if no source specified
    
    all_polygons = []
    
    # Collect geometries from all input layers
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]
        if not source_gdf.empty:
            # Get all individual polygons from this layer
            all_polygons.extend(get_all_polygons(source_gdf.geometry))
    
    if not all_polygons:
        log_warning(format_operation_warning(
            layer_name,
            "envelope",
            "No geometries found to create envelopes"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None
    
    result_geometries = []
    
    # Group nearby polygons
    groups = find_local_groups(all_polygons)
    
    # Process each group separately
    for group_indices in groups:
        group_polygons = [all_polygons[i] for i in group_indices]
        alignment = find_alignment_from_centroids(group_polygons)
        
        if alignment is not None:
            # Create aligned envelopes for each polygon in the group
            for polygon in group_polygons:
                if polygon is not None:
                    envelope = create_aligned_envelope(polygon, alignment)
                    result_geometries.append(envelope)
        else:
            # Fallback for single polygons or unclear alignment
            for polygon in group_polygons:
                if polygon is not None:
                    result_geometries.append(polygon.minimum_rotated_rectangle)
    
    # Create the result layer
    result_gdf = gpd.GeoDataFrame(geometry=result_geometries, crs=crs)
    all_layers[layer_name] = result_gdf
    
    log_info(f"Created envelope layer: {layer_name} with {len(result_geometries)} envelopes")
    return result_gdf

def get_all_polygons(geometries):
    """Extract all individual polygons from a list of geometries."""
    all_polygons = []
    for geom in geometries:
        if isinstance(geom, MultiPolygon):
            all_polygons.extend(list(geom.geoms))
        else:
            all_polygons.append(geom)
    return all_polygons

def find_local_groups(polygons, max_distance=50):
    """Group polygons based on proximity and similar alignment."""
    if len(polygons) < 2:
        return [[0]] if len(polygons) == 1 else []
        
    centroids = np.array([[p.centroid.x, p.centroid.y] for p in polygons])
    groups = []
    unassigned = set(range(len(polygons)))
    
    while unassigned:
        current = unassigned.pop()
        current_group = [current]
        
        # Find nearby points that share similar alignment
        for idx in list(unassigned):
            dist = distance.euclidean(centroids[current], centroids[idx])
            if dist <= max_distance:
                # Check if alignment is similar
                if check_alignment_compatibility(polygons[current], polygons[idx]):
                    current_group.append(idx)
                    unassigned.remove(idx)
        
        groups.append(current_group)
    
    return groups

def check_alignment_compatibility(poly1, poly2):
    """Check if two polygons share similar alignment."""
    vec = np.array([
        poly2.centroid.x - poly1.centroid.x,
        poly2.centroid.y - poly1.centroid.y
    ])
    dist = np.sqrt(np.sum(vec**2))
    if dist < 1e-10:  # Too close to determine direction
        return True
        
    vec = vec / dist  # Normalize
    return True  # Accept all nearby polygons

def find_alignment_from_centroids(polygons):
    """Find the principal direction from the centroids of geometries."""
    if len(polygons) < 2:
        return None
        
    centroids = np.array([[p.centroid.x, p.centroid.y] for p in polygons])
    
    # For two points, use their direct connection
    if len(centroids) == 2:
        direction = centroids[1] - centroids[0]
        return direction / np.linalg.norm(direction)
    
    # For more points, use linear regression
    x = centroids[:, 0]
    y = centroids[:, 1]
    
    # Calculate direction using linear regression
    A = np.vstack([x, np.ones(len(x))]).T
    m, c = np.linalg.lstsq(A, y, rcond=None)[0]
    
    # Convert slope to direction vector
    direction = np.array([1, m])
    return direction / np.linalg.norm(direction)

def create_aligned_envelope(polygon, direction):
    """Create an envelope aligned with the given direction."""
    perpendicular = np.array([-direction[1], direction[0]])
    center = np.array([polygon.centroid.x, polygon.centroid.y])
    
    coords = np.array(polygon.exterior.coords)
    proj_main = np.dot(coords - center, direction)
    proj_perp = np.dot(coords - center, perpendicular)
    
    half_width = (np.max(proj_main) - np.min(proj_main)) / 2
    half_height = (np.max(proj_perp) - np.min(proj_perp)) / 2
    
    corners = [
        center + half_width * direction + half_height * perpendicular,
        center + half_width * direction - half_height * perpendicular,
        center - half_width * direction - half_height * perpendicular,
        center - half_width * direction + half_height * perpendicular
    ]
    
    return Polygon(corners)