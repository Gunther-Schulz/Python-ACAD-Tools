#!/usr/bin/env python3
"""
Clean Line Operation - Remove degenerate vertices and short segments from LineStrings

This operation specifically targets LineString geometries and:
- Removes consecutive duplicate vertices (same vertex appearing twice)
- Removes very short segments (below minSegmentLength threshold)
- Optionally simplifies using Douglas-Peucker algorithm
- Handles both LineString and MultiLineString geometries
"""

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point
import numpy as np
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import ensure_geodataframe


def create_clean_line_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Clean LineString geometries by removing degenerate vertices and short segments.
    
    Parameters:
    -----------
    tolerance : float
        Distance threshold for merging close vertices (default: 0.01m = 1cm)
    minSegmentLength : float
        Minimum segment length to keep (default: 0.5m)
        Segments shorter than this will be removed
    simplifyTolerance : float
        Douglas-Peucker simplification tolerance (default: 0.0 = disabled)
        Set to 0 to disable simplification
    """
    if layer_name not in all_layers:
        log_error(f"Layer '{layer_name}' not found for cleanLine operation")
        return None
    
    input_gdf = all_layers[layer_name].copy()
    if input_gdf.empty:
        log_warning(f"Layer '{layer_name}' is empty")
        return input_gdf
    
    # Parameters
    tolerance = operation.get('tolerance', 0.01)  # 1cm threshold
    min_segment_length = operation.get('minSegmentLength', 0.5)  # 0.5m minimum
    simplify_tolerance = operation.get('simplifyTolerance', 0.0)  # Disabled by default
    
    log_info(f"cleanLine for layer '{layer_name}': tolerance={tolerance}, minSegment={min_segment_length}, simplify={simplify_tolerance}")
    
    # Process each geometry
    cleaned_geometries = []
    total_vertices_removed = 0
    total_segments_removed = 0
    
    for idx, row in input_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        
        try:
            if isinstance(geom, LineString):
                cleaned_geom, stats = _clean_linestring(
                    geom, tolerance, min_segment_length, simplify_tolerance, idx
                )
                total_vertices_removed += stats['vertices_removed']
                total_segments_removed += stats['segments_removed']
                
            elif isinstance(geom, MultiLineString):
                cleaned_parts = []
                for i, line in enumerate(geom.geoms):
                    cleaned_line, stats = _clean_linestring(
                        line, tolerance, min_segment_length, simplify_tolerance, f"{idx}-{i}"
                    )
                    total_vertices_removed += stats['vertices_removed']
                    total_segments_removed += stats['segments_removed']
                    
                    if cleaned_line and not cleaned_line.is_empty:
                        cleaned_parts.append(cleaned_line)
                
                cleaned_geom = MultiLineString(cleaned_parts) if cleaned_parts else None
            else:
                # Not a line geometry, keep as-is
                cleaned_geom = geom
            
            if cleaned_geom and not cleaned_geom.is_empty and cleaned_geom.is_valid:
                new_row = row.copy()
                new_row.geometry = cleaned_geom
                cleaned_geometries.append(new_row)
            else:
                log_warning(f"Feature {idx}: Cleaning resulted in empty/invalid geometry")
                
        except Exception as e:
            log_warning(f"Feature {idx}: Error during line cleaning - {e}, keeping original")
            new_row = row.copy()
            cleaned_geometries.append(new_row)
    
    # Summary logging
    if total_vertices_removed > 0 or total_segments_removed > 0:
        log_info(f"cleanLine for layer '{layer_name}': Removed {total_vertices_removed} duplicate vertices and {total_segments_removed} short segments from {len(cleaned_geometries)} features")
    
    if cleaned_geometries:
        result_gdf = gpd.GeoDataFrame(cleaned_geometries, crs=crs)
        return ensure_geodataframe(all_layers, project_settings, crs, layer_name, result_gdf)
    else:
        log_warning(f"No valid geometries after line cleaning for layer '{layer_name}'")
        return gpd.GeoDataFrame(geometry=[], crs=crs)


def _clean_linestring(linestring, tolerance, min_segment_length, simplify_tolerance, label):
    """
    Clean a single LineString by removing degenerate vertices and short segments.
    
    Returns:
        tuple: (cleaned_linestring, stats_dict)
    """
    if not isinstance(linestring, LineString) or linestring.is_empty:
        return linestring, {'vertices_removed': 0, 'segments_removed': 0}
    
    original_coords = list(linestring.coords)
    if len(original_coords) < 2:
        return linestring, {'vertices_removed': 0, 'segments_removed': 0}
    
    stats = {'vertices_removed': 0, 'segments_removed': 0}
    
    try:
        # STEP 1: Remove consecutive duplicate vertices
        cleaned_coords, duplicates = _remove_consecutive_duplicates_line(original_coords, tolerance)
        stats['vertices_removed'] += duplicates
        
        if len(cleaned_coords) < 2:
            log_debug(f"Feature {label}: Too few vertices after duplicate removal")
            return None, stats
        
        # STEP 2: Remove very short segments
        cleaned_coords, short_segments = _remove_short_segments(cleaned_coords, min_segment_length)
        stats['segments_removed'] += short_segments
        
        if len(cleaned_coords) < 2:
            log_debug(f"Feature {label}: Too few vertices after short segment removal")
            return None, stats
        
        # Create cleaned linestring
        cleaned = LineString(cleaned_coords)
        
        # STEP 3: Optional simplification
        if simplify_tolerance > 0:
            cleaned = cleaned.simplify(simplify_tolerance, preserve_topology=False)
            if cleaned.is_empty or not cleaned.is_valid:
                log_debug(f"Feature {label}: Simplification failed")
                cleaned = LineString(cleaned_coords)
        
        if stats['vertices_removed'] > 0 or stats['segments_removed'] > 0:
            log_debug(f"Feature {label}: Removed {stats['vertices_removed']} duplicate vertices, {stats['segments_removed']} short segments (original: {len(original_coords)} → final: {len(cleaned.coords)} vertices)")
        
        return cleaned, stats
        
    except Exception as e:
        log_error(f"Feature {label}: Error in line cleaning - {e}")
        return linestring, {'vertices_removed': 0, 'segments_removed': 0}


def _remove_consecutive_duplicates_line(coords, tolerance):
    """
    Remove consecutive duplicate or near-duplicate vertices.
    
    Returns:
        tuple: (cleaned_coords, num_duplicates_removed)
    """
    if len(coords) < 2:
        return coords, 0
    
    cleaned = [coords[0]]
    duplicates = 0
    
    for i in range(1, len(coords)):
        current = Point(coords[i])
        previous = Point(cleaned[-1])
        
        # Check if points are effectively the same (within tolerance)
        if current.distance(previous) > tolerance:
            cleaned.append(coords[i])
        else:
            duplicates += 1
            log_debug(f"Removed duplicate vertex at position {i}: {coords[i]} (distance: {current.distance(previous):.6f})")
    
    return cleaned, duplicates


def _remove_short_segments(coords, min_segment_length):
    """
    Remove vertices that create very short segments.
    
    This is the key fix for the alternating block rotation problem!
    When a line has segments like: [..., 0.00, 0.28, 0.00, 1.04, 0.00, ...]
    those zero-length segments cause the angle interpolation to alternate wildly.
    
    Returns:
        tuple: (cleaned_coords, num_segments_removed)
    """
    if len(coords) < 3 or min_segment_length <= 0:
        return coords, 0
    
    # Always keep first vertex
    cleaned = [coords[0]]
    segments_removed = 0
    
    i = 1
    while i < len(coords):
        # Calculate distance from last kept vertex to current vertex
        p1 = Point(cleaned[-1])
        p2 = Point(coords[i])
        segment_length = p1.distance(p2)
        
        # If segment is too short, skip this vertex (unless it's the last one)
        if segment_length < min_segment_length and i < len(coords) - 1:
            segments_removed += 1
            log_debug(f"Removed vertex creating short segment ({segment_length:.3f}m < {min_segment_length}m): {coords[i]}")
            i += 1
            continue
        
        # Keep this vertex
        cleaned.append(coords[i])
        i += 1
    
    # Ensure we always have at least 2 vertices
    if len(cleaned) < 2 and len(coords) >= 2:
        # Fallback: keep first and last
        cleaned = [coords[0], coords[-1]]
        segments_removed = len(coords) - 2
    
    return cleaned, segments_removed

