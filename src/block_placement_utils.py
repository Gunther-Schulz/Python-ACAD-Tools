import random
import math
from shapely.geometry import Point
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_block_reference, remove_entities_by_layer, attach_custom_data


class BlockPlacementUtils:
    """Shared utilities for block placement logic used by both sync and generated systems."""

    @staticmethod
    def _calculate_proximity_based_offset(point, dx, dy, length, offset_config, all_layers):
        """
        Calculate lineOffset based on proximity to a reference layer.

        Args:
            point: Shapely Point where the block will be placed
            dx, dy: Line direction vector components
            length: Length of the direction vector
            offset_config: Dictionary containing proximity configuration
            all_layers: Dictionary of all processed layers

        Returns:
            float: Positive (left side) or negative (right side) offset distance, or None if failed
        """
        reference_layer = offset_config.get('referenceLayer')
        distance = abs(offset_config.get('distance', 1.0))

        if not reference_layer:
            log_warning("Proximity mode enabled but no referenceLayer specified - skipping block placement")
            return None

        if reference_layer not in all_layers:
            log_warning(f"Reference layer '{reference_layer}' not found in all_layers - skipping block placement")
            return None

        ref_layer_data = all_layers[reference_layer]
        if not hasattr(ref_layer_data, 'geometry'):
            log_warning(f"Reference layer '{reference_layer}' has no geometry attribute - skipping block placement")
            return None

        try:
            # Calculate perpendicular unit vector (normalized)
            nx, ny = -dy/length, dx/length
            point_coords = point.coords[0]

            # Calculate candidate points on both sides
            left_point = Point(point_coords[0] + nx*distance, point_coords[1] + ny*distance)
            right_point = Point(point_coords[0] - nx*distance, point_coords[1] - ny*distance)

            # Create union of all reference geometries for distance calculation
            ref_geometries = [geom for geom in ref_layer_data.geometry if geom and not geom.is_empty]
            if not ref_geometries:
                log_warning(f"Reference layer '{reference_layer}' contains no valid geometries - skipping block placement")
                return None

            # Use unary_union for efficient distance calculations
            from shapely.ops import unary_union
            ref_geom_union = unary_union(ref_geometries)

            # Calculate distances to reference geometries
            left_dist = left_point.distance(ref_geom_union)
            right_dist = right_point.distance(ref_geom_union)

            # Return positive offset for left side (closer), negative for right side
            if left_dist < right_dist:
                log_debug(f"Proximity placement: choosing left side (dist: {left_dist:.2f} < {right_dist:.2f})")
                return distance
            else:
                log_debug(f"Proximity placement: choosing right side (dist: {right_dist:.2f} < {left_dist:.2f})")
                return -distance

        except Exception as e:
            log_warning(f"Error in proximity-based offset calculation: {str(e)} - skipping block placement")
            return None

    @staticmethod
    def get_insertion_points(position_config, all_layers):
        """
        Get insertion points based on position configuration.
        Extracted from BlockInsertManager for shared use.

        Args:
            position_config: Position configuration from YAML
            all_layers: Dictionary of all processed layers

        Returns:
            List of tuples: [(x, y, rotation), ...]
        """
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
        if source_layer not in all_layers:
            log_warning(f"Source layer '{source_layer}' not found in all_layers")
            return points

        layer_data = all_layers[source_layer]
        if not hasattr(layer_data, 'geometry'):
            log_warning(f"Layer {source_layer} has no geometry attribute")
            return points

        # Process each geometry based on type and method
        for geometry in layer_data.geometry:
            insert_point, rotation = BlockPlacementUtils.get_insert_point(geometry, position_config, all_layers)
            # Skip placements that failed proximity calculation (indicated by (0,0) position and None rotation)
            if insert_point == (0, 0) and rotation is None:
                continue
            points.append((insert_point[0] + offset_x, insert_point[1] + offset_y, rotation))

        return points

    @staticmethod
    def get_insert_point(geometry, position_config, all_layers=None):
        """
        Get insertion point for a specific geometry.
        Extracted from BlockInsertManager for shared use.

        Args:
            geometry: Shapely geometry object
            position_config: Position configuration from YAML
            all_layers: Dictionary of all processed layers (required for proximity-based lineOffset)

        Returns:
            Tuple: ((x, y), rotation)
        """
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
                        if line_offset != 0 or (isinstance(line_offset, dict) and line_offset.get('proximityMode')):
                            # Calculate perpendicular vector
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                # Check if lineOffset is proximity-based
                                if isinstance(line_offset, dict) and line_offset.get('proximityMode'):
                                    if all_layers is None:
                                        log_warning("Proximity mode enabled but all_layers not provided - skipping block placement")
                                        return ((0, 0), None)  # Skip this placement
                                    else:
                                        effective_offset = BlockPlacementUtils._calculate_proximity_based_offset(
                                            point, dx, dy, length, line_offset, all_layers
                                        )
                                        if effective_offset is None:
                                            return ((0, 0), None)  # Skip this placement
                                else:
                                    # Traditional numeric lineOffset
                                    effective_offset = line_offset

                                # Normalize and rotate 90 degrees
                                nx, ny = -dy/length, dx/length
                                point_coords = point.coords[0]
                                return ((point_coords[0] + nx*effective_offset, point_coords[1] + ny*effective_offset), rotation)

                        return (tuple(point.coords[0][:2]), rotation)

                    elif position_method in ['start', 'end']:
                        base_point = coords[0] if position_method == 'start' else coords[-1]
                        if line_offset != 0 or (isinstance(line_offset, dict) and line_offset.get('proximityMode')):
                            # Calculate direction vector
                            dx = coords[1][0] - coords[0][0] if position_method == 'start' else coords[-1][0] - coords[-2][0]
                            dy = coords[1][1] - coords[0][1] if position_method == 'start' else coords[-1][1] - coords[-2][1]
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                # Check if lineOffset is proximity-based
                                if isinstance(line_offset, dict) and line_offset.get('proximityMode'):
                                    if all_layers is None:
                                        log_warning("Proximity mode enabled but all_layers not provided - skipping block placement")
                                        return ((0, 0), None)  # Skip this placement
                                    else:
                                        base_point_geom = Point(base_point[0], base_point[1])
                                        effective_offset = BlockPlacementUtils._calculate_proximity_based_offset(
                                            base_point_geom, dx, dy, length, line_offset, all_layers
                                        )
                                        if effective_offset is None:
                                            return ((0, 0), None)  # Skip this placement
                                else:
                                    # Traditional numeric lineOffset
                                    effective_offset = line_offset

                                # Normalize and rotate 90 degrees
                                nx, ny = -dy/length, dx/length
                                return ((base_point[0] + nx*effective_offset, base_point[1] + ny*effective_offset), rotation)
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
            return (tuple(geometry.centroid.coords[0][:2]), rotation)

        except Exception as e:
            log_error(f"Error getting insert point: {str(e)}")
            return ((0, 0), rotation)

    @staticmethod
    def place_blocks_bulk(space, config, all_layers, script_identifier):
        """
        Place multiple blocks from a config without sync tracking.
        For use by generated block placement system.

        Args:
            space: DXF space (modelspace or paperspace)
            config: Block placement configuration
            all_layers: Dictionary of all processed layers
            script_identifier: Script identifier for metadata

        Returns:
            List of created block references
        """
        points_and_rotations = BlockPlacementUtils.get_insertion_points(config.get('position', {}), all_layers)
        name = config.get('name')

        if not points_and_rotations:
            log_warning(f"No insertion points found for block placement '{name}'")
            return []

        # Ensure layer exists
        layer_name = config.get('layer', name)
        if layer_name not in space.doc.layers:
            space.doc.layers.new(layer_name)

        created_blocks = []

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
                layer_name,
                scale=config.get('scale', 1.0),
                rotation=final_rotation
            )
            if block_ref:
                attach_custom_data(block_ref, script_identifier)
                created_blocks.append(block_ref)

        log_debug(f"Placed {len(created_blocks)} blocks for '{name}'")
        return created_blocks

    @staticmethod
    def place_block_single(space, config, all_layers, script_identifier):
        """
        Place a single block from a config for sync tracking.
        For use by interactive block insert system.

        Args:
            space: DXF space (modelspace or paperspace)
            config: Block insert configuration
            all_layers: Dictionary of all processed layers
            script_identifier: Script identifier for metadata

        Returns:
            Single block reference or None
        """
        name = config.get('name')
        block_name = config.get('blockName')
        position_config = config.get('position', {})
        source_layer = position_config.get('sourceLayer')
        
        log_debug(f"🔍 BLOCK INSERT DEBUG: Attempting to place block insert '{name}'")
        log_debug(f"  - Block name: {block_name}")
        log_debug(f"  - Source layer: {source_layer}")
        log_debug(f"  - Available layers in all_layers: {list(all_layers.keys())[:20]}")
        log_debug(f"  - Source layer exists: {source_layer in all_layers if source_layer else 'N/A'}")
        
        if source_layer and source_layer in all_layers:
            layer_data = all_layers[source_layer]
            log_debug(f"  - Source layer type: {type(layer_data)}")
            if hasattr(layer_data, 'geometry'):
                log_debug(f"  - Source layer geometry count: {len(layer_data.geometry)}")
        
        points_and_rotations = BlockPlacementUtils.get_insertion_points(position_config, all_layers)
        log_debug(f"  - Insertion points found: {len(points_and_rotations) if points_and_rotations else 0}")

        if not points_and_rotations:
            log_warning(f"❌ No insertion points found for block insert '{name}'")
            return None

        # For sync, we only create one block reference (first point)
        point_data = points_and_rotations[0]

        # Handle both 2-tuple (point, rotation) and 3-tuple (x, y, rotation) formats
        if len(point_data) == 3:
            x, y, rotation = point_data
            point = (x, y)
        else:
            point, rotation = point_data
            if not isinstance(point, tuple):
                point = (point[0], point[1]) if hasattr(point, '__getitem__') else (0, 0)

        # Use the calculated rotation if available, otherwise use config rotation
        final_rotation = rotation if rotation is not None else config.get('rotation', 0)

        # Ensure layer exists (this should be handled by caller, but safety check)
        layer_name = config.get('layer', name)
        if layer_name not in space.doc.layers:
            space.doc.layers.new(layer_name)

        # Check if block exists before trying to insert
        log_debug(f"  - Checking if block '{block_name}' exists in document...")
        if block_name not in space.doc.blocks:
            available_blocks = [b.name for b in space.doc.blocks if not b.name.startswith('*')][:20]
            log_warning(f"❌ Block '{block_name}' not found in document!")
            log_warning(f"   Available blocks: {available_blocks}")
            return None

        block_ref = add_block_reference(
            space,
            config['blockName'],
            point,
            layer_name,
            scale=config.get('scale', 1.0),
            rotation=final_rotation
        )

        if block_ref:
            attach_custom_data(block_ref, script_identifier)
            log_debug(f"Created single block insert '{name}' for sync tracking")
            return block_ref
        else:
            log_warning(f"Failed to create block insert '{name}' - add_block_reference returned None")
            return None
