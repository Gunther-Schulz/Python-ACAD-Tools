"""Module for processing path arrays in DXF files."""

from src.utils import log_debug, log_warning
from .utils import remove_entities_by_layer
from src.path_array import create_path_array

class PathArrayProcessor:
    def __init__(self, script_identifier, project_loader):
        self.project_loader = project_loader
        self.script_identifier = script_identifier
        self.all_layers = {}

    def create_path_arrays(self, msp):
        """Process and create path arrays from project settings"""
        path_arrays = self.project_loader.project_settings.get('pathArrays', [])
        log_debug(f"Processing {len(path_arrays)} path array configurations")
        
        for config in path_arrays:
            name = config.get('name')
            source_layer_name = config.get('sourceLayer')
            updateDxf = config.get('updateDxf', False)  # Default is False
            
            if not name or not source_layer_name:
                log_warning(f"Invalid path array configuration: {config}")
                continue
            
            if not updateDxf:
                log_debug(f"Skipping path array '{name}' as updateDxf flag is not set")
                continue
            
            if source_layer_name not in self.all_layers:
                log_warning(f"Source layer '{source_layer_name}' does not exist in all_layers. Skipping path array creation for this configuration.")
                continue
            
            remove_entities_by_layer(msp, name, self.script_identifier)
            
            block_name = config['block']
            spacing = config['spacing']
            scale = config.get('scale', 1.0)
            rotation = config.get('rotation', 0.0)
            buffer_distance = config.get('bufferDistance', 0.0)
            path_offset = config.get('pathOffset', 0.0)
            show_debug_visual = config.get('showDebugVisual', False)
            adjust_for_vertices = config.get('adjustForVertices', False)
            all_edges = config.get('all_edges', False)
            
            log_debug(f"Creating path array: {name}")
            log_debug(f"Source layer: {source_layer_name}")
            log_debug(f"Block: {block_name}, Spacing: {spacing}, Scale: {scale}")
            log_debug(f"Path offset: {path_offset}")
            log_debug(f"All edges: {all_edges}")
            
            create_path_array(msp, source_layer_name, name, block_name, 
                             spacing, buffer_distance, scale, rotation, 
                             show_debug_visual, self.all_layers, 
                             adjust_for_vertices, path_offset, all_edges)
        
        log_debug("Finished processing all path array configurations")

    def set_all_layers(self, all_layers):
        """Set the all_layers dictionary"""
        self.all_layers = all_layers
