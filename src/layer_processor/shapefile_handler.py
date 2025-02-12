"""Module for handling shapefile operations."""

import os
import shutil
import fiona
import geopandas as gpd
from src.utils import log_warning, log_error
from src.shapefile_utils import write_shapefile

class ShapefileHandler:
    def __init__(self, layer_processor):
        self.layer_processor = layer_processor
        self.project_settings = layer_processor.project_settings
        self.all_layers = layer_processor.all_layers
        self.crs = layer_processor.crs

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
                # Convert Fiona collection to GeoDataFrame immediately
                gdf = gpd.read_file(shapefile)
                if gdf.crs != self.crs:
                    gdf = gdf.to_crs(self.crs)
                self.all_layers[layer_name] = gdf
            except Exception as e:
                log_error(f"Error reading shapefile for layer {layer_name}: {str(e)}")
                raise

    def write_shapefile(self, layer_name):
        """Write a layer to a shapefile."""
        if layer_name not in self.all_layers:
            log_warning(f"Layer {layer_name} not found in all_layers")
            return

        layer_info = next((layer for layer in self.project_settings['geomLayers'] 
                         if layer.get('name') == layer_name), None)
        if not layer_info:
            log_warning(f"Layer info not found for {layer_name}")
            return

        output_file = layer_info.get('outputShapeFile')
        if not output_file:
            return

        write_shapefile(self.all_layers[layer_name], output_file)

    def delete_residual_shapefiles(self):
        """Delete any residual shapefiles."""
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
                self.delete_layer_files(output_dir, layer_name)

    def delete_layer_files(self, directory, layer_name):
        """Delete all files associated with a layer."""
        extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg']
        for ext in extensions:
            file_path = os.path.join(directory, f"{layer_name}{ext}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    log_warning(f"Could not delete file {file_path}: {str(e)}")

    def _get_geometry_error(self, geom):
        """Get error message for invalid geometry."""
        if not geom.is_valid:
            return str(geom.buffer(0).is_valid)
        return None 