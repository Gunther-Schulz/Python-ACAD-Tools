import random
from shapely.geometry import Point
from src.utils import log_info, log_warning, log_error
from src.dxf_utils import add_block_reference, remove_entities_by_layer, attach_custom_data


class BlockInsertManager:
    def __init__(self, project_loader, all_layers, script_identifier):
        self.project_loader = project_loader
        self.all_layers = all_layers
        self.script_identifier = script_identifier
        self.project_settings = project_loader.project_settings

    def process_block_inserts(self, msp):
        self.process_inserts(msp, 'block')

    def process_inserts(self, msp, insert_type='block'):
        configs = self.project_settings.get(f'{insert_type}Inserts', [])
        log_info(f"Processing {len(configs)} {insert_type} insert configurations")
        
        doc = msp.doc
        
        if insert_type == 'block':
            # First pass: collect all names that need cleaning for blocks
            layers_to_clean = set()
            for config in configs:
                if config.get('updateDxf', False):
                    name = config.get('name')
                    if name:
                        layers_to_clean.add(name)
            
            # Clean all block layers at once
            for layer_name in layers_to_clean:
                space = doc.paperspace() if any(c.get('paperspace', False) for c in configs) else doc.modelspace()
                remove_entities_by_layer(space, layer_name, self.script_identifier)
                log_info(f"Cleaned existing entities from layer: {layer_name}")
        else:
            # For text inserts, clean by target layer or name
            layers_to_clean = set()
            for config in configs:
                if config.get('updateDxf', False):
                    # Use targetLayer if specified, otherwise use name
                    layer_name = config.get('targetLayer', config.get('name'))
                    if layer_name:
                        layers_to_clean.add(layer_name)
            
            # Clean all text layers at once
            for layer_name in layers_to_clean:
                space = doc.paperspace() if any(c.get('paperspace', False) for c in configs) else doc.modelspace()
                remove_entities_by_layer(space, layer_name, self.script_identifier)
                log_info(f"Cleaned existing entities from layer: {layer_name}")
        
        # Second pass: process inserts
        for config in configs:
            try:
                name = config.get('name')
                update_dxf = config.get('updateDxf', False)
                
                if not update_dxf:
                    log_info(f"Skipping {insert_type} insert '{name}' as updateDxf flag is not set")
                    continue

                if not name:
                    log_warning(f"Missing name for {insert_type} insert: {config}")
                    continue

                # Get the correct space for insertion
                space = doc.paperspace() if config.get('paperspace', False) else doc.modelspace()

                # Insert entities using common insertion method with correct space
                if insert_type == 'block':
                    self.insert_blocks(space, config)
                else:  # text
                    self.insert_text(space, config)

            except Exception as e:
                log_error(f"Error processing {insert_type} insert: {str(e)}")
                continue

        log_info(f"Finished processing all {insert_type} insert configurations")

    def insert_blocks(self, space, config):
        points = self.get_insertion_points(config.get('position', {}))
        name = config.get('name')  # Use name as the layer
        
        for point in points:
            block_ref = add_block_reference(
                space,
                config['blockName'],
                point,
                name,  # Use name as the layer
                scale=config.get('scale', 1.0),
                rotation=config.get('rotation', 0)
            )
            if block_ref:
                attach_custom_data(block_ref, self.script_identifier)


    def get_insertion_points(self, position_config):
        """Common method to get insertion points for both blocks and text."""
        points = []
        position_type = position_config.get('type', 'polygon')
        offset_x = position_config.get('offset', {}).get('x', 0)
        offset_y = position_config.get('offset', {}).get('y', 0)
        source_layer = position_config.get('sourceLayer')

        # Handle absolute positioning
        if position_type == 'absolute':
            x = position_config.get('x', 0)
            y = position_config.get('y', 0)
            points.append((x + offset_x, y + offset_y))
            return points

        # For non-absolute positioning, we need a source layer
        if not source_layer:
            log_warning("Source layer required for non-absolute positioning")
            return points

        # Handle geometry-based positioning
        if source_layer not in self.all_layers:
            log_warning(f"Source layer '{source_layer}' not found in all_layers")
            return points

        layer_data = self.all_layers[source_layer]
        if not hasattr(layer_data, 'geometry'):
            log_warning(f"Layer {source_layer} has no geometry attribute")
            return points

        # Process each geometry based on type and method
        for geometry in layer_data.geometry:
            insert_point = self.get_insert_point(geometry, position_config)
            points.append((insert_point[0] + offset_x, insert_point[1] + offset_y))

        return points

    def get_insert_point(self, geometry, position_config):
        position_type = position_config.get('type', 'polygon')
        position_method = position_config.get('method', 'centroid')

        if position_type == 'absolute':
            log_warning("Absolute positioning doesn't use geometry-based insert points")
            return (0, 0)
        
        elif position_type == 'polygon':
            if position_method == 'centroid':
                return geometry.centroid.coords[0]
            elif position_method == 'center':
                return geometry.envelope.centroid.coords[0]
            elif position_method == 'random':
                minx, miny, maxx, maxy = geometry.bounds
                while True:
                    point = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
                    if geometry.contains(point):
                        return point.coords[0]
                    
        elif position_type == 'line':
            if position_method == 'start':
                return geometry.coords[0]
            elif position_method == 'end':
                return geometry.coords[-1]
            elif position_method == 'middle':
                return geometry.interpolate(0.5, normalized=True).coords[0]
            elif position_method == 'random':
                distance = random.random()
                return geometry.interpolate(distance, normalized=True).coords[0]
        
        elif position_type == 'points':
            if hasattr(geometry, 'coords'):
                return geometry.coords[0]
        
        # Default fallback
        log_warning(f"Invalid position type '{position_type}' or method '{position_method}'. Using polygon centroid.")
        return geometry.centroid.coords[0]