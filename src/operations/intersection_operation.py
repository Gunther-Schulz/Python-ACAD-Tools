import geopandas as gpd
from src.utils import log_info, log_warning, log_error
import traceback
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, _clean_geometry
from src.operations.common_operations import *
from src.utils import log_info, log_warning, log_error
import geopandas as gpd
import traceback
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, _clean_geometry

def create_intersection_layer(all_layers, project_settings, crs, layer_name, operation):
    return _create_intersection_overlay_layer(all_layers, project_settings, crs, layer_name, operation, 'intersection')




def _create_intersection_overlay_layer(all_layers, project_settings, crs, layer_name, operation, overlay_type):
    log_info(f"Creating {overlay_type} layer: {layer_name}")
    log_info(f"Operation details: {operation}")
    
    overlay_layers = operation.get('layers', [])
    
    if not overlay_layers:
        log_warning(f"No overlay layers specified for {layer_name}")
        return
    
    base_geometry = all_layers.get(layer_name)
    if base_geometry is None:
        log_warning(f"Base layer '{layer_name}' not found for {overlay_type} operation")
        return
    
    combined_overlay_geometry = None
    for layer_info in overlay_layers:
        overlay_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if overlay_layer_name is None:
            continue

        overlay_geometry = _get_filtered_geometry(all_layers, project_settings, crs, overlay_layer_name, values)
        if overlay_geometry is None:
            continue

        if combined_overlay_geometry is None:
            combined_overlay_geometry = overlay_geometry
        else:
            combined_overlay_geometry = combined_overlay_geometry.union(overlay_geometry)

    if combined_overlay_geometry is None:
        log_warning(f"No valid overlay geometries found for layer '{layer_name}'")
        return

    try:
        if overlay_type == 'difference':
            result_geometry = base_geometry.geometry.difference(combined_overlay_geometry)
        elif overlay_type == 'intersection':
            result_geometry = base_geometry.geometry.intersection(combined_overlay_geometry)
        else:
            log_warning(f"Unsupported overlay type: {overlay_type}")
            return
        
        # Apply a series of cleaning operations
        result_geometry = _clean_geometry(all_layers, project_settings, crs, result_geometry)
        
        log_info(f"Applied {overlay_type} operation and cleaned up results")
    except Exception as e:
        log_error(f"Error during {overlay_type} operation: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return

    # Check if result_geometry is empty
    if result_geometry.empty:
        log_warning(f"No valid geometry created for {overlay_type} layer: {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=base_geometry.crs)
    else:
        # Create a new GeoDataFrame with the resulting geometries and explode to singlepart
        result_gdf = explode_to_singlepart(gpd.GeoDataFrame(geometry=result_geometry, crs=base_geometry.crs))
        all_layers[layer_name] = result_gdf
        log_info(f"Created {overlay_type} layer: {layer_name} with {len(result_gdf)} geometries")

    return all_layers[layer_name]





