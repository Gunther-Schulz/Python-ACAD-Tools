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
        source_layer_name = layer_info['name'] if isinstance(layer_info, dict) else layer_info
        values = layer_info.get('values', []) if isinstance(layer_info, dict) else []
        
        if source_layer_name not in all_layers:
            log_warning(f"Source layer '{source_layer_name}' not found")
            continue
            
        # Get the source layer and make a copy
        source_gdf = all_layers[source_layer_name].copy()
        
        # Apply value filtering if values are specified
        if values:
            if 'OBJECTID' in source_gdf.columns:
                source_gdf = source_gdf[source_gdf['OBJECTID'].astype(str).isin([str(v) for v in values])]
            else:
                log_warning(f"Cannot filter values: OBJECTID column not found in {source_layer_name}")
        
        if source_gdf.empty:
            continue
            
        # Ensure we're working with a GeoDataFrame
        if not isinstance(source_gdf, gpd.GeoDataFrame):
            source_gdf = gpd.GeoDataFrame(geometry=[source_gdf], crs=crs)
        
        # Explode to ensure single-part geometries
        source_gdf = explode_to_singlepart(source_gdf)
        
        if combined_gdf is None:
            combined_gdf = source_gdf
        else:
            combined_gdf = pd.concat([combined_gdf, source_gdf], ignore_index=True)

    if combined_gdf is not None and not combined_gdf.empty:
        # Final explode to ensure features stay separate
        combined_gdf = explode_to_singlepart(combined_gdf)
        all_layers[layer_name] = combined_gdf
        log_info(f"Created copy layer: {layer_name} with {len(combined_gdf)} separate features")
    else:
        log_warning(f"No valid source layers found for copy operation on {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
