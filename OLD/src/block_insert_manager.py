import random
import math
from shapely.geometry import Point
from src.utils import log_info, log_warning, log_error, log_debug
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
        log_debug(f"Processing {len(configs)} {insert_type} insert configurations")
        
        # Group configs by target layer
        layers_to_clean = {
            c.get('name') 
            for c in configs 
            if c.get('updateDxf', False) and c.get('name')
        }
        
        # Clean layers (remove_entities_by_layer handles both spaces)
        for layer_name in layers_to_clean:
            remove_entities_by_layer(msp, layer_name, self.script_identifier)
            log_debug(f"Cleaned existing entities from layer: {layer_name}")

        # Process all inserts
        for config in configs:
            try:
                if not config.get('updateDxf', False):
                    continue
                
                name = config.get('name')
                if not name:
                    continue
                
                # Get the correct space for this insert
                space = msp.doc.paperspace() if config.get('paperspace', False) else msp.doc.modelspace()
                
                if insert_type == 'block':
                    self.insert_blocks(space, config)
                else:
                    self.insert_text(space, config)
                
            except Exception as e:
                log_error(f"Error processing {insert_type} insert '{config.get('name')}': {str(e)}")
                continue

        log_debug(f"Finished processing all {insert_type} insert configurations")

    def insert_blocks(self, space, config):
        points_and_rotations = self.get_insertion_points(config.get('position', {}))
        name = config.get('name')
        
        for point_data in points_and_rotations:
            # Handle both 2-tuple (point, rotation) and 3-tuple (x, y, rotation) formats
            if len(point_data) == 3:
                x, y, rotation = point_data
                point = (x, y)
            else:
                point, rotation = point_data
                if not isinstance(point, tuple):  # Ensure point is always a tuple
                    point = (point[0], point[1]) if hasattr(point, '__getitem__') else (0, 0)
            
            # Use the calculated rotation if available, otherwise use config rotation
            final_rotation = rotation if rotation is not None else config.get('rotation', 0)
            
            block_ref = add_block_reference(
                space,
                config['blockName'],
                point,
                name,
                scale=config.get('scale', 1.0),
                rotation=final_rotation
            )
            if block_ref:
                attach_custom_data(block_ref, self.script_identifier)

    def get_insertion_points(self, position_config):
        """Common method to get insertion points for both blocks and text."""
        points = []
        position_type = position_config.get('type', 'polygon')
        offset_x = position_config.get('offset', {}).get('x', 0)
        offset_y = position_config.get('offset', {}).get('y', 0)

        # Handle absolute positioning
        if position_type == 'absolute':
            x = position_config.get('x', 0)
            y = position_config.get('y', 0)
            # Return a 3-tuple format (x, y, rotation) for consistency
            return [(x + offset_x, y + offset_y, None)]

        # For non-absolute positioning, we need a source layer
        source_layer = position_config.get('sourceLayer')
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
            insert_point, rotation = self.get_insert_point(geometry, position_config)
            points.append((insert_point[0] + offset_x, insert_point[1] + offset_y, rotation))

        return points

    def get_insert_point(self, geometry, position_config):
        position_type = position_config.get('type', 'absolute')
        position_method = position_config.get('method', 'centroid')
        # Get the perpendicular offset distance
        line_offset = position_config.get('lineOffset', 0)

        # Default rotation is None (will use config rotation instead)
        rotation = None

        try:
            if position_type == 'absolute':
                log_warning("Absolute positioning doesn't use geometry-based insert points")
                return ((0, 0), rotation)
            
            elif position_type == 'line':
                coords = list(geometry.coords)
                if len(coords) >= 2:
                    if position_method == 'middle':
                        point = geometry.interpolate(0.5, normalized=True)
                        # Calculate rotation angle from line direction
                        start, end = coords[0], coords[-1]
                        dx = end[0] - start[0]
                        dy = end[1] - start[1]
                        rotation = math.degrees(math.atan2(dy, dx))
                        
                        # Apply perpendicular offset if specified
                        if line_offset != 0:
                            # Calculate perpendicular vector
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                # Normalize and rotate 90 degrees
                                nx, ny = -dy/length, dx/length
                                point_coords = point.coords[0]
                                return ((point_coords[0] + nx*line_offset, point_coords[1] + ny*line_offset), rotation)
                        
                        return (tuple(point.coords[0][:2]), rotation)
                    
                    elif position_method in ['start', 'end']:
                        base_point = coords[0] if position_method == 'start' else coords[-1]
                        if line_offset != 0:
                            # Calculate direction vector
                            dx = coords[1][0] - coords[0][0] if position_method == 'start' else coords[-1][0] - coords[-2][0]
                            dy = coords[1][1] - coords[0][1] if position_method == 'start' else coords[-1][1] - coords[-2][1]
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                # Normalize and rotate 90 degrees
                                nx, ny = -dy/length, dx/length
                                return ((base_point[0] + nx*line_offset, base_point[1] + ny*line_offset), rotation)
                        return (tuple(base_point[:2]), rotation)
            
            elif position_type == 'points':
                if hasattr(geometry, 'coords'):
                    return (tuple(geometry.coords[0][:2]), rotation)  # Take only x,y coordinates
            
            elif position_type == 'polygon':
                if position_method == 'centroid':
                    return (tuple(geometry.centroid.coords[0][:2]), rotation)  # Take only x,y coordinates
                elif position_method == 'center':
                    return (tuple(geometry.envelope.centroid.coords[0][:2]), rotation)  # Take only x,y coordinates
                elif position_method == 'random':
                    minx, miny, maxx, maxy = geometry.bounds
                    while True:
                        point = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
                        if geometry.contains(point):
                            return (tuple(point.coords[0][:2]), rotation)  # Take only x,y coordinates
            
            # Default fallback
            log_warning(f"Invalid position type '{position_type}' or method '{position_method}'. Using polygon centroid.")
            return (tuple(geometry.centroid.coords[0][:2]), rotation)  # Take only x,y coordinates
            
        except Exception as e:
            log_warning(f"Error in get_insert_point: {str(e)}")
            return ((0, 0), rotation)  # Safe fallback