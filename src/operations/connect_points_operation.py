import geopandas as gpd
from shapely.geometry import Point, LineString, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, format_operation_warning
import numpy as np
from scipy.spatial.distance import cdist

def create_connect_points_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating connect points layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]  # Use the current layer if no source specified
    
    all_points = []
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]
        
        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            if isinstance(geom, Point):
                all_points.append((geom.x, geom.y))
            elif isinstance(geom, MultiPoint):
                all_points.extend([(p.x, p.y) for p in geom.geoms])
    
    if not all_points:
        log_warning(format_operation_warning(
            layer_name,
            "connect-points",
            "No points found to connect"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None
    
    if len(all_points) == 1:
        # If there's only one point, we can't create a line
        log_warning(format_operation_warning(
            layer_name,
            "connect-points",
            "Only one point found - cannot create connecting line"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None
    
    # Convert points to numpy array for efficient distance calculation
    points_array = np.array(all_points)
    
    # Start with the first point
    remaining_points = list(range(1, len(points_array)))
    path = [0]
    
    # Find nearest neighbor for each point
    while remaining_points:
        current = path[-1]
        if not remaining_points:
            break
            
        # Calculate distances from current point to all remaining points
        current_point = points_array[current].reshape(1, -1)
        remaining_points_array = points_array[remaining_points]
        
        distances = cdist(current_point, remaining_points_array)[0]
        
        # Find the index of the nearest point among remaining points
        nearest_idx = np.argmin(distances)
        next_point_idx = remaining_points[nearest_idx]
        
        # Add the nearest point to the path and remove it from remaining points
        path.append(next_point_idx)
        remaining_points.remove(next_point_idx)
    
    # Create the connected line (no need to close the path)
    connected_points = [points_array[i] for i in path]
    line = LineString(connected_points)
    
    # Create GeoDataFrame with the result
    result_gdf = gpd.GeoDataFrame(geometry=[line], crs=crs)
    all_layers[layer_name] = result_gdf
    
    log_info(f"Created connect points layer: {layer_name} connecting {len(all_points)} points")
    return result_gdf 