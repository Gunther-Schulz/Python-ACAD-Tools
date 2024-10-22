import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry

def create_filtered_geometry_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating filtered geometry layer: {layer_name}")
    source_layers = operation.get('layers', [])
    
    max_area = operation.get('maxArea', float('inf'))
    min_area = operation.get('minArea', 0)
    max_width = operation.get('maxWidth', float('inf'))
    min_width = operation.get('minWidth', 0)
    
    filtered_geometries = []
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if layer_geometry is None:
            continue

        if isinstance(layer_geometry, (Polygon, MultiPolygon)):
            filtered = filter_polygons(layer_geometry, max_area, min_area, max_width, min_width)
        elif isinstance(layer_geometry, (LineString, MultiLineString)):
            filtered = filter_linestrings(layer_geometry, max_width, min_width)
        else:
            log_warning(f"Unsupported geometry type for filtering: {type(layer_geometry)}")
            continue

        filtered_geometries.extend(filtered)

    if filtered_geometries:
        result_gdf = gpd.GeoDataFrame(geometry=filtered_geometries, crs=crs)
        all_layers[layer_name] = result_gdf
        log_info(f"Created filtered geometry layer '{layer_name}' with {len(result_gdf)} geometries")
    else:
        log_warning(f"No geometries passed the filter for layer '{layer_name}'")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]

def filter_polygons(geometry, max_area, min_area, max_width, min_width):
    filtered = []
    if isinstance(geometry, Polygon):
        geometries = [geometry]
    else:  # MultiPolygon
        geometries = list(geometry.geoms)

    for poly in geometries:
        area = poly.area
        width = estimate_width(poly)
        if min_area <= area <= max_area and min_width <= width <= max_width:
            filtered.append(poly)
    
    return filtered

def filter_linestrings(geometry, max_width, min_width):
    filtered = []
    if isinstance(geometry, LineString):
        geometries = [geometry]
    else:  # MultiLineString
        geometries = list(geometry.geoms)

    for line in geometries:
        width = line.length  # For LineStrings, we use length as a proxy for width
        if min_width <= width <= max_width:
            filtered.append(line)
    
    return filtered

def estimate_width(polygon):
    # This is a simple estimation using the square root of the area
    # For more accurate results, you might want to implement a more sophisticated method
    return (polygon.area / polygon.length) * 2