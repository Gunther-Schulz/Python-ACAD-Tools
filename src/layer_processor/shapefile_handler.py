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
        self.layer_processor = layer_processor
        self.project_settings = layer_processor.project_settings
        self.all_layers = layer_processor.all_layers
        self.crs = layer_processor.crs
        self.folder_prefix = layer_processor.project_loader.folder_prefix

    def setup_shapefiles(self):
        """Set up shapefiles for all layers."""
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
                if gdf.crs != self.crs:
                    log_debug(f"Converting CRS for layer {layer_name} from {gdf.crs} to {self.crs}")
                    gdf = gdf.to_crs(self.crs)
                self.all_layers[layer_name] = gdf
                log_debug(f"Successfully loaded shapefile for layer {layer_name}")
            except Exception as e:
                log_error(f"Error reading shapefile for layer {layer_name}: {str(e)}")
                raise

    def write_shapefile(self, layer_name):
        """Write a layer to a shapefile using the utility function."""
        if layer_name not in self.all_layers:
            log_warning(f"Layer {layer_name} not found in all_layers")
            return False

        layer_info = next((layer for layer in self.project_settings['geomLayers'] 
                         if layer.get('name') == layer_name), None)
        if not layer_info:
            log_warning(f"Layer info not found for {layer_name}")
            return False

        # Get output directory and ensure it exists
        output_dir = self.project_settings.get('shapefileOutputDir')
        if not output_dir:
            log_warning(f"No shapefileOutputDir specified in project settings")
            return False

        # Resolve the output directory with folder prefix
        output_dir = resolve_path(output_dir, self.folder_prefix)

        # If outputShapeFile is specified in layer config, use that path
        if layer_info.get('outputShapeFile'):
            output_file = resolve_path(layer_info['outputShapeFile'], self.folder_prefix)
        else:
            # Otherwise construct path in the output directory
            output_file = os.path.join(output_dir, f"{layer_name}.shp")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        log_debug(f"Writing shapefile for layer {layer_name} to {output_file}")
        
        # Use the utility function to write the shapefile
        return write_shapefile(
            gdf=self.all_layers[layer_name],
            output_path=output_file,
            delete_existing=True
        )

    def delete_residual_shapefiles(self):
        """Delete any residual shapefiles using the utility functions."""
        output_dir = self.project_settings.get('shapefileOutputDir')
        if not output_dir:
            return

        for layer in self.project_settings.get('geomLayers', []):
            layer_name = layer.get('name')
            if not layer_name:
                continue

            if not layer.get('outputShapeFile'):
                continue

            if layer_name not in self.all_layers:
                log_debug(f"Deleting residual files for layer {layer_name}")
                _delete_existing_shapefile(output_dir, layer_name)

    def _get_geometry_error(self, geom):
        """Get error message for invalid geometry."""
        if not geom.is_valid:
            return str(geom.buffer(0).is_valid)
        return None 