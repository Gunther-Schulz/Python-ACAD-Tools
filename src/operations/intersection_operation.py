import geopandas as gpd
from src.utils import log_info, log_warning, log_error
import traceback
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry
from src.operations.common_operations import *
from src.utils import log_info, log_warning, log_error
import geopandas as gpd
import traceback


def create_intersection_layer(all_layers, project_settings, crs, layer_name, operation):
    return _create_intersection_overlay_layer(all_layers, project_settings, crs, layer_name, operation, 'intersection')




def _create_intersection_overlay_layer(all_layers, project_settings, crs, layer_name, operation, overlay_type):
    log_info(f"Creating {overlay_type} layer: {layer_name}")
    log_info(f"Operation details: {operation}")
    
    overlay_layers = operation.get('layers', [])
    make_valid = operation.get('makeValid', True)
    
    if not overlay_layers:
        log_warning(f"No overlay layers specified for {layer_name}")
        return
    
    base_geometry = all_layers.get(layer_name)
    if base_geometry is None:
        log_warning(f"Base layer '{layer_name}' not found for {overlay_type} operation")
        return
    
    if make_valid:
        base_geometry.geometry = base_geometry.geometry.apply(make_valid_geometry)
        base_geometry = base_geometry[base_geometry.geometry.notna()]
    
    combined_overlay_geometry = None
    for layer_info in overlay_layers:
        overlay_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if overlay_layer_name is None:
            continue

        overlay_geometry = _get_filtered_geometry(all_layers, project_settings, crs, overlay_layer_name, values)
        if overlay_geometry is None:
            continue

        if make_valid:
            overlay_geometry = make_valid_geometry(overlay_geometry)
            if overlay_geometry is None:
                continue

        if combined_overlay_geometry is None:
            combined_overlay_geometry = overlay_geometry
        else:
            combined_overlay_geometry = combined_overlay_geometry.union(overlay_geometry)

    if combined_overlay_geometry is None:
        log_warning(format_operation_warning(
            layer_name,
            overlay_type,
            "No valid overlay geometries found"
        ))
        return
    try:
        if overlay_type == 'difference':
            result_geometry = base_geometry.geometry.difference(combined_overlay_geometry)
        elif overlay_type == 'intersection':
            result_parts_with_attrs = []
            for idx, row in base_geometry.iterrows():
                intersected_geom = row.geometry.intersection(combined_overlay_geometry)
                if not intersected_geom.is_empty:
                    result_parts_with_attrs.append({
                        'geometry': intersected_geom,
                        'attrs': {col: row[col] for col in base_geometry.columns if col != 'geometry'}
                    })
            
            if result_parts_with_attrs:
                result_geometry = gpd.GeoDataFrame(
                    geometry=[part['geometry'] for part in result_parts_with_attrs],
                    data=[part['attrs'] for part in result_parts_with_attrs],
                    crs=crs
                )
            else:
                result_geometry = gpd.GeoDataFrame(geometry=[], crs=crs)
        else:
            log_warning(f"Unsupported overlay type: {overlay_type}")
            return
        
        # Remove lines and points from the result
        result_geometry = remove_geometry_types(result_geometry, remove_lines=True, remove_points=True)
        
        # Remove empty geometries
        if isinstance(result_geometry, gpd.GeoDataFrame):
            result_geometry = result_geometry[~result_geometry.geometry.is_empty]
        else:
            result_geometry = result_geometry[~result_geometry.is_empty]
        
        log_info(f"Applied {overlay_type} operation, removed lines and points, and removed empty geometries")
    except Exception as e:
        log_error(f"Error during {overlay_type} operation: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return

    if make_valid:
        if isinstance(result_geometry, gpd.GeoDataFrame):
            result_geometry['geometry'] = result_geometry['geometry'].apply(make_valid_geometry)
            result_geometry = result_geometry[result_geometry['geometry'].notna()]
        else:
            result_geometry = result_geometry.apply(make_valid_geometry)
            result_geometry = result_geometry[result_geometry.notna()]

    # Create a new GeoDataFrame with the resulting geometries and explode to singlepart
    if isinstance(result_geometry, gpd.GeoDataFrame):
        result_gdf = result_geometry
    elif isinstance(result_geometry, gpd.GeoSeries):
        result_gdf = gpd.GeoDataFrame(geometry=result_geometry, crs=base_geometry.crs)
    else:
        result_gdf = gpd.GeoDataFrame(geometry=[result_geometry], crs=base_geometry.crs)
    
    result_gdf = explode_to_singlepart(result_gdf)
    
    # Remove empty geometries again after exploding
    result_gdf = result_gdf[~result_gdf.geometry.is_empty]
    
    if result_gdf.empty:
        log_warning(f"No valid geometry created for {overlay_type} layer: {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=base_geometry.crs)
    else:
        all_layers[layer_name] = result_gdf
        log_info(f"Created {overlay_type} layer: {layer_name} with {len(result_gdf)} geometries")

    return all_layers[layer_name]






