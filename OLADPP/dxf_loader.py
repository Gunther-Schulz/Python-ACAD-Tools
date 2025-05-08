import os
import geopandas as gpd
import traceback
from src.dump_to_shape import merge_dxf_layer_to_shapefile
from src.utils import log_info, log_warning, log_error

def load_dxf_layer(layer_name, dxf_layer_name, dxf_doc, project_loader, crs):
    try:
        log_warning(f"Attempting to load DXF layer '{dxf_layer_name}' for layer: {layer_name}")
        
        if dxf_doc is None:
            log_warning("DXF document is None during DXF layer loading")
            return gpd.GeoDataFrame(geometry=[], crs=crs)
        else:
            log_warning("DXF document is loaded during DXF layer loading")
        
        # Check if source layer exists
        if dxf_layer_name not in dxf_doc.layers:
            log_warning(f"Source layer '{dxf_layer_name}' does not exist in DXF file")
            return gpd.GeoDataFrame(geometry=[], crs=crs)
        else:
            log_debug(f"Source layer '{dxf_layer_name}' exists in DXF file")
        
        msp = dxf_doc.modelspace()
        entities = msp.query(f'*[layer=="{dxf_layer_name}"]')
        
        # Create temporary directory in system temp
        temp_dir = os.path.join('/tmp', 'python_acad_tools')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Use existing merge_dxf_layer_to_shapefile function
        merge_dxf_layer_to_shapefile(
            project_loader.dxf_filename,
            temp_dir,
            layer_name,
            entities,
            crs
        )
        
        # Read the generated shapefile
        temp_shp = os.path.join(temp_dir, f"{layer_name}.shp")
        if os.path.exists(temp_shp):
            gdf = gpd.read_file(temp_shp)
            
            # Clean up temporary files
            for ext in ['.shp', '.shx', '.dbf', '.prj']:
                temp_file = os.path.join(temp_dir, f"{layer_name}{ext}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
            if not gdf.empty:
                log_debug(f"Successfully loaded {len(gdf)} features from DXF layer '{dxf_layer_name}'")
                return gdf
            
        log_warning(f"No valid geometries found in DXF layer '{dxf_layer_name}'")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
        
    except Exception as e:
        log_error(f"Failed to load DXF layer '{dxf_layer_name}': {str(e)}")
        log_error(traceback.format_exc())
        return gpd.GeoDataFrame(geometry=[], crs=crs)
