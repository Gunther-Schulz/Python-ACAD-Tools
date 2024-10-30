import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from shapely.ops import unary_union
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry
from src.operations.common_operations import *

def create_merged_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating merged layer: {layer_name}")
    source_layers = operation.get('layers', [])
    
    combined_geometries = []
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if layer_geometry is None:
            continue

        log_info(f"Adding geometry from layer '{source_layer_name}': {layer_geometry.geom_type}")
        combined_geometries.append(layer_geometry)

    log_info(f"Total geometries collected: {len(combined_geometries)}")

    if combined_geometries:
        merged_geometry = unary_union(combined_geometries)
        
        # If the result is a MultiPolygon, convert it to separate Polygons
        if isinstance(merged_geometry, MultiPolygon):
            log_info("Result is a MultiPolygon, separating into individual Polygons")
            result_geometries = list(merged_geometry.geoms)
        elif isinstance(merged_geometry, Polygon):
            log_info("Result is a single Polygon")
            result_geometries = [merged_geometry]
        else:
            log_info(f"Result is of type {type(merged_geometry)}")
            result_geometries = [merged_geometry]
        
        log_info(f"Number of resulting geometries: {len(result_geometries)}")
        
        # Create a GeoDataFrame with the resulting geometries and explode to singlepart
        result_gdf = explode_to_singlepart(gpd.GeoDataFrame(geometry=result_geometries, crs=crs))
        all_layers[layer_name] = result_gdf
        log_info(f"Created merged layer '{layer_name}' with {len(result_gdf)} geometries")
        
        # Log details of each resulting geometry
        for i, geom in enumerate(result_gdf.geometry):
            log_info(f"Geometry {i+1}: {geom.geom_type}, Area: {geom.area}, Length: {geom.length}")
    else:
        log_warning(format_operation_warning(
            layer_name,
            "merge",
            "No valid source geometries found for merged layer"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
