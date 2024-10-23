import geopandas as gpd
from shapely.ops import unary_union
from src.utils import log_info, log_warning
from src.operations.common_operations import explode_to_singlepart
import pandas as pd

def create_dissolved_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating dissolved layer: {layer_name}")
    source_layers = operation.get('layers', [layer_name])  # Default to current layer if not specified
    dissolve_field = operation.get('dissolveField')
    buffer_distance = operation.get('bufferDistance', 0.01)
    thin_growth_threshold = operation.get('thinGrowthThreshold', 0.001)
    merge_vertices_tolerance = operation.get('mergeVerticesTolerance', 0.0001)

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

        if dissolve_field and dissolve_field in combined_gdf.columns:
            dissolved = gpd.GeoDataFrame(geometry=combined_gdf.geometry, data=combined_gdf[dissolve_field]).dissolve(by=dissolve_field, as_index=False)
        else:
            dissolved = gpd.GeoDataFrame(geometry=[unary_union(combined_gdf.geometry)])
        
        # Clean up the resulting geometry and explode to singlepart
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
            log_info(f"Created dissolved layer: {layer_name} with {len(dissolved)} features")
    else:
        log_warning(f"No valid source layers found for dissolve operation on {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
