from src.utils import log_debug, log_warning
from src.dxf_utils import create_hatch, attach_custom_data

class HatchProcessor:
    def __init__(self, script_identifier, project_loader, style_manager, layer_manager):
        self.project_loader = project_loader
        self.style_manager = style_manager
        self.layer_manager = layer_manager
        self.script_identifier = script_identifier
        self.all_layers = {}

    def process_hatch(self, doc, msp, layer_name, layer_info):
        """Process hatch for a layer"""
        log_debug(f"Processing hatch for layer: {layer_name}")
        
        hatch_config = self.style_manager.get_hatch_config(layer_info)
        log_debug(f"Hatch config: {hatch_config}")

        apply_hatch = layer_info.get('applyHatch', False)
        if not apply_hatch:
            log_debug(f"Hatch processing skipped for layer: {layer_name}")
            return

        boundary_layers = hatch_config.get('layers', [layer_name])
        boundary_geometry = self._get_boundary_geometry(boundary_layers)
        
        if boundary_geometry is None or boundary_geometry.is_empty:
            log_warning(f"No valid boundary geometry found for hatch in layer: {layer_name}")
            return
        
        individual_hatches = hatch_config.get('individual_hatches', True)

        if individual_hatches:
            geometries = [boundary_geometry] if not hasattr(boundary_geometry, 'geoms') else list(boundary_geometry.geoms)
        else:
            geometries = [boundary_geometry]
        
        for geometry in geometries:
            hatch_paths = self._get_hatch_paths(geometry)
            if hatch_paths:
                hatch = create_hatch(msp, hatch_paths, hatch_config, self.project_loader)
                hatch.dxf.layer = layer_name
                attach_custom_data(hatch, self.script_identifier)

        log_debug(f"Added hatch{'es' if individual_hatches else ''} to layer: {layer_name}")

    def _get_boundary_geometry(self, boundary_layers):
        """Get combined geometry from boundary layers"""
        combined_geometry = None
        for layer_name in boundary_layers:
            if layer_name in self.all_layers:
                layer_geometry = self.all_layers[layer_name]
                if hasattr(layer_geometry, 'geometry'):
                    layer_geometry = layer_geometry.geometry.unary_union
                if combined_geometry is None:
                    combined_geometry = layer_geometry
                else:
                    combined_geometry = combined_geometry.union(layer_geometry)
        return combined_geometry

    def _get_hatch_paths(self, geometry):
        """Get hatch paths from geometry"""
        if hasattr(geometry, 'exterior'):
            paths = [list(geometry.exterior.coords)]
            for interior in geometry.interiors:
                paths.append(list(interior.coords))
            return paths
        elif hasattr(geometry, 'geoms'):
            paths = []
            for geom in geometry.geoms:
                paths.extend(self._get_hatch_paths(geom))
            return paths
        return []

    def set_all_layers(self, all_layers):
        """Set the all_layers dictionary"""
        self.all_layers = all_layers
