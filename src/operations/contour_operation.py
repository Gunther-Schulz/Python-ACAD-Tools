import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.contour_processor import process_contour
from src.operations.common_operations import _get_filtered_geometry
from src.operations.common_operations import *

def _handle_contour_operation(all_layers, project_settings, crs, layer_name, operation):
        log_info(f"Starting contour operation for layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        geltungsbereich = _get_filtered_geometry(operation['layers'][0], [])
        if geltungsbereich is None:
            log_warning(f"Geltungsbereich not found for contour operation on layer '{layer_name}'")
            return None

        buffer_distance = operation.get('buffer', 0)
        contour_gdf = process_contour(operation, geltungsbereich, buffer_distance, crs)

        if layer_name in all_layers:
            log_warning(f"Layer '{layer_name}' already exists. Overwriting with new contour data.")
        
        all_layers[layer_name] = contour_gdf
        log_info(f"Finished contour operation for layer: {layer_name}")
        log_info(f"Number of contour features: {len(contour_gdf)}")
        return contour_gdf


