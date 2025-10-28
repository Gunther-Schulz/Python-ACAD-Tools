import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
from shapely.ops import split, unary_union
from src.utils import log_info, log_warning, log_debug
from src.operations.common_operations import format_operation_warning
import numpy as np

def create_break_at_intersections_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Break lines at all intersection points.
    This includes:
    - Line-line crossings (T-junctions, X-crossings)
    - Line endpoints touching other lines
    - Multiple lines meeting at a point
    """
    
    # Get source layers
    source_layers = operation.get('layers', [layer_name])
    if not source_layers:
        source_layers = [layer_name]
    
    # Tolerance for finding nearby points
    tolerance = operation.get('tolerance', 0.001)  # 1mm default
    
    all_lines = []
    
    # Collect all lines from source layers
    for source_layer_name in source_layers:
        if isinstance(source_layer_name, dict):
            source_layer_name = source_layer_name.get('name')
        
        if source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "breakAtIntersections",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue
        
        source_gdf = all_layers[source_layer_name]
        
        if source_gdf.empty:
            continue
        
        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            
            if geom is None or geom.is_empty:
                continue
            
            if isinstance(geom, LineString):
                all_lines.append(geom)
            elif isinstance(geom, MultiLineString):
                for line in geom.geoms:
                    all_lines.append(line)
    
    if not all_lines:
        log_warning(format_operation_warning(
            layer_name,
            "breakAtIntersections",
            "No lines found to process"
        ))
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    log_debug(f"Breaking {len(all_lines)} lines at intersections")
    
    # Find all intersection points
    intersection_points = set()
    
    # Check each pair of lines for intersections
    for i in range(len(all_lines)):
        for j in range(i + 1, len(all_lines)):
            line1 = all_lines[i]
            line2 = all_lines[j]
            
            if line1.intersects(line2):
                intersection = line1.intersection(line2)
                
                # Extract points from intersection
                if isinstance(intersection, Point):
                    intersection_points.add((intersection.x, intersection.y))
                elif isinstance(intersection, MultiPoint):
                    for pt in intersection.geoms:
                        intersection_points.add((pt.x, pt.y))
                elif isinstance(intersection, LineString):
                    # Lines overlap - add endpoints
                    coords = list(intersection.coords)
                    if coords:
                        intersection_points.add((coords[0][0], coords[0][1]))
                        intersection_points.add((coords[-1][0], coords[-1][1]))
    
    # Also add all line endpoints as potential break points
    for line in all_lines:
        coords = list(line.coords)
        if coords:
            intersection_points.add((coords[0][0], coords[0][1]))
            intersection_points.add((coords[-1][0], coords[-1][1]))
    
    log_debug(f"Found {len(intersection_points)} intersection points")
    
    # Convert to Point geometries
    split_points = [Point(x, y) for x, y in intersection_points]
    split_points_geom = unary_union(split_points)
    
    # Break each line at intersection points
    broken_lines = []
    
    for line in all_lines:
        # Find which split points are ON this line (within tolerance)
        points_on_line = []
        for pt in split_points:
            # Check if point is on the line (not just intersecting bounds)
            dist = line.distance(pt)
            if dist < tolerance:
                # Project point onto line to get exact position
                projected_dist = line.project(pt)
                # Only add if not at the very start or end
                if tolerance < projected_dist < (line.length - tolerance):
                    points_on_line.append(pt)
        
        if not points_on_line:
            # No split points on this line, keep as-is
            broken_lines.append(line)
        else:
            # Split the line at all points
            current_geom = line
            for pt in points_on_line:
                try:
                    # Buffer the point slightly to ensure it intersects
                    pt_buffered = pt.buffer(tolerance * 2)
                    result = split(current_geom, pt_buffered)
                    
                    if hasattr(result, 'geoms') and len(result.geoms) > 1:
                        # Successfully split - keep first part, continue with rest
                        for part in result.geoms[:-1]:
                            if isinstance(part, LineString) and part.length > tolerance:
                                broken_lines.append(part)
                        current_geom = result.geoms[-1]
                    # else: split failed, continue with current geometry
                except Exception as e:
                    log_debug(f"Failed to split line at point: {str(e)}")
            
            # Add the remaining part
            if isinstance(current_geom, LineString) and current_geom.length > tolerance:
                broken_lines.append(current_geom)
            elif isinstance(current_geom, MultiLineString):
                for part in current_geom.geoms:
                    if part.length > tolerance:
                        broken_lines.append(part)
    
    log_info(f"Broke {len(all_lines)} lines into {len(broken_lines)} segments for layer '{layer_name}'")
    
    # Create GeoDataFrame
    result_gdf = gpd.GeoDataFrame(geometry=broken_lines, crs=crs)
    
    return result_gdf

