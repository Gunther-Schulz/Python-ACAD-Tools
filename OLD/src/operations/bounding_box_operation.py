import geopandas as gpd
from shapely.geometry import Polygon, box
from src.utils import log_info, log_warning, log_debug
from src.operations.common_operations import _process_layer_info, format_operation_warning

def create_bounding_box_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Creates a bounding box (rectangle) that encompasses all input geometries.
    """
    log_debug(f"Creating bounding box layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]  # Use the current layer if no source specified
    
    # Optional padding around the bounding box
    padding = operation.get('padding', 0)
    
    # Collect all bounds
    bounds = None
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]
        
        if source_gdf.empty:
            continue
            
        # Get the total bounds of the layer (minx, miny, maxx, maxy)
        layer_bounds = source_gdf.total_bounds
        
        if bounds is None:
            bounds = layer_bounds
        else:
            # Update bounds to include this layer
            bounds = (
                min(bounds[0], layer_bounds[0]),  # minx
                min(bounds[1], layer_bounds[1]),  # miny
                max(bounds[2], layer_bounds[2]),  # maxx
                max(bounds[3], layer_bounds[3])   # maxy
            )
    
    if bounds is None:
        log_warning(format_operation_warning(
            layer_name,
            "bounding-box",
            "No geometries found to create bounding box"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None
    
    # Apply padding if specified
    if padding:
        bounds = (
            bounds[0] - padding,  # minx
            bounds[1] - padding,  # miny
            bounds[2] + padding,  # maxx
            bounds[3] + padding   # maxy
        )
    
    # Create the bounding box polygon
    bbox = box(*bounds)
    
    # Create GeoDataFrame with the result
    result_gdf = gpd.GeoDataFrame(geometry=[bbox], crs=crs)
    all_layers[layer_name] = result_gdf
    
    log_debug(f"Created bounding box layer: {layer_name}")
    return result_gdf 