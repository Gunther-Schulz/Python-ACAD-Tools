import geopandas as gpd
from shapely.ops import unary_union
from src.utils import log_info, log_warning
from src.operations.common_operations import explode_to_singlepart, apply_buffer_trick, make_valid_geometry, _merge_close_vertices
import pandas as pd

def create_dissolved_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating dissolved layer: {layer_name}")
    source_layers = operation.get('layers', [layer_name])  # Default to current layer if not specified
    dissolve_field = operation.get('dissolveField')
    buffer_distance = operation.get('bufferDistance', 0.01)
    use_buffer_trick = operation.get('useBufferTrick', False)
    merge_vertices = operation.get('mergeVertices', False)  # Default to False
    double_pass = operation.get('doublePass', True)  # New flag, default to True
    thin_growth_threshold = operation.get('thinGrowthThreshold', 0.001)
    merge_vertices_tolerance = operation.get('mergeVerticesTolerance', buffer_distance/2)
    make_valid = operation.get('makeValid', True)

    combined_gdf = None
    for layer_info in source_layers:
        source_layer_name = layer_info if isinstance(layer_info, str) else layer_info.get('name')
        
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        layer_geometry = all_layers[source_layer_name]

        if combined_gdf is None:
            combined_gdf = layer_geometry
        else:
            combined_gdf = pd.concat([combined_gdf, layer_geometry], ignore_index=True)

    if combined_gdf is not None and not combined_gdf.empty:
        # Remove empty geometries before processing
        combined_gdf = combined_gdf[~combined_gdf.geometry.is_empty]

        if make_valid and combined_gdf is not None:
            combined_gdf.geometry = combined_gdf.geometry.apply(make_valid_geometry)
            combined_gdf = combined_gdf[combined_gdf.geometry.notna()]

        if use_buffer_trick:
            if merge_vertices:
                # First merge close vertices
                combined_gdf.geometry = combined_gdf.geometry.apply(
                    lambda geom: _merge_close_vertices(all_layers, project_settings, crs, geom, tolerance=merge_vertices_tolerance)
                )
                combined_gdf = combined_gdf[combined_gdf.geometry.notna()]
            # Then apply buffer trick with mitre join
            combined_gdf.geometry = apply_buffer_trick(combined_gdf.geometry, buffer_distance)

        if dissolve_field and dissolve_field in combined_gdf.columns:
            dissolved = gpd.GeoDataFrame(geometry=combined_gdf.geometry, data=combined_gdf[dissolve_field]).dissolve(by=dissolve_field, as_index=False)
        else:
            # First pass
            dissolved = gpd.GeoDataFrame(geometry=[unary_union(combined_gdf.geometry)])
            # Second pass if enabled
            if double_pass:
                dissolved = gpd.GeoDataFrame(geometry=[unary_union(dissolved.geometry)])

        # Clean up the resulting geometry and explode to singlepart
        if make_valid:
            dissolved.geometry = dissolved.geometry.make_valid()
        dissolved = dissolved[~dissolved.is_empty]
        dissolved = explode_to_singlepart(dissolved)

        if use_buffer_trick:
            if merge_vertices:
                # Merge vertices again before negative buffer
                dissolved.geometry = dissolved.geometry.apply(
                    lambda geom: _merge_close_vertices(all_layers, project_settings, crs, geom, tolerance=merge_vertices_tolerance)
                )
                dissolved = dissolved[dissolved.geometry.notna()]
            # Apply negative buffer
            dissolved.geometry = apply_buffer_trick(dissolved.geometry, -buffer_distance)
            if make_valid:
                dissolved.geometry = dissolved.geometry.apply(make_valid_geometry)
                dissolved = dissolved[dissolved.geometry.notna()]
        
        # Remove empty geometries after processing
        dissolved = dissolved[~dissolved.geometry.is_empty]

        if dissolved.empty:
            log_warning(f"No valid geometry created for dissolved layer: {layer_name}")
            all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        else:
            all_layers[layer_name] = dissolved.set_crs(crs)
            log_info(f"Created dissolved layer: {layer_name} with {len(dissolved)} features")
    else:
        log_warning(f"No valid source layers found for dissolve operation on {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
