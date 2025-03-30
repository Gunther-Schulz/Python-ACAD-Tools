import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe
from src.operations.common_operations import *

def create_filtered_by_intersection_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating filtered layer: {layer_name}")

    if layer_name not in all_layers:
        log_warning(f"Layer '{layer_name}' not found for filtering")
        return

    source_gdf = all_layers[layer_name]
    filtered_gdf = source_gdf.copy()

    # Track columns and values to add
    columns_to_add = {}

    for layer_info in operation['layers']:
        source_layer_name, values, column_name = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        log_debug(f"Processing filter layer: {source_layer_name}")

        filter_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values, column_name)
        if filter_geometry is None:
            continue

        log_debug(f"Filter geometry type for {source_layer_name}: {type(filter_geometry)}")

        # Store the column name and values for later addition
        columns_to_add[source_layer_name] = values[0] if values else None

        # Explode MultiPolygon into individual Polygons
        filtered_gdf = explode_to_singlepart(filtered_gdf)

        # Apply a small buffer to handle edge-on-edge proximity
        small_buffer = -1
        buffered_filter_geometry = filter_geometry.buffer(small_buffer)

        # Filter the geometries based on intersection with the buffered filter geometry
        filtered_gdf = filtered_gdf[filtered_gdf.geometry.intersects(buffered_filter_geometry)]

        # If no geometries are left after filtering, break early
        if filtered_gdf.empty:
            log_warning(format_operation_warning(
                layer_name,
                "filter",
                "No geometries left after filtering"
            ))
            all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
            break

    if not filtered_gdf.empty:
        # Add the stored columns and values
        for col_name, value in columns_to_add.items():
            if value is not None:
                filtered_gdf[col_name] = value

        all_layers[layer_name] = ensure_geodataframe(all_layers, project_settings, crs, layer_name, filtered_gdf)
    else:
        log_warning(f"No geometries left after filtering for layer: {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)

    return all_layers[layer_name]
