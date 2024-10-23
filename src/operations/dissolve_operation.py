import geopandas as gpd
from shapely.ops import unary_union
from src.utils import log_info, log_warning
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, apply_buffer_trick
import pandas as pd

def create_dissolved_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating dissolved layer: {layer_name}")
    source_layers = operation.get('layers', [])
    dissolve_field = operation.get('dissolveField')
    buffer_distance = operation.get('bufferDistance', 0.01)  # Default small buffer distance

    combined_gdf = None
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if layer_geometry is None:
            continue

        if not isinstance(layer_geometry, gpd.GeoDataFrame):
            layer_geometry = gpd.GeoDataFrame(geometry=[layer_geometry], crs=crs)

        if combined_gdf is None:
            combined_gdf = layer_geometry
        else:
            combined_gdf = pd.concat([combined_gdf, layer_geometry], ignore_index=True)

    if combined_gdf is not None and not combined_gdf.empty:
        if dissolve_field and dissolve_field in combined_gdf.columns:
            dissolved = gpd.GeoDataFrame(geometry=combined_gdf.geometry, data=combined_gdf[dissolve_field]).dissolve(by=dissolve_field, as_index=False)
        else:
            dissolved = gpd.GeoDataFrame(geometry=[unary_union(combined_gdf.geometry)])
        
        # Apply buffer trick
        dissolved.geometry = dissolved.geometry.apply(lambda geom: apply_buffer_trick(geom, buffer_distance))
        
        # Clean up the resulting geometry
        dissolved.geometry = dissolved.geometry.make_valid()
        dissolved = dissolved[~dissolved.is_empty]

        all_layers[layer_name] = dissolved.set_crs(crs)
        log_info(f"Created dissolved layer: {layer_name} with {len(dissolved)} features")
    else:
        log_warning(f"No valid source layers found for dissolve operation on {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
