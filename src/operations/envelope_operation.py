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
    
    def find_local_groups(polygons, max_distance=100):
        """Group polygons based on proximity and similar alignment."""
        if len(polygons) < 2:
            return [[0]] if len(polygons) == 1 else []
            
        centroids = np.array([[p.centroid.x, p.centroid.y] for p in polygons])
        groups = []
        unassigned = set(range(len(polygons)))
        
        # Sort points by x coordinate to maintain sequence
        sorted_indices = np.argsort(centroids[:, 0])
        sequence = {idx: i for i, idx in enumerate(sorted_indices)}
        
        while unassigned:
            current = unassigned.pop()
            current_group = [current]
            
            # Find nearby points considering sequence
            for idx in list(unassigned):
                dist = distance.euclidean(centroids[current], centroids[idx])
                if dist <= max_distance:
                    # Check sequence continuity
                    if abs(sequence[current] - sequence[idx]) <= 2:  # Allow gaps of 1 point
                        current_group.append(idx)
                        unassigned.remove(idx)
            
            groups.append(sorted(current_group, key=lambda x: sequence[x]))
        
        return groups
    
    def find_alignment_from_centroids(polygons):
        """Find the principal direction from the centroids of geometries."""
        if len(polygons) < 2:
            return None
            
        centroids = np.array([[p.centroid.x, p.centroid.y] for p in polygons])
        
        # Sort centroids by x coordinate to maintain sequence
        sort_idx = np.argsort(centroids[:, 0])
        centroids = centroids[sort_idx]
        
        # For two points, try to use context from nearby groups
        if len(centroids) == 2:
            # Calculate direct vector between points
            direct_vec = centroids[1] - centroids[0]
            direct_vec = direct_vec / np.linalg.norm(direct_vec)
            
            # Try to find nearby groups for context
            nearby_centroids = []
            for poly in all_polygons:  # Now all_polygons is in scope
                if poly not in polygons:
                    cent = np.array([poly.centroid.x, poly.centroid.y])
                    min_dist = min(np.linalg.norm(cent - centroids[0]), 
                                 np.linalg.norm(cent - centroids[1]))
                    if min_dist < 150:  # Increased search radius
                        nearby_centroids.append(cent)
            
            if nearby_centroids:
                # Include nearby points in direction calculation
                all_points = np.vstack([centroids] + nearby_centroids)
                
                # Use linear regression with all points
                x = all_points[:, 0]
                y = all_points[:, 1]
                A = np.vstack([x, np.ones(len(x))]).T
                m, c = np.linalg.lstsq(A, y, rcond=None)[0]
                
                # Convert slope to direction vector
                context_vec = np.array([1, m])
                context_vec = context_vec / np.linalg.norm(context_vec)
                
                # Blend between direct vector and context vector
                dist = np.linalg.norm(centroids[1] - centroids[0])
                weight = min(1.0, dist / 100.0)  # More weight to context for distant points
                final_vec = weight * context_vec + (1 - weight) * direct_vec
                return final_vec / np.linalg.norm(final_vec)
            
            return direct_vec
        
        # For more points, use standard linear regression
        x = centroids[:, 0]
        y = centroids[:, 1]
        A = np.vstack([x, np.ones(len(x))]).T
        m, c = np.linalg.lstsq(A, y, rcond=None)[0]
        direction = np.array([1, m])
        return direction / np.linalg.norm(direction)
    
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