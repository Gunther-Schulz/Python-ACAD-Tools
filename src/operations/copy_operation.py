import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe
from src.operations.common_operations import *

def create_copy_layer(all_layers, project_settings, crs, layer_name, operation):
    source_layers = operation.get('layers', [])
    combined_gdf = None

    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(f"Source layer '{source_layer_name}' not found for copy operation")
            continue

        source_gdf = all_layers[source_layer_name]
        
        if values:
            label_column = next((l['label'] for l in project_settings['geomLayers'] if l['name'] == source_layer_name), None)
            if label_column and label_column in source_gdf.columns:
                filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(values)].copy()
            else:
                log_warning(f"Label column '{label_column}' not found in layer '{source_layer_name}'")
                continue
        else:
            filtered_gdf = source_gdf.copy()

        if combined_gdf is None:
            combined_gdf = filtered_gdf
        else:
            # Combine GeoDataFrames, keeping all columns
            combined_gdf = combined_gdf.append(filtered_gdf, ignore_index=True)

    if combined_gdf is not None and not combined_gdf.empty:
        # Ensure the CRS is set correctly
        combined_gdf = combined_gdf.set_crs(crs)
        all_layers[layer_name] = combined_gdf
        log_info(f"Copied layer(s) to {layer_name} with {len(combined_gdf)} features and {len(combined_gdf.columns)} attributes")
    else:
        log_warning(f"No valid source layers found for copy operation on {layer_name}")

    return all_layers[layer_name] if layer_name in all_layers else None
