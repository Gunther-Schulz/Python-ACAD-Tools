import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from shapely.ops import unary_union
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry
from src.operations.common_operations import *
from src.operations.common_operations import explode_to_singlepart

def create_buffer_layer(all_layers, project_settings, crs, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layers = operation.get('layers', [])
        buffer_distance = operation['distance']
        join_style = operation.get('joinStyle', 'mitre')  # Default to 'mitre' instead of 'round'

        join_style_map = {'round': 1, 'mitre': 2, 'bevel': 3}
        join_style_value = join_style_map.get(join_style, 2)  # Default to mitre (2) if not specified

        combined_geometry = None
        for layer_info in source_layers:
            source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
            if layer_geometry is None:
                continue

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.union(layer_geometry)

        if combined_geometry is not None:
            if isinstance(combined_geometry, gpd.GeoDataFrame):
                buffered = combined_geometry.geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                buffered = buffered[~buffered.is_empty]  # Remove empty geometries
                if buffered.empty:
                    log_warning(f"Buffer operation resulted in empty geometry for layer {layer_name}")
                    return None
                result = explode_to_singlepart(gpd.GeoDataFrame(geometry=buffered, crs=crs))
                
                # Copy attributes from the original geometry
                for col in combined_geometry.columns:
                    if col != 'geometry':
                        result[col] = combined_geometry[col].iloc[0]
            else:
                # Handle individual geometry objects
                buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                if buffered.is_empty:
                    log_warning(f"Buffer operation resulted in empty geometry for layer {layer_name}")
                    return None
                result = explode_to_singlepart(gpd.GeoDataFrame(geometry=[buffered], crs=crs))
            
            return result
        else:
            log_warning(f"No valid geometry found for buffer operation on layer {layer_name}")
            return None




