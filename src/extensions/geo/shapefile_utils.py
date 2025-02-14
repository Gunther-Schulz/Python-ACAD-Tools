"""Utilities for handling shapefile operations."""

import os
import geopandas as gpd
from pathlib import Path
from src.utils import log_debug, log_error, log_warning, ensure_path_exists
import traceback
from typing import Set, Optional

def _normalize_field_name(name: str, max_length: int = 10) -> str:
    """
    Normalize field names to be shapefile-compatible.
    
    Args:
        name: Original field name
        max_length: Maximum length for the field name (10 for shapefiles)
    
    Returns:
        Normalized field name
    """
    # If name is already short enough, return it as-is
    if len(name) <= max_length:
        return name
        
    # Common abbreviations for longer words
    abbreviations = {
        'intersection': 'isect',
        'area': 'ar',
        'length': 'len',
        'distance': 'dist',
        'coordinate': 'coord',
        'position': 'pos',
        'elevation': 'elev',
        'height': 'ht',
        'width': 'wd',
        'diameter': 'dia',
        'radius': 'rad',
        'number': 'num',
        'description': 'desc',
        'identifier': 'id',
        'reference': 'ref',
        'category': 'cat',
        'attribute': 'attr',
        'parameter': 'param',
        'calculation': 'calc',
        'measurement': 'meas'
    }
    
    # Split name into words
    words = name.split('_')
    
    # Try abbreviating one word at a time until we're under the limit
    for i in range(len(words)):
        current_word = words[i].lower()
        if current_word in abbreviations:
            test_words = words.copy()
            test_words[i] = abbreviations[current_word]
            test_name = '_'.join(test_words)
            if len(test_name) <= max_length:
                return test_name
    
    # If still too long, remove vowels from the middle of words
    if len(name) > max_length:
        vowels = 'aeiouAEIOU'
        words = name.split('_')
        for i in range(len(words)):
            if len(''.join(words)) <= max_length:
                break
            # Keep first and last character, remove vowels from middle
            word = words[i]
            if len(word) > 3:
                chars = list(word)
                for j in range(1, len(chars) - 1):
                    if len('_'.join(words)) <= max_length:
                        break
                    if chars[j] in vowels:
                        chars[j] = ''
                words[i] = ''.join(chars)
        name = '_'.join(words)
    
    # If still too long, truncate
    if len(name) > max_length:
        name = name[:max_length]
    
    return name

def _validate_geometry_types(geom_types: Set[str], layer_name: str) -> Optional[str]:
    if not geom_types:
        return None
    
    # Handle case where None is mixed with a single valid type
    if None in geom_types and len(geom_types) == 2:
        valid_types = geom_types - {None}
        if len(valid_types) == 1:
            valid_type = valid_types.pop()
            log_warning(f"When saving Layer '{layer_name}': Mixed None and {valid_type} geometry types found. Using {valid_type}.")
            return valid_type

    # Handle mixed Polygon and MultiPolygon case
    if geom_types == {'Polygon', 'MultiPolygon'}:
        log_warning(f"Layer '{layer_name}': Mixed Polygon and MultiPolygon types found. Using Polygon (MultiPolygons will be exploded).")
        return 'Polygon'

    if len(geom_types) > 1:
        log_error(f"Layer '{layer_name}': Mixed geometry types found: {geom_types}")
        return None

    return geom_types.pop() if None not in geom_types else None

def write_shapefile(gdf: gpd.GeoDataFrame, output_path: str, delete_existing: bool = True) -> bool:
    """
    Write a GeoDataFrame to a shapefile.
    
    Args:
        gdf: GeoDataFrame to write
        output_path: Full path to the output shapefile (including .shp extension)
        delete_existing: Whether to delete existing shapefile components before writing
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if gdf is None or len(gdf) == 0:
            log_warning(f"Skipping empty GeoDataFrame for {output_path}")
            return False
            
        if not isinstance(gdf, gpd.GeoDataFrame):
            log_error(f"Cannot write shapefile {output_path}: Input is not a GeoDataFrame")
            return False

        # Validate geometry with detailed information
        invalid_geoms = ~gdf.geometry.is_valid
        if invalid_geoms.any():
            invalid_count = invalid_geoms.sum()
            invalid_indices = gdf.index[invalid_geoms].tolist()
            invalid_reasons = []
            for geom in gdf[invalid_geoms].geometry:
                if geom is None:
                    invalid_reasons.append("Geometry is None")
                else:
                    invalid_reasons.append(geom.explain_validity())
            
            log_warning(f"Found {invalid_count} invalid geometries in {output_path}")
            for idx, reason in zip(invalid_indices, invalid_reasons):
                log_warning(f"  - Feature at index {idx}: {reason}")

        # Verify geometry types are consistent
        geom_types = set(gdf.geometry.geom_type)
        valid_geom_type = _validate_geometry_types(geom_types, output_path)
        if valid_geom_type is None:
            return False

        # Explode MultiPolygons if mixed with Polygons
        if 'MultiPolygon' in geom_types and valid_geom_type == 'Polygon':
            gdf = gdf.explode(index_parts=True).reset_index(drop=True)
            log_debug(f"Exploded MultiPolygons into individual Polygons")

        # Convert long suffixes to short ones
        output_path = (
            output_path.replace('_points.', '_pt.')
            .replace('_lines.', '_ln.')
            .replace('_polygons.', '_pl.')
        )

        # Normalize column names
        rename_dict = {col: _normalize_field_name(col) for col in gdf.columns if col != 'geometry'}
        if rename_dict:
            # Log column name changes
            for original, normalized in rename_dict.items():
                if original != normalized:
                    log_debug(f"Normalized field name: '{original}' to '{normalized}'")
            gdf = gdf.rename(columns=rename_dict)

        output_dir = str(Path(output_path).parent)
        layer_name = Path(output_path).stem
        
        log_debug(f"Writing shapefile to: {output_path}")
        
        if not ensure_path_exists(output_dir):
            log_error(f"Could not create output directory: {output_dir}")
            return False
            
        if delete_existing:
            _delete_existing_shapefile(output_dir, layer_name)
        
        # Write the shapefile
        gdf.to_file(output_path)
        
        return _verify_shapefile_components(output_dir, layer_name)
            
    except Exception as e:
        log_error(f"Error writing shapefile {output_path}: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return False

def _delete_existing_shapefile(directory: str, layer_name: str):
    """Delete all existing shapefile components for the given layer."""
    log_debug(f"Deleting existing files for layer: {layer_name}")
    shapefile_extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', 
                          '.fbn', '.fbx', '.ain', '.aih', '.ixs', '.mxs', '.atx', '.xml']
    
    for ext in shapefile_extensions:
        file_path = os.path.join(directory, f"{layer_name}{ext}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                log_debug(f"Deleted file: {file_path}")
            except Exception as e:
                log_warning(f"Failed to delete {file_path}. Reason: {e}")

def _verify_shapefile_components(directory: str, layer_name: str) -> bool:
    """Verify that all required shapefile components exist."""
    required_extensions = ['.shp', '.shx', '.dbf', '.prj']
    missing_files = []
    
    for ext in required_extensions:
        component_path = os.path.join(directory, f"{layer_name}{ext}")
        if not os.path.exists(component_path):
            missing_files.append(ext)
            log_error(f"Missing shapefile component: {component_path}")
        else:
            log_debug(f"Found shapefile component: {component_path}")
    
    return len(missing_files) == 0 