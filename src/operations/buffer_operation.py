import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from shapely.ops import unary_union
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, make_valid_geometry, format_operation_warning
from src.operations.common_operations import *


def create_buffer_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating buffer layer: {layer_name}")
    log_info(f"Operation details: {operation}")

    buffer_distance = operation.get('distance', 0)
    buffer_mode = operation.get('mode', 'off')
    join_style = operation.get('joinStyle', 'mitre')

    join_style_map = {
        'round': 1,
        'mitre': 2,
        'bevel': 3
    }
    join_style_value = join_style_map.get(join_style, 2)

    source_layers = operation.get('layers', [layer_name])
    
    combined_geometry = None
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "buffer",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue

        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if source_geometry is None:
            log_warning(format_operation_warning(
                layer_name,
                "buffer",
                f"Failed to get filtered geometry for layer '{source_layer_name}'"
            ))
            continue

        if combined_geometry is None:
            combined_geometry = source_geometry
        else:
            try:
                combined_geometry = combined_geometry.union(source_geometry)
            except Exception as e:
                log_warning(format_operation_warning(
                    layer_name,
                    "buffer",
                    f"Error combining geometries: {str(e)}"
                ))
                continue

    if combined_geometry is None:
        log_warning(format_operation_warning(
            layer_name,
            "buffer",
            "No valid source geometry found"
        ))
        return None

    make_valid = operation.get('makeValid', True)

    if make_valid and combined_geometry is not None:
        combined_geometry = make_valid_geometry(combined_geometry)

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

        # After buffer operations and before converting to result_geom
        if make_valid:
            if buffer_mode == 'keep':
                result = [make_valid_geometry(geom) if geom is not None else None for geom in result]
                result = [geom for geom in result if geom is not None]
            else:
                result = make_valid_geometry(result)

        result_gdf = gpd.GeoDataFrame(geometry=result_geom, crs=crs)
        all_layers[layer_name] = result_gdf
        log_info(f"Created buffer layer: {layer_name} with {len(result_geom)} geometries")
        return result_gdf
    except Exception as e:
        log_error(format_operation_warning(
            layer_name,
            "buffer",
            f"Error during buffer operation: {str(e)}"
        ))
        return None






