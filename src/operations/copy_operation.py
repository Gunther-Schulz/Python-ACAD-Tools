import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, explode_to_singlepart

def create_copy_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating copy layer: {layer_name}")
    source_layers = operation.get('layers', [])
    
    combined_gdf = None
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        filtered_geom = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if filtered_geom is None:
            continue

        if isinstance(filtered_geom, gpd.GeoDataFrame):
            filtered_gdf = filtered_geom
        else:
            # Convert single geometry to GeoDataFrame
            filtered_gdf = gpd.GeoDataFrame(geometry=[filtered_geom], crs=crs)

        # Use explode_to_singlepart for MultiPolygon geometries
        filtered_gdf = explode_to_singlepart(filtered_gdf)

        if combined_gdf is None:
            combined_gdf = filtered_gdf
        else:
            combined_gdf = pd.concat([combined_gdf, filtered_gdf], ignore_index=True)

    if combined_gdf is not None and not combined_gdf.empty:
        all_layers[layer_name] = combined_gdf
        log_info(f"Created copy layer: {layer_name} with {len(combined_gdf)} features")
    else:
        log_warning(f"No valid source layers found for copy operation on {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
