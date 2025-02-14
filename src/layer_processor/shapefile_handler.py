"""Module for handling shapefile operations."""

import os
from src.core.utils import log_warning, log_error, log_debug, resolve_path
from src.geo.shapefile_utils import (
    write_shapefile,
    _delete_existing_shapefile,
    _verify_shapefile_components
)
import geopandas as gpd

class ShapefileHandler:
    def __init__(self, layer_processor):
        try:
            self.layer_processor = layer_processor
            self.project_settings = layer_processor.project_settings
            self.all_layers = layer_processor.all_layers
            self.crs = layer_processor.crs
            self.folder_prefix = layer_processor.project_loader.folder_prefix
            log_debug("Shapefile handler initialized successfully")
        except Exception as e:
            log_error(f"Error initializing shapefile handler: {str(e)}")
            raise

    def setup_shapefiles(self):
        """Set up shapefiles for all layers."""
        try:
            log_debug("Starting shapefile setup")
            processed_count = 0
            error_count = 0
            
            for layer in self.project_settings.get('geomLayers', []):
                layer_name = layer.get('name')
                if not layer_name:
                    continue

                shapefile = layer.get('shapeFile')
                if not shapefile:
                    continue

                try:
                    log_debug(f"Loading shapefile for layer {layer_name}: {shapefile}")
                    # Convert Fiona collection to GeoDataFrame immediately
                    gdf = gpd.read_file(shapefile)
                    
                    # Standardize CRS
                    if gdf.crs != self.crs:
                        log_debug(f"Converting CRS for layer {layer_name} from {gdf.crs} to {self.crs}")
                        gdf = gdf.to_crs(self.crs)
                    
                    # Prepare geometry for DXF if needed
                    if layer.get('updateDxf', False):
                        log_debug(f"Preparing geometry for DXF export in layer {layer_name}")
                        gdf.geometry = gdf.geometry.apply(
                            lambda geom: self.layer_processor.geometry_handler.prepare_geometry_for_dxf(geom, layer_name)
                        )
                        
                    self.all_layers[layer_name] = gdf
                    processed_count += 1
                    log_debug(f"Successfully loaded shapefile for layer {layer_name}")
                except Exception as e:
                    error_count += 1
                    log_error(f"Error reading shapefile for layer {layer_name}: {str(e)}")
                    continue
                    
            log_debug(f"Shapefile setup complete. Processed: {processed_count}, Errors: {error_count}")
            
        except Exception as e:
            log_error(f"Error during shapefile setup: {str(e)}")
            raise

    def write_shapefile(self, layer_name):
        """Write a layer to a shapefile."""
        try:
            if layer_name not in self.all_layers:
                log_warning(f"Layer {layer_name} not found in all_layers")
                return False

            layer_info = next((layer for layer in self.project_settings['geomLayers'] 
                             if layer.get('name') == layer_name), None)
            if not layer_info:
                log_warning(f"Layer info not found for {layer_name}")
                return False

            output_dir = self.project_settings.get('shapefileOutputDir')
            if not output_dir:
                log_warning(f"No shapefileOutputDir specified in project settings")
                return False

            # Resolve output paths
            output_dir = resolve_path(output_dir, self.folder_prefix)
            output_file = (
                resolve_path(layer_info['outputShapeFile'], self.folder_prefix)
                if layer_info.get('outputShapeFile')
                else os.path.join(output_dir, f"{layer_name}.shp")
            )

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            log_debug(f"Writing shapefile for layer {layer_name} to {output_file}")
            
            # Get the layer data
            layer_data = self.all_layers[layer_name]
            
            # Verify geometry validity before writing
            if not layer_data.geometry.is_valid.all():
                log_warning(f"Invalid geometries found in layer {layer_name}, attempting to fix")
                layer_data.geometry = layer_data.geometry.buffer(0)
            
            # Write the shapefile
            success = write_shapefile(
                gdf=layer_data,
                output_path=output_file,
                delete_existing=True
            )
            
            if success:
                log_debug(f"Successfully wrote shapefile for layer {layer_name}")
            else:
                log_warning(f"Failed to write shapefile for layer {layer_name}")
                
            return success
            
        except Exception as e:
            log_error(f"Error writing shapefile for layer {layer_name}: {str(e)}")
            return False

    def delete_residual_shapefiles(self):
        """Delete any residual shapefiles."""
        try:
            output_dir = self.project_settings.get('shapefileOutputDir')
            if not output_dir:
                return

            deleted_count = 0
            for layer in self.project_settings.get('geomLayers', []):
                layer_name = layer.get('name')
                if not layer_name:
                    continue

                if not layer.get('outputShapeFile'):
                    continue

                if layer_name not in self.all_layers:
                    log_debug(f"Deleting residual files for layer {layer_name}")
                    if _delete_existing_shapefile(output_dir, layer_name):
                        deleted_count += 1
                        
            log_debug(f"Deleted {deleted_count} residual shapefile(s)")
            
        except Exception as e:
            log_error(f"Error deleting residual shapefiles: {str(e)}")

    def _get_geometry_error(self, geom):
        """Get error message for invalid geometry."""
        try:
            if not geom.is_valid:
                return str(geom.buffer(0).is_valid)
            return None
        except Exception as e:
            log_error(f"Error checking geometry validity: {str(e)}")
            return str(e) 