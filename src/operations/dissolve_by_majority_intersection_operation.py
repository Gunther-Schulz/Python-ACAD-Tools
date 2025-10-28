"""
Dissolve By Majority Intersection Operation

Reconstructs coarse-resolution polygons using high-resolution constituent polygons
based on spatial overlap. Useful for creating accurate administrative boundaries
from higher-detail source data.

Example use case:
- Source: High-detail Gemarkung (cadastral district) boundaries
- Reference: Low-detail Gemeinde (municipality) boundaries  
- Result: Accurate Gemeinde boundaries reconstructed from Gemarkung polygons

Algorithm:
1. For each reference polygon (e.g., Gemeinde)
2. Find all source polygons (e.g., Gemarkung) where >50% of area overlaps
3. Dissolve matched source polygons into a single high-detail boundary
4. Transfer attributes from reference polygon to result
"""

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon
from src.utils import log_info, log_debug


def create_dissolve_by_majority_intersection_layer(
    all_layers, global_path_prefix, source_crs, layer_name, operation_config
):
    """
    Reconstruct polygons from higher-detail source data based on majority overlap.
    
    Args:
        all_layers: Dictionary of all available layers
        global_path_prefix: Base path for files
        source_crs: Coordinate reference system
        layer_name: Name of the layer being created
        operation_config: Configuration with:
            - sourceLayer: Name of high-detail source layer (e.g., 'Gemarkung Input')
            - referenceLayer: Name of low-detail reference layer (e.g., 'Gemeinde Input')
            - transferAttributes: List of attribute names to copy from reference to result
            - threshold: Optional, minimum overlap percentage (default: 50.0)
    
    Returns:
        GeoDataFrame with reconstructed polygons
    """
    source_layer_name = operation_config.get('sourceLayer')
    reference_layer_name = operation_config.get('referenceLayer')
    transfer_attrs = operation_config.get('transferAttributes', [])
    threshold = operation_config.get('threshold', 50.0)
    
    if not source_layer_name or not reference_layer_name:
        raise ValueError(
            f"dissolveByMajorityIntersection requires 'sourceLayer' and 'referenceLayer' "
            f"(got sourceLayer={source_layer_name}, referenceLayer={reference_layer_name})"
        )
    
    # Get the layers
    source_gdf = all_layers.get(source_layer_name)
    reference_gdf = all_layers.get(reference_layer_name)
    
    if source_gdf is None:
        raise ValueError(f"Source layer '{source_layer_name}' not found")
    if reference_gdf is None:
        raise ValueError(f"Reference layer '{reference_layer_name}' not found")
    
    if source_gdf.empty:
        log_info(f"Source layer '{source_layer_name}' is empty, returning empty result")
        return gpd.GeoDataFrame(geometry=[], crs=source_crs)
    
    if reference_gdf.empty:
        log_info(f"Reference layer '{reference_layer_name}' is empty, returning empty result")
        return gpd.GeoDataFrame(geometry=[], crs=source_crs)
    
    log_info(
        f"Reconstructing {len(reference_gdf)} polygons from {len(source_gdf)} source polygons "
        f"(threshold: {threshold}%)"
    )
    
    # Ensure both are in the same CRS
    if source_gdf.crs != reference_gdf.crs:
        reference_gdf = reference_gdf.to_crs(source_gdf.crs)
    
    # Build result list
    reconstructed_features = []
    
    # For each reference polygon, find matching source polygons
    for ref_idx, ref_row in reference_gdf.iterrows():
        ref_geom = ref_row.geometry
        
        if ref_geom is None or ref_geom.is_empty:
            continue
        
        # Find source polygons that overlap with this reference polygon
        matching_source_indices = []
        
        for src_idx, src_row in source_gdf.iterrows():
            src_geom = src_row.geometry
            
            if src_geom is None or src_geom.is_empty:
                continue
            
            # Check if they intersect at all
            if not src_geom.intersects(ref_geom):
                continue
            
            # Calculate overlap percentage (% of source polygon inside reference)
            intersection = src_geom.intersection(ref_geom)
            overlap_area = intersection.area
            source_area = src_geom.area
            
            if source_area > 0:
                overlap_pct = (overlap_area / source_area) * 100
                
                if overlap_pct >= threshold:
                    matching_source_indices.append(src_idx)
                    log_debug(
                        f"  Match: {src_row.get('name', src_idx)} -> "
                        f"{ref_row.get('name', ref_idx)} ({overlap_pct:.1f}% overlap)"
                    )
        
        # If we found matching source polygons, dissolve them
        if matching_source_indices:
            matched_sources = source_gdf.loc[matching_source_indices]
            
            # Dissolve all matched source polygons into one
            from shapely.ops import unary_union
            dissolved_geom = unary_union(matched_sources.geometry.tolist())
            
            # Create result feature with attributes from reference
            result_attrs = {}
            
            # Copy requested attributes from reference polygon
            for attr in transfer_attrs:
                if attr in ref_row.index:
                    result_attrs[attr] = ref_row[attr]
            
            # Add geometry
            result_attrs['geometry'] = dissolved_geom
            
            reconstructed_features.append(result_attrs)
            
            log_info(
                f"  Reconstructed '{ref_row.get(transfer_attrs[0] if transfer_attrs else 'name', ref_idx)}': "
                f"{len(matching_source_indices)} source polygons → "
                f"{dissolved_geom.area/1e6:.2f} km²"
            )
        else:
            log_debug(
                f"  No matches for reference polygon {ref_row.get('name', ref_idx)}"
            )
    
    # Create result GeoDataFrame
    if reconstructed_features:
        result_gdf = gpd.GeoDataFrame(reconstructed_features, crs=source_gdf.crs)
        log_info(
            f"Successfully reconstructed {len(result_gdf)} polygons from "
            f"{len(source_gdf)} source features"
        )
    else:
        log_info("No polygons reconstructed")
        result_gdf = gpd.GeoDataFrame(geometry=[], crs=source_crs)
    
    return result_gdf

