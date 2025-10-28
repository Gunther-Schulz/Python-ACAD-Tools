import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
from shapely.ops import split, unary_union, linemerge
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
    intersections_found = 0
    
    # Check each pair of lines for intersections
    for i in range(len(all_lines)):
        for j in range(i + 1, len(all_lines)):
            line1 = all_lines[i]
            line2 = all_lines[j]
            
            if line1.intersects(line2):
                intersections_found += 1
                intersection = line1.intersection(line2)
                
                # Extract points from intersection
                if isinstance(intersection, Point):
                    intersection_points.add((intersection.x, intersection.y))
                elif isinstance(intersection, MultiPoint):
                    for pt in intersection.geoms:
                        intersection_points.add((pt.x, pt.y))
                elif isinstance(intersection, LineString):
                    # Lines overlap - add only ENDPOINTS (corners)
                    coords = list(intersection.coords)
                    if coords:
                        # Add start and end points only
                        intersection_points.add((coords[0][0], coords[0][1]))
                        intersection_points.add((coords[-1][0], coords[-1][1]))
                elif isinstance(intersection, MultiLineString):
                    # Multiple overlapping segments - merge connected segments
                    # Use linemerge to join connected line segments
                    merged = linemerge(intersection)
                    if isinstance(merged, LineString):
                        # Successfully merged into single line - add endpoints
                        coords = list(merged.coords)
                        if coords:
                            intersection_points.add((coords[0][0], coords[0][1]))
                            intersection_points.add((coords[-1][0], coords[-1][1]))
                    else:
                        # Still MultiLineString - add endpoints of each disconnected part
                        for line_part in merged.geoms if hasattr(merged, 'geoms') else [merged]:
                            coords = list(line_part.coords)
                            if coords:
                                intersection_points.add((coords[0][0], coords[0][1]))
                                intersection_points.add((coords[-1][0], coords[-1][1]))
    
    # Also add all line endpoints as potential break points
    for line in all_lines:
        coords = list(line.coords)
        if coords:
            intersection_points.add((coords[0][0], coords[0][1]))
            intersection_points.add((coords[-1][0], coords[-1][1]))
    
    log_info(f"Found {intersections_found} intersections between {len(all_lines)} lines, resulting in {len(intersection_points)} break points")
    
    # Convert to Point geometries
    split_points = [Point(x, y) for x, y in intersection_points]
    split_points_geom = unary_union(split_points)
    
    # Break each line at intersection points
    broken_lines = []
    
    for line_idx, line in enumerate(all_lines):
        # Find which split points are ON this line (within tolerance)
        points_on_line = []
        for pt in split_points:
            # Check if point is on the line (not just intersecting bounds)
            dist = line.distance(pt)
            if dist < tolerance:
                # Project point onto line to get exact position
                projected_dist = line.project(pt)
                # Add ALL points that are on the line
                # Don't exclude endpoints - shared edges can start/end at polygon corners
                points_on_line.append((projected_dist, pt))
        
        if not points_on_line:
            # No split points on this line, keep as-is
            broken_lines.append(line)
        else:
            # Sort points by distance along line
            points_on_line.sort(key=lambda x: x[0])
            
            # Use substring to extract segments (preserves all vertices)
            split_distances = [0.0] + [dist for dist, pt in points_on_line] + [line.length]
            
            # Remove duplicate distances
            unique_distances = []
            for dist in split_distances:
                if not unique_distances or abs(dist - unique_distances[-1]) > tolerance:
                    unique_distances.append(dist)
            
            # Create segments between consecutive distances
            segments_created = 0
            for i in range(len(unique_distances) - 1):
                start_dist = unique_distances[i]
                end_dist = unique_distances[i + 1]
                
                if end_dist - start_dist > tolerance:
                    # Use substring to extract the segment (preserves all vertices!)
                    try:
                        from shapely.ops import substring
                        segment = substring(line, start_dist, end_dist)
                        
                        if segment and segment.length > tolerance:
                            broken_lines.append(segment)
                            segments_created += 1
                    except Exception as e:
                        log_debug(f"Failed to create substring: {str(e)}")
                        # Fallback: use interpolate for start/end
                        try:
                            start_pt = line.interpolate(start_dist)
                            end_pt = line.interpolate(end_dist)
                            segment = LineString([start_pt, end_pt])
                            if segment.length > tolerance:
                                broken_lines.append(segment)
                                segments_created += 1
                        except:
                            pass
    
    log_info(f"Broke {len(all_lines)} lines into {len(broken_lines)} segments for layer '{layer_name}'")
    
    # Create GeoDataFrame
    result_gdf = gpd.GeoDataFrame(geometry=broken_lines, crs=crs)
    
    return result_gdf

