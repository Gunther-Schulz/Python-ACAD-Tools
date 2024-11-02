import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import format_operation_warning, _process_layer_info, _get_filtered_geometry, explode_to_singlepart

def create_copy_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating copy layer: {layer_name}")
    source_layers = operation.get('layers', [])
    
    combined_gdf = None
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue
            
        if source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "copy",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue
            
        source_gdf = all_layers[source_layer_name].copy()
        
        if values:
            label_column = next((l['label'] for l in project_settings['geomLayers'] if l['name'] == source_layer_name), None)
            if label_column and label_column in source_gdf.columns:
                source_gdf = source_gdf[source_gdf[label_column].astype(str).isin([str(v) for v in values])]
                log_info(f"Filtered {source_layer_name} using column '{label_column}': {len(source_gdf)} features remaining")
            else:
                log_warning(format_operation_warning(
                    layer_name,
                    "copy",
                    f"Label column for layer '{source_layer_name}' not found in project settings or data"
                ))
                continue
        
        if source_gdf.empty:
            continue
            
        if not isinstance(source_gdf, gpd.GeoDataFrame):
            source_gdf = gpd.GeoDataFrame(geometry=[source_gdf], crs=crs)
        
        source_gdf = explode_to_singlepart(source_gdf)
        
        if combined_gdf is None:
            combined_gdf = source_gdf
        else:
            combined_gdf = pd.concat([combined_gdf, source_gdf], ignore_index=True)

    if combined_gdf is not None and not combined_gdf.empty:
        combined_gdf = explode_to_singlepart(combined_gdf)
        all_layers[layer_name] = combined_gdf
        log_info(f"Created copy layer: {layer_name} with {len(combined_gdf)} separate features")
    else:
        log_warning(format_operation_warning(
            layer_name,
            "copy",
            "No valid source layers found"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
