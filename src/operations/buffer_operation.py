import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from shapely.ops import unary_union
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry
from src.operations.common_operations import *
from src.operations.common_operations import explode_to_singlepart
from src.operations.common_operations import prepare_and_clean_geometry

def create_buffer_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating buffer layer: {layer_name}")
    log_info(f"Operation details: {operation}")

    buffer_distance = operation.get('distance', 0)
    buffer_mode = operation.get('mode', 'off')
    join_style = operation.get('join_style', 'mitre')

    # Map join style names to shapely constants
    join_style_map = {
        'round': 1,
        'mitre': 2,
        'bevel': 3
    }
    join_style_value = join_style_map.get(join_style, 2)  # Default to 'mitre' if invalid

    source_layers = operation.get('layers', [layer_name])
    
    combined_geometry = None
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(f"Source layer '{source_layer_name}' not found for buffer operation on {layer_name}")
            continue

        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if source_geometry is None:
            continue

        if combined_geometry is None:
            combined_geometry = source_geometry
        else:
            combined_geometry = combined_geometry.union(source_geometry)

    if combined_geometry is None:
        log_warning(f"No valid source geometry found for buffer operation on {layer_name}")
        return None

    try:
        if buffer_mode == 'outer':
            buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
            result = buffered.difference(combined_geometry)
        elif buffer_mode == 'inner':
            result = combined_geometry.buffer(-buffer_distance, cap_style=2, join_style=join_style_value)
        elif buffer_mode == 'keep':
            buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
            result = [combined_geometry, buffered]
        else:  # 'off' or any other value
            result = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)

        # Ensure the result is a valid geometry type for shapefiles
        if buffer_mode == 'keep':
            result_geom = []
            for geom in result:
                if isinstance(geom, (Polygon, MultiPolygon)):
                    result_geom.append(geom)
                elif isinstance(geom, GeometryCollection):
                    result_geom.extend([g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))])
        else:
            if isinstance(result, (Polygon, MultiPolygon)):
                result_geom = [result]
            elif isinstance(result, GeometryCollection):
                result_geom = [geom for geom in result.geoms if isinstance(geom, (Polygon, MultiPolygon))]
            else:
                result_geom = []

        result_gdf = gpd.GeoDataFrame(geometry=result_geom, crs=crs)
        all_layers[layer_name] = result_gdf
        log_info(f"Created buffer layer: {layer_name} with {len(result_geom)} geometries")
        return result_gdf
    except Exception as e:
        log_error(f"Error during buffer operation: {str(e)}")
        import traceback
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return None





