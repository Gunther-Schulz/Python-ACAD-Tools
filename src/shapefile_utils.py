import os
import geopandas as gpd
from pathlib import Path
from src.utils import log_debug, log_error, log_warning, ensure_path_exists

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
        
        # Verify all components were written
        if _verify_shapefile_components(output_dir, layer_name):
            log_debug(f"Successfully wrote shapefile: {output_path}")
            return True
        else:
            log_error(f"Failed to write complete shapefile: {output_path}")
            return False
            
    except Exception as e:
        log_error(f"Error writing shapefile {output_path}: {str(e)}")
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