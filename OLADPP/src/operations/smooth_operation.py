import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe, make_valid_geometry
from src.operations.common_operations import *

def create_smooth_layer(all_layers, project_settings, crs, layer_name, operation):
        log_debug(f"Creating smooth layer: {layer_name}")
        source_layers = operation.get('layers', [])
        strength = operation.get('strength', 1.0)  # Default strength to 1.0
        make_valid = operation.get('makeValid', True)

        combined_geometry = None
        for layer_info in source_layers:
            source_layer_name, values = _process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = _get_filtered_geometry(source_layer_name, values)
            if layer_geometry is None:
                continue

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.union(layer_geometry)

        if combined_geometry is not None:
            if make_valid and combined_geometry is not None:
                combined_geometry = make_valid_geometry(combined_geometry)
            buffer_distance = operation.get('bufferDistance', 0.001)
            thin_growth_threshold = operation.get('thinGrowthThreshold', 0.001)
            merge_vertices_tolerance = operation.get('mergeVerticesTolerance', 0.0001)
            smoothed_geometry = smooth_geometry(combined_geometry, strength)
            if make_valid:
                smoothed_geometry = make_valid_geometry(smoothed_geometry)
            cleaned_geometry = smoothed_geometry
            all_layers[layer_name] = ensure_geodataframe(layer_name, gpd.GeoDataFrame(geometry=[cleaned_geometry], crs=crs))
            log_debug(f"Created smooth layer: {layer_name}")
        else:
            log_warning(f"No valid source geometry found for smooth layer '{layer_name}'")
            all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)


def smooth_geometry(all_layers, project_settings, crs, geometry, strength):
        # Simplify the geometry
        smoothed = geometry.simplify(strength, preserve_topology=True)
        
        # Ensure the smoothed geometry does not expand beyond the original geometry
        if not geometry.contains(smoothed):
            smoothed = geometry.intersection(smoothed)
        
        # Increase vertex count for smoother curves
        if isinstance(smoothed, (Polygon, MultiPolygon)):
            smoothed = smoothed.buffer(0.01).buffer(-0.01)
        
        # Ensure the smoothed geometry does not expand beyond the original geometry after vertex increase
        if not geometry.contains(smoothed):
            smoothed = geometry.intersection(smoothed)
        
        return smoothed




