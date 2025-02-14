import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint
from src.core.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, format_operation_warning

def create_circle_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating circle layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    radius = operation.get('radius')  # Fixed radius if specified
    radius_field = operation.get('radiusField')  # Field name containing radius values
    
    if radius is None and radius_field is None:
        log_warning(format_operation_warning(
            layer_name,
            "circle",
            "Neither radius nor radiusField specified"
        ))
        return None

    result_circles = []
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]
        
        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            current_radius = float(row[radius_field]) if radius_field else radius
            
            points = []
            if isinstance(geom, (Point, MultiPoint)):
                if isinstance(geom, Point):
                    points = [geom]
                else:
                    points = list(geom.geoms)
            elif isinstance(geom, (LineString, MultiLineString)):
                if isinstance(geom, LineString):
                    points = [Point(coord) for coord in geom.coords]
                else:
                    points = [Point(coord) for line in geom.geoms for coord in line.coords]
            elif isinstance(geom, (Polygon, MultiPolygon)):
                if isinstance(geom, Polygon):
                    points = [Point(coord) for coord in geom.exterior.coords]
                else:
                    points = [Point(coord) for poly in geom.geoms for coord in poly.exterior.coords]
            
            # Create circles at each point
            for point in points:
                circle = point.buffer(current_radius)
                result_circles.append(circle)

    if result_circles:
        result_gdf = gpd.GeoDataFrame(geometry=result_circles, crs=crs)
        all_layers[layer_name] = result_gdf
        log_debug(f"Created circle layer: {layer_name} with {len(result_circles)} circles")
        return result_gdf
    else:
        log_warning(format_operation_warning(
            layer_name,
            "circle",
            "No circles created"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None 