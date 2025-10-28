import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point
from src.utils import log_info, log_warning, log_debug
from src.operations.common_operations import format_operation_warning
import numpy as np

def create_remove_duplicate_lines_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Remove duplicate and overlapping line segments.
    Lines are considered duplicates if they occupy approximately the same space
    (within tolerance), regardless of direction.
    """
    
    # Get source layers
    source_layers = operation.get('layers', [layer_name])
    if not source_layers:
        source_layers = [layer_name]
    
    # Tolerance for considering lines as duplicates (default 1cm)
    tolerance = operation.get('tolerance', 0.01)
    
    all_lines = []
    
    # Collect all lines from source layers
    for source_layer_name in source_layers:
        if isinstance(source_layer_name, dict):
            source_layer_name = source_layer_name.get('name')
        
        if source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "removeDuplicateLines",
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
            "removeDuplicateLines",
            "No lines found to process"
        ))
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    log_debug(f"Checking {len(all_lines)} lines for duplicates (tolerance={tolerance}m)")
    
    # Track which lines to keep
    unique_lines = []
    skip_indices = set()
    
    duplicates_found = []  # Track what we're removing
    
    for i in range(len(all_lines)):
        if i in skip_indices:
            continue
        
        line1 = all_lines[i]
        is_duplicate = False
        
        # Check against all previously kept unique lines
        for unique_line in unique_lines:
            if _lines_are_duplicate(line1, unique_line, tolerance):
                is_duplicate = True
                skip_indices.add(i)
                duplicates_found.append((i, line1.length))
                break
        
        if not is_duplicate:
            # Also check remaining lines and mark them as duplicates
            for j in range(i + 1, len(all_lines)):
                if j not in skip_indices:
                    line2 = all_lines[j]
                    if _lines_are_duplicate(line1, line2, tolerance):
                        skip_indices.add(j)
                        duplicates_found.append((j, line2.length))
                        if line2.length > 1000:  # Log large "duplicates"
                            log_debug(f"  Removing large 'duplicate': {line2.length:.1f}m (indices {i}, {j})")
            
            unique_lines.append(line1)
    
    duplicates_removed = len(all_lines) - len(unique_lines)
    total_removed_length = sum(length for _, length in duplicates_found)
    log_debug(f"Removed {duplicates_removed} duplicate lines (total {total_removed_length:.1f}m), keeping {len(unique_lines)} unique lines for layer '{layer_name}'")
    
    # Create GeoDataFrame
    result_gdf = gpd.GeoDataFrame(geometry=unique_lines, crs=crs)
    
    return result_gdf


def _lines_are_duplicate(line1, line2, tolerance):
    """
    Check if two lines are duplicates (overlap within tolerance).
    Lines can be going in the same or opposite direction.
    ULTRA-STRICT: Lines must be nearly identical (shared polygon edges only).
    """
    
    # STRICT length check: duplicates must have VERY similar lengths
    length_ratio = min(line1.length, line2.length) / max(line1.length, line2.length)
    if length_ratio < 0.999:  # Within 0.1% - basically identical
        return False
    
    # STRICT endpoints check: both ends must match
    line1_coords = list(line1.coords)
    line2_coords = list(line2.coords)
    
    if len(line1_coords) < 2 or len(line2_coords) < 2:
        return False
    
    start1, end1 = Point(line1_coords[0]), Point(line1_coords[-1])
    start2, end2 = Point(line2_coords[0]), Point(line2_coords[-1])
    
    # Check if endpoints match (same or opposite direction)
    # Shared edges can be within 1 meter of each other
    check_tol = max(tolerance, 1.0)  # Use at least 1 meter
    same_dir = (start1.distance(start2) < check_tol and end1.distance(end2) < check_tol)
    opp_dir = (start1.distance(end2) < check_tol and end1.distance(start2) < check_tol)
    
    if not (same_dir or opp_dir):
        return False
    
    # Hausdorff distance: EVERY point must be close
    hausdorff_dist = line1.hausdorff_distance(line2)
    if hausdorff_dist > check_tol:
        return False
    
    # Final check: lines must actually overlap in space
    if not line1.buffer(check_tol).intersects(line2):
        return False
    
    # All checks passed - these are TRUE duplicates (shared edges)
    return True


def _lines_same_direction(line1, line2, tolerance):
    """
    Check if two lines go in approximately the same direction.
    Returns True if same direction, False if opposite direction, None if unclear.
    """
    coords1 = list(line1.coords)
    coords2 = list(line2.coords)
    
    if len(coords1) < 2 or len(coords2) < 2:
        return None
    
    # Compare start and end points
    start1 = np.array(coords1[0])
    end1 = np.array(coords1[-1])
    start2 = np.array(coords2[0])
    end2 = np.array(coords2[-1])
    
    # Distance from start1 to start2 and end1 to end2
    same_dir_dist = np.linalg.norm(start1 - start2) + np.linalg.norm(end1 - end2)
    
    # Distance from start1 to end2 and end1 to start2
    opp_dir_dist = np.linalg.norm(start1 - end2) + np.linalg.norm(end1 - start2)
    
    if same_dir_dist < opp_dir_dist:
        return True
    else:
        return False

