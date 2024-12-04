import os
import geopandas as gpd
from pathlib import Path
from src.utils import log_debug, log_error, log_warning, ensure_path_exists
import traceback

def _normalize_field_name(name: str, max_length: int = 10) -> str:
    """
    Normalize field names to be shapefile-compatible.
    
    Args:
        name: Original field name
        max_length: Maximum length for the field name (10 for shapefiles)
    
    Returns:
        Normalized field name
    """
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
    
    # First try to replace common words with abbreviations
    name_lower = name.lower()
    for word, abbrev in abbreviations.items():
        if word in name_lower:
            name = name.replace(word, abbrev)
    
    # If still too long, intelligently truncate
    if len(name) > max_length:
        # Remove vowels from the middle of the string, keeping first and last characters
        vowels = 'aeiouAEIOU'
        chars = list(name)
        for i in range(1, len(chars) - 1):
            if len(''.join(chars)) <= max_length:
                break
            if chars[i] in vowels:
                chars[i] = ''
        name = ''.join(chars)
        
        # If still too long, truncate to max_length
        if len(name) > max_length:
            name = name[:max_length]
    
    return name

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

        # Verify geometry types are consistent
        geom_types = set(gdf.geometry.geom_type)
        if len(geom_types) > 1:
            log_error(f"Mixed geometry types found in GeoDataFrame: {geom_types}")
            return False

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