import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry
import math

def create_directional_line_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating directional line layer: {layer_name}")
    
    # Get operation parameters
    source_layers = operation.get('layers', [])
    line_length = operation.get('length', 1.0)  # Default length of 1 unit
    angle = operation.get('angle', 0)  # Default 0 degrees (pointing east)
    relative_angle = operation.get('relativeAngle', True)  # Whether angle is relative to input line
    anchor_point = operation.get('anchorPoint', 'mid')  # 'start', 'mid', 'end', or 'point'
    
    result_lines = []
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(f"Source layer '{source_layer_name}' not found")
            continue

        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if source_geometry is None:
            continue

        # Handle different geometry types
        if isinstance(source_geometry, (LineString, MultiLineString)):
            if isinstance(source_geometry, MultiLineString):
                lines = list(source_geometry.geoms)
            else:
                lines = [source_geometry]

            for line in lines:
                # Get the anchor point based on the specified position
                if anchor_point == 'start':
                    anchor = Point(line.coords[0])
                    if relative_angle:
                        base_angle = math.degrees(math.atan2(
                            line.coords[1][1] - line.coords[0][1],
                            line.coords[1][0] - line.coords[0][0]
                        ))
                elif anchor_point == 'end':
                    anchor = Point(line.coords[-1])
                    if relative_angle:
                        base_angle = math.degrees(math.atan2(
                            line.coords[-1][1] - line.coords[-2][1],
                            line.coords[-1][0] - line.coords[-2][0]
                        ))
                else:  # 'mid' or any other value
                    anchor = line.interpolate(0.5, normalized=True)
                    if relative_angle:
                        base_angle = math.degrees(math.atan2(
                            line.coords[-1][1] - line.coords[0][1],
                            line.coords[-1][0] - line.coords[0][0]
                        ))

                # Calculate the final angle
                if relative_angle:
                    new_angle = math.radians(base_angle + angle)
                else:
                    new_angle = math.radians(angle)

                # Create the new line
                x_offset = math.cos(new_angle) * line_length
                y_offset = math.sin(new_angle) * line_length
                
                new_line = LineString([
                    (anchor.x, anchor.y),
                    (anchor.x + x_offset, anchor.y + y_offset)
                ])
                
                result_lines.append(new_line)

        elif isinstance(source_geometry, (Point, MultiPoint)):
            if isinstance(source_geometry, MultiPoint):
                points = list(source_geometry.geoms)
            else:
                points = [source_geometry]

            for point in points:
                # For points, only absolute angle is meaningful
                new_angle = math.radians(angle)
                x_offset = math.cos(new_angle) * line_length
                y_offset = math.sin(new_angle) * line_length
                
                new_line = LineString([
                    (point.x, point.y),
                    (point.x + x_offset, point.y + y_offset)
                ])
                
                result_lines.append(new_line)
        else:
            log_warning(f"Unsupported geometry type: {type(source_geometry)}")
            continue

    if result_lines:
        result_gdf = gpd.GeoDataFrame(geometry=result_lines, crs=crs)
        all_layers[layer_name] = result_gdf
        log_info(f"Created directional line layer: {layer_name} with {len(result_lines)} lines")
        return result_gdf
    else:
        log_warning(f"No directional lines created for layer: {layer_name}")
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None