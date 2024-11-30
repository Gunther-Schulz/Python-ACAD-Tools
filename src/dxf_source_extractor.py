import ezdxf
import geopandas as gpd
from pathlib import Path
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists
from src.dump_to_shape import merge_dxf_layer_to_shapefile

class DXFSourceExtractor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.dxf_extracts = project_loader.project_settings.get('updateFromSource', [])
        self.crs = project_loader.crs

    def process_extracts(self, doc):
        """Process all DXF extracts defined in updateFromSource configuration"""
        if not self.dxf_extracts:
            log_info("No DXF extracts configured in updateFromSource")
            return
        
        for extract in self.dxf_extracts:
            source_layer = extract.get('sourceLayer')
            output_file = extract.get('outputShapeFile')
            
            if not source_layer or not output_file:
                log_warning(f"Skipping invalid DXF extract configuration: {extract}")
                continue
            
            if source_layer not in doc.layers:
                log_warning(f"Source layer '{source_layer}' not found in DXF document")
                continue
                
            self._process_single_extract(doc, source_layer, output_file)

    def _process_single_extract(self, doc, source_layer, output_file):
        """Extract geometries from a single DXF layer and save to shapefile"""
        print(f"Extracting geometries from DXF layer: {source_layer}")
        
        try:
            # Resolve the full output path
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)
            
            # Ensure output directory exists
            output_dir = str(Path(full_output_path).parent)
            if not ensure_path_exists(output_dir):
                log_error(f"Could not create output directory: {output_dir}")
                return

            # Get all entities from the source layer
            msp = doc.modelspace()
            entities = msp.query(f'*[layer=="{source_layer}"]')

            # Extract geometries from DXF layer and convert to shapefile
            # Use the full output path instead of creating a file based on the layer name
            merge_dxf_layer_to_shapefile(doc, str(Path(full_output_path).parent), Path(full_output_path).name.replace('.shp', ''), entities, self.crs)
            
        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")