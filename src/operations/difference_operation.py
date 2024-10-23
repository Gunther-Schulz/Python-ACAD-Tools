import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from shapely.ops import unary_union
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, _remove_empty_geometries, _create_generic_overlay_layer, apply_buffer_trick, _clean_geometry, _remove_thin_growths, _merge_close_vertices, explode_to_singlepart
from src.operations.intersection_operation import _create_intersection_overlay_layer

def create_difference_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating difference layer: {layer_name}")
    overlay_layers = operation.get('layers', [])
    manual_reverse = operation.get('reverseDifference')
    buffer_distance = operation.get('bufferDistance', 0.001)  # Increased default value
    thin_growth_threshold = operation.get('thinGrowthThreshold', 0.001)
    merge_vertices_tolerance = operation.get('mergeVerticesTolerance', 0.0001)
    use_buffer_trick = operation.get('useBufferTrick', False)
    
    base_geometry = all_layers.get(layer_name)
    if base_geometry is None:
        log_warning(f"Base layer '{layer_name}' not found for difference operation")
        return None

    base_geometry = _remove_empty_geometries(all_layers, project_settings, crs, layer_name, base_geometry)
    if base_geometry is None or base_geometry.empty:
        log_warning(f"No valid geometries in base layer '{layer_name}' after removing empty geometries")
        return None

    overlay_geometry = None
    for layer_info in overlay_layers:
        overlay_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if overlay_layer_name is None:
            continue

        layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, overlay_layer_name, values)
        if layer_geometry is None:
            continue

        layer_geometry = _remove_empty_geometries(all_layers, project_settings, crs, overlay_layer_name, layer_geometry)
        if layer_geometry is None:
            continue

        if overlay_geometry is None:
            overlay_geometry = layer_geometry
        else:
            overlay_geometry = overlay_geometry.union(layer_geometry)
    if overlay_geometry is None:
        log_warning(f"No valid overlay geometry found for layer {layer_name}")
        return None

    # Use manual override if provided, otherwise use auto-detection
    if isinstance(manual_reverse, bool):
        reverse_difference = manual_reverse
        log_info(f"Using manual override for reverse_difference: {reverse_difference}")
    else:
        reverse_difference = _should_reverse_difference(all_layers, project_settings, crs, base_geometry, overlay_geometry)
        log_info(f"Auto-detected reverse_difference for {layer_name}: {reverse_difference}")

    if use_buffer_trick:
        # Apply buffer trick to both base and overlay geometries
        base_geometry = apply_buffer_trick(base_geometry, buffer_distance)
        overlay_geometry = apply_buffer_trick(overlay_geometry, buffer_distance)

    # Use base_geometry and overlay_geometry directly
    if reverse_difference:
        result = overlay_geometry.difference(base_geometry)
    else:
        result = base_geometry.difference(overlay_geometry)
    
    if use_buffer_trick:
        # Apply inverse buffer to shrink the result back
        result = apply_buffer_trick(result, -buffer_distance)

    # Convert result to GeoSeries
    if isinstance(result, (Polygon, MultiPolygon, LineString, MultiLineString)):
        result = gpd.GeoSeries([result])
    elif not isinstance(result, gpd.GeoSeries):
        log_warning(f"Unexpected result type: {type(result)}")
        return None

    result = result[~result.is_empty & result.notna()]
    
    if result.empty:
        log_warning(f"Difference operation resulted in empty geometry for layer {layer_name}")
        return None
    
    result_gdf = explode_to_singlepart(gpd.GeoDataFrame(geometry=result, crs=crs))
    if isinstance(base_geometry, gpd.GeoDataFrame):
        for col in base_geometry.columns:
            if col != 'geometry':
                result_gdf[col] = base_geometry[col].iloc[0]

    return result_gdf


def _should_reverse_difference(all_layers, project_settings, crs, base_geometry, overlay_geometry):
        if isinstance(base_geometry, gpd.GeoDataFrame):
            base_geometry = base_geometry.geometry.unary_union
        
        # Ensure we're working with single geometries
        if isinstance(base_geometry, (MultiPolygon, MultiLineString)):
            base_geometry = unary_union(base_geometry)
        if isinstance(overlay_geometry, (MultiPolygon, MultiLineString)):
            overlay_geometry = unary_union(overlay_geometry)
        
        # Check if overlay_geometry is completely within base_geometry
        if overlay_geometry.within(base_geometry):
            return False
        
        # Check if base_geometry is completely within overlay_geometry
        if base_geometry.within(overlay_geometry):
            return True
        
        # Compare areas
        base_area = base_geometry.area
        overlay_area = overlay_geometry.area
        
        # If the overlay area is larger, it's likely a positive buffer, so don't reverse
        if overlay_area > base_area:
            return False
        
        # If the base area is larger, it's likely a negative buffer, so do reverse
        if base_area > overlay_area:
            return True
        
        # If areas are similar, check the intersection
        intersection = base_geometry.intersection(overlay_geometry)
        intersection_area = intersection.area
        
        # If the intersection is closer to the base area, reverse
        if abs(intersection_area - base_area) < abs(intersection_area - overlay_area):
            return True
        
        # Default to not reversing
        return False





