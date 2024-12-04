import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error, log_debug
from shapely.ops import unary_union, split
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, make_valid_geometry, format_operation_warning, remove_islands
from src.operations.common_operations import *


def create_buffer_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating buffer layer: {layer_name}")
    log_debug(f"Operation details: {operation}")

    buffer_distance = operation.get('distance', 0)
    buffer_mode = operation.get('mode', 'off')
    join_style = operation.get('joinStyle', 'mitre')
    cap_style = operation.get('capStyle', 'square')
    start_cap_style = operation.get('startCapStyle', cap_style)
    end_cap_style = operation.get('endCapStyle', cap_style)

    join_style_map = {
        'round': 1,
        'mitre': 2,
        'bevel': 3
    }
    
    cap_style_map = {
        'round': 1,
        'flat': 2,
        'square': 3
    }
    
    join_style_value = join_style_map.get(join_style, 2)
    start_cap_value = cap_style_map.get(start_cap_style, 2)
    end_cap_value = cap_style_map.get(end_cap_style, 2)
    print(f"Layer: {layer_name}, Join style: {join_style}, Start cap: {start_cap_style}, End cap: {end_cap_style}")

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

    skip_islands = operation.get('skipIslands', False)
    preserve_islands = operation.get('preserveIslands', False)
    
    if (skip_islands or preserve_islands) and combined_geometry is not None:
        combined_geometry = remove_islands(combined_geometry, preserve=preserve_islands)
        if combined_geometry is None:
            log_warning(format_operation_warning(
                layer_name,
                "buffer",
                "No geometry remained after processing islands"
            ))
            return None
        log_debug(f"Processed islands from input geometry for layer: {layer_name}")

    def buffer_with_different_caps(geom, distance, start_cap, end_cap, join_style, preserve_holes=False):
        if not isinstance(geom, (LineString, MultiLineString)):
            if preserve_holes and isinstance(geom, (Polygon, MultiPolygon)):
                # For polygons with holes when preserving islands:
                if isinstance(geom, Polygon):
                    # Buffer exterior with specified distance
                    exterior = Polygon(geom.exterior.coords).buffer(distance, cap_style=start_cap, join_style=join_style)
                    # Buffer holes with distance 0 (preserve them as-is)
                    holes = [Polygon(interior.coords).buffer(0) for interior in geom.interiors]
                    # Cut the preserved holes from the buffered exterior
                    result = exterior
                    for hole in holes:
                        result = result.difference(hole)
                    return result
                else:  # MultiPolygon
                    buffered_parts = [buffer_with_different_caps(part, distance, start_cap, end_cap, join_style, preserve_holes=True) 
                                    for part in geom.geoms]
                    return unary_union(buffered_parts)
            else:
                # Regular buffer for other cases
                return geom.buffer(distance, cap_style=start_cap, join_style=join_style)

        if isinstance(geom, MultiLineString):
            # Handle each line separately
            buffered_parts = [buffer_with_different_caps(line, distance, start_cap, end_cap, join_style) 
                            for line in geom.geoms]
            return unary_union(buffered_parts)

        # For single LineString
        if start_cap == end_cap:
            # If caps are the same, use regular buffer
            return geom.buffer(distance, cap_style=start_cap, join_style=join_style)

        # Get start and end points
        start_point = Point(geom.coords[0])
        end_point = Point(geom.coords[-1])

        # Create buffers with different caps
        buffer1 = geom.buffer(distance, cap_style=start_cap, join_style=join_style)
        buffer2 = geom.buffer(distance, cap_style=end_cap, join_style=join_style)

        # Create small circles around start and end points
        start_circle = start_point.buffer(distance * 1.5)
        end_circle = end_point.buffer(distance * 1.5)

        # Combine the results
        result = (
            (buffer1.intersection(start_circle))
            .union(buffer2.intersection(end_circle))
            .union(buffer1.difference(start_circle).difference(end_circle))
        )

        return result

    try:
        if preserve_islands:
            result = buffer_with_different_caps(combined_geometry, buffer_distance,
                                          start_cap_value, end_cap_value, join_style_value,
                                          preserve_holes=True)
        else:
            result = buffer_with_different_caps(combined_geometry, buffer_distance,
                                          start_cap_value, end_cap_value, join_style_value)

        # Convert MultiPolygons to individual Polygons
        result_geom = []
        if buffer_mode == 'keep':
            for geom in result:
                if isinstance(geom, Polygon):
                    result_geom.append(geom)
                elif isinstance(geom, MultiPolygon):
                    result_geom.extend(list(geom.geoms))
                elif isinstance(geom, GeometryCollection):
                    for g in geom.geoms:
                        if isinstance(g, Polygon):
                            result_geom.append(g)
                        elif isinstance(g, MultiPolygon):
                            result_geom.extend(list(g.geoms))
        else:
            if isinstance(result, Polygon):
                result_geom = [result]
            elif isinstance(result, MultiPolygon):
                result_geom = list(result.geoms)
            elif isinstance(result, GeometryCollection):
                for geom in result.geoms:
                    if isinstance(geom, Polygon):
                        result_geom.append(geom)
                    elif isinstance(geom, MultiPolygon):
                        result_geom.extend(list(geom.geoms))

        # After buffer operations and before converting to result_geom
        if make_valid:
            if buffer_mode == 'keep':
                result = [make_valid_geometry(geom) if geom is not None else None for geom in result]
                result = [geom for geom in result if geom is not None]
            else:
                result = make_valid_geometry(result)

        result_gdf = gpd.GeoDataFrame(geometry=result_geom, crs=crs)
        all_layers[layer_name] = result_gdf
        log_debug(f"Created buffer layer: {layer_name} with {len(result_geom)} geometries")
        return result_gdf
    except Exception as e:
        log_error(format_operation_warning(
            layer_name,
            "buffer",
            f"Error during buffer operation: {str(e)}"
        ))
        return None






