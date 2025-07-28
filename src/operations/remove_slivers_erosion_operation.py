#!/usr/bin/env python3

import geopandas as gpd
from src.operations.buffer_operation import create_buffer_layer
from src.operations.common_operations import ensure_geodataframe
from src.utils import log_info, log_warning, log_error, log_debug

def create_remove_slivers_erosion_layer(all_layers, project_settings, crs, layer_name, operation):
    """Remove slivers using erosion/dilation technique with mitre joins to preserve sharp corners."""

    # Get parameters
    erosion_distance = operation.get('erosionDistance', 0.1)  # How much to erode

    log_debug(f"=== STARTING removeSliversByErosion operation for layer: {layer_name} ===")
    log_debug(f"Using erosion distance: {erosion_distance} (removes features thinner than {erosion_distance * 2})")

    # Get the current layer
    if layer_name not in all_layers:
        log_warning(f"Layer '{layer_name}' not found for sliver removal by erosion")
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    input_gdf = all_layers[layer_name]

    if input_gdf.empty:
        log_warning(f"No geometries found in layer '{layer_name}' for sliver removal")
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    original_count = len(input_gdf)

    # Step 1: Erosion (negative buffer) - removes thin features
    erosion_operation = {
        'distance': -erosion_distance,
        'joinStyle': 'mitre',
        'capStyle': 'flat'
    }

    log_debug(f"Step 1: Eroding by {erosion_distance} to remove thin features")

    # Temporarily update the layer for the erosion step
    all_layers[layer_name] = input_gdf
    eroded_result = create_buffer_layer(all_layers, project_settings, crs, layer_name, erosion_operation)

    if eroded_result.empty:
        log_warning(f"All geometries removed during erosion step - erosion distance too large")
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    # Step 2: Dilation (positive buffer) - restores size but keeps thin features removed
    dilation_operation = {
        'distance': erosion_distance,
        'joinStyle': 'mitre',
        'capStyle': 'flat'
    }

    log_debug(f"Step 2: Dilating by {erosion_distance} to restore original size")

    # Update the layer with eroded result for dilation step
    all_layers[layer_name] = eroded_result
    final_result = create_buffer_layer(all_layers, project_settings, crs, layer_name, dilation_operation)

    # Restore original layer in case other operations need it
    all_layers[layer_name] = input_gdf

    final_count = len(final_result) if not final_result.empty else 0
    features_removed = original_count - final_count

    # Only show message if features were actually removed
    if features_removed > 0:
        log_info(f"removeSliversByErosion for '{layer_name}': {features_removed} features removed, {final_count} remaining")

    log_debug(f"=== COMPLETED removeSliversByErosion: {features_removed} features removed, {final_count} features remaining ===")

    if final_result.empty:
        log_warning(f"No valid geometries after sliver removal for layer '{layer_name}'")
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    return ensure_geodataframe(all_layers, project_settings, crs, layer_name, final_result)
