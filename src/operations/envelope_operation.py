import geopandas as gpd
import numpy as np
from shapely.geometry import box, MultiPolygon, Polygon, LineString
from src.utils import log_info, log_warning
from src.operations.common_operations import _process_layer_info, format_operation_warning

def create_envelope_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Creates a minimum-area bounding rectangle (envelope) for each input geometry.
    """
    log_info(f"Creating envelope layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]
    
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
                # Handle each part of a MultiPolygon separately
                for part in geom.geoms:
                    envelope = create_optimal_envelope(part)
                    if envelope:
                        result_geometries.append(envelope)
            else:
                envelope = create_optimal_envelope(geom)
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

def create_optimal_envelope(polygon):
    """Create an envelope with optimal orientation for the polygon."""
    if polygon is None:
        return None
    
    # First get the minimum rotated rectangle
    min_rect = polygon.minimum_rotated_rectangle
    min_rect_coords = np.array(min_rect.exterior.coords)
    
    # Calculate the orientation from the minimum rotated rectangle
    edges = min_rect_coords[1:] - min_rect_coords[:-1]
    edge_lengths = np.sqrt(np.sum(edges**2, axis=1))
    longest_idx = np.argmax(edge_lengths)
    
    # Get the exact direction from the longest edge of the minimum rotated rectangle
    direction = edges[longest_idx] / edge_lengths[longest_idx]
    perpendicular = np.array([-direction[1], direction[0]])
    
    # Now create our envelope using this exact orientation
    # but with dimensions from the original polygon
    center = np.array([polygon.centroid.x, polygon.centroid.y])
    
    # Project original polygon onto these directions
    original_coords = np.array(polygon.exterior.coords)
    coords_centered = original_coords - center
    
    # Calculate exact dimensions needed
    proj_main = np.dot(coords_centered, direction)
    proj_perp = np.dot(coords_centered, perpendicular)
    
    half_width = (np.max(proj_main) - np.min(proj_main)) / 2
    half_height = (np.max(proj_perp) - np.min(proj_perp)) / 2
    
    # Create envelope corners using the minimum rotated rectangle's orientation
    corners = [
        center + half_width * direction + half_height * perpendicular,
        center + half_width * direction - half_height * perpendicular,
        center - half_width * direction - half_height * perpendicular,
        center - half_width * direction + half_height * perpendicular
    ]
    
    return Polygon(corners)