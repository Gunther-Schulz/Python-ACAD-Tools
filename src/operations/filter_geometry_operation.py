import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, explode_to_singlepart

def create_filtered_geometry_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating filtered geometry layer: {layer_name}")
    
    # Get the input layer
    input_gdf = all_layers[layer_name].copy()
    
    # Define geometry type mappings
    GEOMETRY_TYPE_GROUPS = {
        'polygon': ['Polygon', 'MultiPolygon'],
        'line': ['LineString', 'MultiLineString'],
        'point': ['Point', 'MultiPoint']
    }
    
    # Get filter parameters
    max_area = operation.get('maxArea', float('inf'))
    min_area = operation.get('minArea', 0)
    max_width = operation.get('maxWidth', float('inf'))
    min_width = operation.get('minWidth', 0)
    geometry_types = operation.get('geometryTypes', None)
    
    if geometry_types:
        # Convert simplified types to actual geometry types
        allowed_types = []
        for geom_type in geometry_types:
            geom_type_lower = geom_type.lower()
            if geom_type_lower not in GEOMETRY_TYPE_GROUPS:
                log_warning(f"Unrecognized geometry type '{geom_type}' in filter for layer '{layer_name}'. "
                          f"Valid types are: {', '.join(GEOMETRY_TYPE_GROUPS.keys())}")
            else:
                allowed_types.extend(GEOMETRY_TYPE_GROUPS[geom_type_lower])
    
    # Create combined mask for all filters
    mask = input_gdf.geometry.apply(lambda geom: 
        min_area <= geom.area <= max_area and 
        min_width <= estimate_width(geom) <= max_width and
        (geometry_types is None or geom.geom_type in allowed_types)
    )
    
    # Filter the GeoDataFrame
    result_gdf = input_gdf[mask].copy()
    
    if not result_gdf.empty:
        all_layers[layer_name] = result_gdf
        log_debug(f"Created filtered geometry layer '{layer_name}' with {len(result_gdf)} geometries")
    else:
        log_warning(f"No geometries passed the filter for layer '{layer_name}'")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]

def estimate_width(polygon):
    # This is a simple estimation using the square root of the area
    # For more accurate results, you might want to implement a more sophisticated method
    return (polygon.area / polygon.length) * 2
