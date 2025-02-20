"""Dissolve operation module."""

import geopandas as gpd
from shapely.ops import unary_union
from src.core.utils import log_info, log_warning, log_debug
from src.operations.common_operations import format_operation_warning, explode_to_singlepart, apply_buffer_trick, make_valid_geometry, _merge_close_vertices, snap_vertices_to_grid
import pandas as pd

def create_dissolved_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating dissolved layer: {layer_name}")
    source_layers = operation.get('layers', [])
    if layer_name in all_layers:
        source_layers = [layer_name] + source_layers  # Include existing layer plus specified layers
    
    dissolve_field = operation.get('dissolveField')
    buffer_distance = operation.get('bufferDistance', 0.01)
    use_buffer_trick = operation.get('useBufferTrick', False)
    merge_vertices = operation.get('mergeVertices', False)
    use_double_union = operation.get('useDoubleUnion', True)
    use_asymmetric_buffer = operation.get('useAsymmetricBuffer', False)
    use_snap_to_grid = operation.get('useSnapToGrid', False)
    merge_vertices_tolerance = operation.get('mergeVerticesTolerance', buffer_distance/2)
    grid_size = operation.get('gridSize', buffer_distance/10)
    make_valid = operation.get('makeValid', True)

    combined_gdf = None
    for layer_info in source_layers:
        source_layer_name = layer_info if isinstance(layer_info, str) else layer_info.get('name')
        
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "dissolve",
                f"Source layer '{source_layer_name}' not found or invalid"
            ))
            continue

        layer_geometry = all_layers[source_layer_name]
        if layer_geometry.empty:
            log_warning(format_operation_warning(
                layer_name,
                "dissolve",
                f"Source layer '{source_layer_name}' is empty"
            ))
            continue

        if combined_gdf is None:
            combined_gdf = layer_geometry
        else:
            combined_gdf = pd.concat([combined_gdf, layer_geometry], ignore_index=True)

    if combined_gdf is None or combined_gdf.empty:
        log_warning(format_operation_warning(
            layer_name,
            "dissolve",
            "No valid source geometries found"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return all_layers[layer_name]

    if make_valid and combined_gdf is not None:
        combined_gdf.geometry = combined_gdf.geometry.apply(make_valid_geometry)
        combined_gdf = combined_gdf[combined_gdf.geometry.notna()]

    if use_buffer_trick:
        if merge_vertices:
            combined_gdf.geometry = combined_gdf.geometry.apply(
                lambda geom: _merge_close_vertices(all_layers, project_settings, crs, geom, tolerance=merge_vertices_tolerance)
            )
            combined_gdf = combined_gdf[combined_gdf.geometry.notna()]
        
        if use_asymmetric_buffer:
            # Apply asymmetric buffer trick
            initial_buffer = buffer_distance * 1.1
            reverse_buffer = -(buffer_distance * 0.9)
            combined_gdf.geometry = combined_gdf.geometry.buffer(initial_buffer, join_style=2)
            combined_gdf.geometry = combined_gdf.geometry.buffer(reverse_buffer, join_style=2)
        else:
            # Apply regular buffer trick
            combined_gdf.geometry = apply_buffer_trick(combined_gdf.geometry, buffer_distance)

        if use_snap_to_grid:
            combined_gdf.geometry = combined_gdf.geometry.apply(
                lambda geom: snap_vertices_to_grid(geom, grid_size)
            )

    if dissolve_field and dissolve_field in combined_gdf.columns:
        dissolved = gpd.GeoDataFrame(geometry=combined_gdf.geometry, data=combined_gdf[dissolve_field]).dissolve(by=dissolve_field, as_index=False)
    else:
        # First unary_union
        dissolved = gpd.GeoDataFrame(geometry=[unary_union(combined_gdf.geometry)])
        # Second unary_union if enabled
        if use_double_union:
            dissolved = gpd.GeoDataFrame(geometry=[unary_union(dissolved.geometry)])
        
        if make_valid:
            dissolved.geometry = dissolved.geometry.make_valid()
        dissolved = dissolved[~dissolved.is_empty]
        dissolved = explode_to_singlepart(dissolved)

    # Remove empty geometries after processing
    dissolved = dissolved[~dissolved.geometry.is_empty]

    if dissolved.empty:
        log_warning(f"No valid geometry created for dissolved layer: {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
    else:
        all_layers[layer_name] = dissolved.set_crs(crs)
        log_debug(f"Created dissolved layer: {layer_name} with {len(dissolved)} features")

    return all_layers[layer_name]
