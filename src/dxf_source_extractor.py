import ezdxf
import geopandas as gpd
from pathlib import Path
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists, log_debug
from src.shapefile_utils import write_shapefile
from src.preprocessors.block_exploder import explode_blocks
from src.preprocessors.circle_extractor import extract_circle_centers
from src.layer_processor import LayerProcessor

class DXFSourceExtractor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.dxf_extracts = project_loader.project_settings.get('updateFromSource', [])
        self.crs = project_loader.crs
        self.preprocessors = {
            'block_exploder': explode_blocks,
            'circle_extractor': extract_circle_centers
        }

    def process_extracts(self, default_doc):
        """Process all DXF extracts defined in updateFromSource configuration"""
        if not self.dxf_extracts:
            log_debug("No DXF extracts configured in updateFromSource")
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
        log_debug(f"Extracting geometries from DXF layer: {source_layer}")
        
        try:
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)
            output_dir = str(Path(full_output_path).parent)
            log_debug(f"Output directory: {output_dir}")
            if not ensure_path_exists(output_dir):
                log_error(f"Could not create output directory: {output_dir}")
                return

            msp = doc.modelspace()
            entities = msp.query(f'*[layer=="{source_layer}"]')
            log_debug(f"Number of entities found: {len(entities)}")

            if preprocessors:
                # Process through each preprocessor in sequence
                processed_data = entities
                for preprocessor in preprocessors:
                    if preprocessor not in self.preprocessors:
                        log_warning(f"Preprocessor '{preprocessor}' not found, skipping")
                        continue
                    
                    log_debug(f"Applying preprocessor: {preprocessor}")
                    processed_data = self.preprocessors[preprocessor](processed_data, source_layer)
                    log_debug(f"Preprocessor {preprocessor} produced {len(processed_data)} features")
                
                # Convert final processed data to GeoDataFrame
                if isinstance(processed_data[0], dict):  # Check if we have features with attributes
                    points_df = gpd.GeoDataFrame(
                        geometry=[gpd.points_from_xy([p['coords'][0]], [p['coords'][1]])[0] for p in processed_data],
                        data=[p['attributes'] for p in processed_data],
                        crs=self.crs
                    )
                else:  # Backward compatibility for simple coordinate tuples
                    points_df = gpd.GeoDataFrame(
                        geometry=[gpd.points_from_xy([p[0]], [p[1]])[0] for p in processed_data],
                        crs=self.crs
                    )
                
                log_debug(f"GeoDataFrame created with {len(points_df)} features")
                # Store in layer_processor and write shapefile
                layer_name = Path(output_file).stem
                if write_shapefile(points_df, full_output_path):
                    log_debug(f"Successfully saved {len(processed_data)} processed features to {full_output_path}")
                else:
                    log_error(f"Failed to write {len(processed_data)} processed features to {full_output_path}")
            else:
                # Convert entities directly to GeoDataFrame
                geometries = []
                for entity in entities:
                    # Add logic here to convert DXF entities to shapely geometries
                    # This would replace the functionality from merge_dxf_layer_to_shapefile
                    # You'll need to implement the conversion logic based on your needs
                    pass
                
                gdf = gpd.GeoDataFrame(geometry=geometries, crs=self.crs)
                log_debug(f"GeoDataFrame created with {len(gdf)} features")
                layer_name = Path(output_file).stem
                if write_shapefile(gdf, full_output_path):
                    log_debug(f"Successfully saved shapefile to {full_output_path}")
                else:
                    log_error(f"Failed to write shapefile to {full_output_path}")
                
        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")