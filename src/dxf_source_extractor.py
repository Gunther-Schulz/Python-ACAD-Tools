import ezdxf
import geopandas as gpd
from pathlib import Path
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists
from src.dump_to_shape import merge_dxf_layer_to_shapefile
from src.preprocessors.block_exploder import extract_circle_centers_from_blocks

class DXFSourceExtractor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.dxf_extracts = project_loader.project_settings.get('updateFromSource', [])
        self.crs = project_loader.crs
        self.preprocessors = {
            'block_exploder': extract_circle_centers_from_blocks
        }

    def process_extracts(self, default_doc):
        """Process all DXF extracts defined in updateFromSource configuration"""
        if not self.dxf_extracts:
            log_info("No DXF extracts configured in updateFromSource")
            return
        
        for extract in self.dxf_extracts:
            source_layer = extract.get('sourceLayer')
            output_file = extract.get('outputShapeFile')
            source_dxf = extract.get('sourceDxf')
            preprocessors = extract.get('preprocessors', [])
            
            if not source_layer or not output_file:
                log_warning(f"Skipping invalid DXF extract configuration: {extract}")
                continue
            
            # Load alternative DXF if specified
            doc = default_doc
            if source_dxf:
                try:
                    full_source_path = resolve_path(source_dxf, self.project_loader.folder_prefix)
                    doc = ezdxf.readfile(full_source_path)
                except Exception as e:
                    log_error(f"Failed to load alternative DXF {source_dxf}: {str(e)}")
                    continue
            
            if source_layer not in doc.layers:
                log_warning(f"Source layer '{source_layer}' not found in DXF document")
                continue
                
            self._process_single_extract(doc, source_layer, output_file, preprocessors)

    def _process_single_extract(self, doc, source_layer, output_file, preprocessors=None):
        """Extract geometries from a single DXF layer and save to shapefile"""
        print(f"Extracting geometries from DXF layer: {source_layer}")
        
        try:
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)
            output_dir = str(Path(full_output_path).parent)
            if not ensure_path_exists(output_dir):
                log_error(f"Could not create output directory: {output_dir}")
                return

            msp = doc.modelspace()
            entities = msp.query(f'*[layer=="{source_layer}"]')

            if preprocessors:
                # Process through each preprocessor in sequence
                processed_data = entities
                for preprocessor in preprocessors:
                    if preprocessor not in self.preprocessors:
                        log_warning(f"Preprocessor '{preprocessor}' not found, skipping")
                        continue
                    
                    log_info(f"Applying preprocessor: {preprocessor}")
                    processed_data = self.preprocessors[preprocessor](processed_data, source_layer)
                    log_info(f"Preprocessor {preprocessor} produced {len(processed_data)} features")
                
                # Convert final processed data to GeoDataFrame and save
                points_df = gpd.GeoDataFrame(
                    geometry=[gpd.points_from_xy([p[0]], [p[1]])[0] for p in processed_data],
                    crs=self.crs
                )
                points_df.to_file(full_output_path)
                log_info(f"Saved {len(processed_data)} processed features to {full_output_path}")
            else:
                # Use existing merge_dxf_layer_to_shapefile for standard processing
                merge_dxf_layer_to_shapefile(
                    doc, 
                    str(Path(full_output_path).parent),
                    Path(full_output_path).name.replace('.shp', ''),
                    entities,
                    self.crs
                )
            
        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")