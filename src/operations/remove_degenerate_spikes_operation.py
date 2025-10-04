#!/usr/bin/env python3
"""
Remove degenerate spikes - zero-width features where polygon edges 
go out and return on the exact same path.

This operation specifically targets:
- Duplicate/near-duplicate consecutive vertices
- Zero-width spikes (edge goes A→B→A)
- Collinear points that create zero-area features
"""

import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import ensure_geodataframe


def create_remove_degenerate_spikes_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Remove degenerate spikes using multiple aggressive techniques.
    
    Parameters:
    -----------
    tolerance : float
        Distance threshold for merging close vertices (default: 0.01m)
    simplify_tolerance : float
        Douglas-Peucker simplification tolerance (default: 0.05m)
    min_spike_length : float
        Minimum length to consider as spike (default: 0.1m)
    """
    if layer_name not in all_layers:
        log_error(f"Layer '{layer_name}' not found for remove degenerate spikes operation")
        return None
    
    input_gdf = all_layers[layer_name].copy()
    if input_gdf.empty:
        log_warning(f"Layer '{layer_name}' is empty")
        return input_gdf
    
    # Parameters
    tolerance = operation.get('tolerance', 0.01)  # 1cm threshold for merging vertices
    simplify_tolerance = operation.get('simplifyTolerance', 0.05)  # 5cm simplification
    min_spike_length = operation.get('minSpikeLength', 0.1)  # 10cm minimum spike
    
    log_debug(f"removeDegenerateSpikes for layer '{layer_name}': tolerance={tolerance}, simplify={simplify_tolerance}, minSpike={min_spike_length}")
    
    # Process each geometry
    cleaned_geometries = []
    total_spikes_removed = 0
    total_original_area = 0
    total_cleaned_area = 0
    
    for idx, row in input_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        
        log_debug(f"Processing feature {idx}: {geom.geom_type}, area={geom.area:.1f}")
        original_area = geom.area
        
        try:
            if isinstance(geom, Polygon):
                cleaned_geom, spikes_removed = _remove_degenerate_spikes_from_polygon(
                    geom, tolerance, simplify_tolerance, min_spike_length, idx
                )
            elif isinstance(geom, MultiPolygon):
                cleaned_parts = []
                spikes_removed = 0
                for i, poly in enumerate(geom.geoms):
                    cleaned_poly, part_spikes = _remove_degenerate_spikes_from_polygon(
                        poly, tolerance, simplify_tolerance, min_spike_length, f"{idx}-{i}"
                    )
                    spikes_removed += part_spikes
                    if cleaned_poly and not cleaned_poly.is_empty:
                        cleaned_parts.append(cleaned_poly)
                
                cleaned_geom = MultiPolygon(cleaned_parts) if cleaned_parts else None
            else:
                cleaned_geom = geom
                spikes_removed = 0
            
            total_spikes_removed += spikes_removed
            
            if cleaned_geom and not cleaned_geom.is_empty and cleaned_geom.is_valid:
                new_row = row.copy()
                new_row.geometry = cleaned_geom
                cleaned_geometries.append(new_row)
                total_original_area += original_area
                total_cleaned_area += cleaned_geom.area
            else:
                log_warning(f"Feature {idx}: Cleaning resulted in empty/invalid geometry")
                
        except Exception as e:
            log_warning(f"Feature {idx}: Error during spike removal - {e}, keeping original")
            new_row = row.copy()
            cleaned_geometries.append(new_row)
            total_original_area += original_area
            total_cleaned_area += original_area
    
    # Only log if something was actually removed
    if total_spikes_removed > 0:
        area_change_pct = abs(total_original_area - total_cleaned_area) / total_original_area * 100 if total_original_area > 0 else 0
        log_info(f"removeDegenerateSpikes for layer '{layer_name}': Removed {total_spikes_removed} spikes from {len(cleaned_geometries)} features (area change: {area_change_pct:.2f}%)")
    
    if cleaned_geometries:
        result_gdf = gpd.GeoDataFrame(cleaned_geometries, crs=crs)
        return ensure_geodataframe(all_layers, project_settings, crs, layer_name, result_gdf)
    else:
        log_warning(f"No valid geometries after spike removal for layer '{layer_name}'")
        return gpd.GeoDataFrame(geometry=[], crs=crs)


def _remove_degenerate_spikes_from_polygon(polygon, tolerance, simplify_tolerance, min_spike_length, label):
    """Remove degenerate spikes from a single polygon using aggressive multi-step approach."""
    
    if not isinstance(polygon, Polygon) or polygon.is_empty:
        return polygon, 0
    
    original_coords = len(polygon.exterior.coords)
    spikes_removed = 0
    
    try:
        # STEP 0A: Remove consecutive duplicate vertices (same vertex appearing twice)
        cleaned = _remove_consecutive_duplicates(polygon)
        if cleaned is None or cleaned.is_empty:
            log_debug(f"Feature {label}: consecutive duplicate removal failed")
            return polygon, 0
        
        # STEP 0B: Remove collinear points (THE REAL FIX!)
        # When C→D→F are on the same line, D creates a zero-width spike
        cleaned = _remove_collinear_vertices(cleaned, tolerance)
        if cleaned is None or cleaned.is_empty:
            log_debug(f"Feature {label}: collinear vertex removal failed")
            return polygon, 0
        
        # STEP 1: Fix topology with buffer(0) - this removes many degenerate features
        cleaned = cleaned.buffer(0)
        if cleaned.is_empty or not cleaned.is_valid:
            log_debug(f"Feature {label}: buffer(0) failed")
            return polygon, 0
        
        # Handle case where buffer(0) creates MultiPolygon (take largest)
        if isinstance(cleaned, MultiPolygon):
            cleaned = max(cleaned.geoms, key=lambda p: p.area)
        
        # STEP 2: Merge close vertices (removes near-duplicates)
        cleaned = _merge_close_vertices_polygon(cleaned, tolerance)
        if cleaned is None or cleaned.is_empty:
            log_debug(f"Feature {label}: vertex merge failed")
            return polygon, 0
        
        # STEP 3: Simplify to remove collinear/redundant points
        cleaned = cleaned.simplify(simplify_tolerance, preserve_topology=True)
        if cleaned.is_empty or not cleaned.is_valid:
            log_debug(f"Feature {label}: simplify failed")
            return polygon, 0
        
        # STEP 4: Remove spike-like protrusions using negative buffer trick
        # This catches thin spikes that survived previous steps
        buffer_amount = min(min_spike_length / 2, 0.1)  # Use half spike length
        eroded = cleaned.buffer(-buffer_amount)
        
        if not eroded.is_empty:
            # Restore original size
            restored = eroded.buffer(buffer_amount)
            if restored.is_valid and not restored.is_empty:
                # Handle MultiPolygon result (take largest)
                if isinstance(restored, MultiPolygon):
                    restored = max(restored.geoms, key=lambda p: p.area)
                cleaned = restored
        
        # STEP 5: Final buffer(0) to ensure validity
        cleaned = cleaned.buffer(0)
        if isinstance(cleaned, MultiPolygon):
            cleaned = max(cleaned.geoms, key=lambda p: p.area)
        
        if cleaned.is_empty or not cleaned.is_valid:
            log_debug(f"Feature {label}: Final validation failed")
            return polygon, 0
        
        # Count removed vertices as proxy for spikes
        final_coords = len(cleaned.exterior.coords)
        spikes_removed = max(0, original_coords - final_coords)
        
        # Check if we changed something
        if spikes_removed > 0:
            area_loss = abs(polygon.area - cleaned.area) / polygon.area if polygon.area > 0 else 0
            log_debug(f"Feature {label}: Removed {spikes_removed} vertices/spikes, area change: {area_loss:.2%}")
        
        return cleaned, spikes_removed
        
    except Exception as e:
        log_error(f"Feature {label}: Error in spike removal - {e}")
        return polygon, 0


def _merge_close_vertices_polygon(polygon, tolerance):
    """Merge vertices that are closer than tolerance distance."""
    
    try:
        # Process exterior ring
        exterior_coords = list(polygon.exterior.coords)
        if len(exterior_coords) < 4:
            return polygon
        
        merged_exterior = [exterior_coords[0]]
        for i in range(1, len(exterior_coords)):
            current = Point(exterior_coords[i])
            previous = Point(merged_exterior[-1])
            
            # Keep vertex only if it's far enough from previous
            if current.distance(previous) > tolerance:
                merged_exterior.append(exterior_coords[i])
        
        # Ensure ring is closed
        if len(merged_exterior) >= 3:
            if merged_exterior[0] != merged_exterior[-1]:
                merged_exterior.append(merged_exterior[0])
        
        # Need at least 4 points to make a valid polygon (3 unique + closing point)
        if len(merged_exterior) < 4:
            log_debug("Merged exterior has too few points")
            return None
        
        # Process interior rings
        merged_interiors = []
        for interior in polygon.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) < 4:
                continue
            
            merged_interior = [interior_coords[0]]
            for i in range(1, len(interior_coords)):
                current = Point(interior_coords[i])
                previous = Point(merged_interior[-1])
                
                if current.distance(previous) > tolerance:
                    merged_interior.append(interior_coords[i])
            
            # Ensure ring is closed
            if len(merged_interior) >= 3:
                if merged_interior[0] != merged_interior[-1]:
                    merged_interior.append(merged_interior[0])
            
            # Only keep valid interior rings
            if len(merged_interior) >= 4:
                merged_interiors.append(merged_interior)
        
        # Create cleaned polygon
        return Polygon(merged_exterior, merged_interiors)
        
    except Exception as e:
        log_warning(f"Error merging vertices: {e}")
        return polygon


def _remove_consecutive_duplicates(polygon):
    """
    Remove consecutive duplicate vertices - THE KEY FIX for your problem!
    
    When a vertex appears twice in a row (e.g., C→D→D→F), this creates a 
    zero-width spike where the edge goes to D and immediately returns.
    
    This function removes such duplicates.
    """
    try:
        # Process exterior ring
        exterior_coords = list(polygon.exterior.coords)
        if len(exterior_coords) < 4:
            return polygon
        
        # Remove consecutive duplicates while preserving order
        cleaned_exterior = [exterior_coords[0]]
        duplicates_found = 0
        
        for i in range(1, len(exterior_coords)):
            current = exterior_coords[i]
            previous = cleaned_exterior[-1]
            
            # Only add if different from previous (exact comparison)
            if current != previous:
                cleaned_exterior.append(current)
            else:
                duplicates_found += 1
                log_debug(f"Found consecutive duplicate vertex at position {i}: {current}")
        
        # Ensure ring is still closed (first == last)
        if len(cleaned_exterior) >= 3:
            if cleaned_exterior[0] != cleaned_exterior[-1]:
                cleaned_exterior.append(cleaned_exterior[0])
        
        # Need at least 4 points to make a valid polygon (3 unique + closing point)
        if len(cleaned_exterior) < 4:
            log_warning("After removing duplicates, exterior has too few points")
            return None
        
        if duplicates_found > 0:
            log_info(f"Removed {duplicates_found} consecutive duplicate vertices from exterior")
        
        # Process interior rings
        cleaned_interiors = []
        for interior in polygon.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) < 4:
                continue
            
            cleaned_interior = [interior_coords[0]]
            interior_duplicates = 0
            
            for i in range(1, len(interior_coords)):
                current = interior_coords[i]
                previous = cleaned_interior[-1]
                
                if current != previous:
                    cleaned_interior.append(current)
                else:
                    interior_duplicates += 1
            
            # Ensure ring is closed
            if len(cleaned_interior) >= 3:
                if cleaned_interior[0] != cleaned_interior[-1]:
                    cleaned_interior.append(cleaned_interior[0])
            
            # Only keep valid interior rings
            if len(cleaned_interior) >= 4:
                cleaned_interiors.append(cleaned_interior)
                if interior_duplicates > 0:
                    log_info(f"Removed {interior_duplicates} consecutive duplicates from interior ring")
        
        # Create cleaned polygon
        return Polygon(cleaned_exterior, cleaned_interiors)
        
    except Exception as e:
        log_warning(f"Error removing consecutive duplicates: {e}")
        return polygon


def _remove_collinear_vertices(polygon, tolerance=0.01):
    """
    Remove collinear vertices - THIS IS THE KEY FIX for your problem!
    
    When C→D→F are on the same line (or very close), D is unnecessary and 
    creates a zero-width spike. This function removes such intermediate collinear points.
    
    Uses cross-product to determine if three consecutive points are collinear:
    If cross_product(C→D, D→F) ≈ 0, then C,D,F are collinear → remove D
    """
    import numpy as np
    
    try:
        # Process exterior ring
        exterior_coords = list(polygon.exterior.coords)
        if len(exterior_coords) < 4:
            return polygon
        
        cleaned_exterior = [exterior_coords[0]]
        collinear_removed = 0
        
        # Check each vertex (except first and last which is the same as first)
        for i in range(1, len(exterior_coords) - 1):
            prev_point = np.array(cleaned_exterior[-1])
            current_point = np.array(exterior_coords[i])
            next_point = np.array(exterior_coords[i + 1])
            
            # Calculate vectors
            vec1 = current_point - prev_point
            vec2 = next_point - current_point
            
            # Calculate cross product (in 2D, this gives the z-component)
            cross_product = vec1[0] * vec2[1] - vec1[1] * vec2[0]
            
            # Calculate the distance from current point to the line prev→next
            # This is more robust than just cross product
            if np.linalg.norm(vec1) > 0 and np.linalg.norm(vec2) > 0:
                # Normalize
                cross_product_normalized = abs(cross_product) / (np.linalg.norm(vec1) + np.linalg.norm(vec2))
                
                # If cross product is very small, points are collinear
                if cross_product_normalized < tolerance:
                    collinear_removed += 1
                    log_debug(f"Removed collinear vertex at position {i}: {current_point} (cross_product: {cross_product_normalized:.6f})")
                    continue  # Skip this vertex
            
            cleaned_exterior.append(tuple(current_point))
        
        # Close the ring
        if len(cleaned_exterior) >= 3:
            cleaned_exterior.append(cleaned_exterior[0])
        
        # Need at least 4 points (3 unique + closing)
        if len(cleaned_exterior) < 4:
            log_warning("After removing collinear vertices, exterior has too few points")
            return None
        
        if collinear_removed > 0:
            log_debug(f"Removed {collinear_removed} collinear vertices from exterior")
        
        # Process interior rings
        cleaned_interiors = []
        for interior in polygon.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) < 4:
                continue
            
            cleaned_interior = [interior_coords[0]]
            interior_collinear = 0
            
            for i in range(1, len(interior_coords) - 1):
                prev_point = np.array(cleaned_interior[-1])
                current_point = np.array(interior_coords[i])
                next_point = np.array(interior_coords[i + 1])
                
                vec1 = current_point - prev_point
                vec2 = next_point - current_point
                
                cross_product = vec1[0] * vec2[1] - vec1[1] * vec2[0]
                
                if np.linalg.norm(vec1) > 0 and np.linalg.norm(vec2) > 0:
                    cross_product_normalized = abs(cross_product) / (np.linalg.norm(vec1) + np.linalg.norm(vec2))
                    
                    if cross_product_normalized < tolerance:
                        interior_collinear += 1
                        continue
                
                cleaned_interior.append(tuple(current_point))
            
            # Close the ring
            if len(cleaned_interior) >= 3:
                cleaned_interior.append(cleaned_interior[0])
            
            if len(cleaned_interior) >= 4:
                cleaned_interiors.append(cleaned_interior)
                if interior_collinear > 0:
                    log_debug(f"Removed {interior_collinear} collinear vertices from interior ring")
        
        # Create cleaned polygon
        return Polygon(cleaned_exterior, cleaned_interiors)
        
    except Exception as e:
        log_warning(f"Error removing collinear vertices: {e}")
        return polygon

