import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, explode_to_singlepart

def create_filtered_geometry_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating filtered geometry layer: {layer_name}")
    source_layers = operation.get('layers', [layer_name])
    
    max_area = operation.get('maxArea', float('inf'))
    min_area = operation.get('minArea', 0)
    max_width = operation.get('maxWidth', float('inf'))
    min_width = operation.get('minWidth', 0)
    geometry_types = operation.get('geometryTypes', None)

    # Map Multi variants to their base type
    geometry_type_mapping = {
        'MultiPolygon': 'Polygon',
        'MultiLineString': 'LineString',
        'MultiPoint': 'Point'
    }
    
    if geometry_types:
        # Normalize geometry types to base types
        geometry_types = [geometry_type_mapping.get(gt, gt) for gt in geometry_types]
        log_info(f"Filtering for geometry types: {geometry_types}")
    
    filtered_geometries = []
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if layer_geometry is None:
            continue

        if isinstance(layer_geometry, GeometryCollection):
            for geom in layer_geometry.geoms:
                # Get base type for the geometry
                base_type = geometry_type_mapping.get(geom.geom_type, geom.geom_type)
                if geometry_types and base_type not in geometry_types:
                    continue
                filtered = filter_geometry(geom, max_area, min_area, max_width, min_width)
                filtered_geometries.extend(filtered)
        else:
            base_type = geometry_type_mapping.get(layer_geometry.geom_type, layer_geometry.geom_type)
            if not geometry_types or base_type in geometry_types:
                filtered = filter_geometry(layer_geometry, max_area, min_area, max_width, min_width)
                filtered_geometries.extend(filtered)

    if filtered_geometries:
        result_gdf = explode_to_singlepart(gpd.GeoDataFrame(geometry=filtered_geometries, crs=crs))
        all_layers[layer_name] = result_gdf
        log_info(f"Created filtered geometry layer '{layer_name}' with {len(result_gdf)} geometries")
    else:
        log_warning(f"No geometries passed the filter for layer '{layer_name}'")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]

def filter_geometry(geometry, max_area, min_area, max_width, min_width):
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return filter_polygons(geometry, max_area, min_area, max_width, min_width)
    elif isinstance(geometry, (LineString, MultiLineString)):
        return filter_linestrings(geometry, max_width, min_width)
    else:
        log_warning(f"Unsupported geometry type for filtering: {type(geometry)}")
        return []

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
