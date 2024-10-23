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

    source_layer_name = operation.get('sourceLayer')
    if not source_layer_name:
        log_warning(f"No source layer specified for buffer operation on {layer_name}")
        return None

    source_geometry = all_layers.get(source_layer_name)
    if source_geometry is None:
        log_warning(f"Source layer '{source_layer_name}' not found for buffer operation on {layer_name}")
        return None

    buffer_distance = operation.get('distance', 0)
    log_info(f"Buffer distance: {buffer_distance}")

    try:
        if isinstance(source_geometry, gpd.GeoDataFrame):
            buffered = source_geometry.geometry.buffer(buffer_distance)
        else:
            buffered = source_geometry.buffer(buffer_distance)

        # Apply prepare_and_clean_geometry to each geometry
        if isinstance(buffered, gpd.GeoSeries):
            cleaned = buffered.apply(lambda geom: prepare_and_clean_geometry(all_layers, project_settings, crs, geom,
                                                                             buffer_distance=0.001,
                                                                             thin_growth_threshold=0.001,
                                                                             merge_vertices_tolerance=0.0001))
        else:
            cleaned = prepare_and_clean_geometry(all_layers, project_settings, crs, buffered,
                                                 buffer_distance=0.001,
                                                 thin_growth_threshold=0.001,
                                                 merge_vertices_tolerance=0.0001)

        # Create a new GeoDataFrame with the resulting geometries
        if isinstance(cleaned, gpd.GeoSeries):
            result_gdf = gpd.GeoDataFrame(geometry=cleaned, crs=crs)
        else:
            result_gdf = gpd.GeoDataFrame(geometry=[cleaned], crs=crs)

        all_layers[layer_name] = result_gdf
        log_info(f"Created buffer layer: {layer_name} with {len(result_gdf)} geometries")
        return result_gdf
    except Exception as e:
        log_error(f"Error during buffer operation: {str(e)}")
        import traceback
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return None




