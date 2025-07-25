import random
import math
from shapely.geometry import Point
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_block_reference, remove_entities_by_layer, attach_custom_data, find_entity_by_xdata_name, XDATA_APP_ID, detect_entity_paperspace
from src.unified_sync_processor import UnifiedSyncProcessor
from src.sync_hash_utils import clean_entity_config_for_yaml_output


class BlockInsertManager(UnifiedSyncProcessor):
    """Manager for block insert synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_loader, all_layers, script_identifier):
        # Initialize base class (use 'block' as entity_type)
        super().__init__(project_loader.project_settings, script_identifier, 'block', project_loader)

        # Block insert specific dependencies
        self.all_layers = all_layers

    def process_block_inserts(self, msp):
        """Process block inserts using the sync-based BlockInsertManager."""
        block_configs = self._get_entity_configs()
        if not block_configs:
            log_debug("No block inserts found in project settings")
            return

        # Clean target layers before processing (only for entities that will be pushed)
        configs_to_process = [c for c in block_configs if self._get_sync_direction(c) == 'push']
        self.clean_target_layers(msp.doc, configs_to_process)

        # Process using sync manager
        processed_blocks = self.process_entities(msp.doc, msp)
        log_debug(f"Processed {len(processed_blocks)} block inserts using sync system")

    def clean_target_layers(self, doc, configs_to_process):
        """Clean target layers for block configs (both spaces). Uses centralized logic."""
        return self._centralize_target_layer_cleaning(doc, configs_to_process)

    def insert_blocks(self, space, config):
        points_and_rotations = self.get_insertion_points(config.get('position', {}))
        name = config.get('name')

                # Determine layer for block insert and ensure it exists (centralized)
        layer_name = self._ensure_entity_layer_exists(space.doc, config)

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

    # ============================================================================
    # UnifiedSyncProcessor Abstract Method Implementations
    # ============================================================================

    def _get_entity_configs(self):
        """Get block insert configurations from project settings."""
        return self.project_settings.get(self._get_config_key(), []) or []

    def _sync_push(self, doc, space, config):
        """Create block insert in AutoCAD from YAML configuration."""
        name = config.get('name', 'unnamed')

        try:
            # Get the correct space for this insert (centralized)
            target_space = self._get_target_space(doc, config)

            # Use existing logic to get insertion points
            points_and_rotations = self.get_insertion_points(config.get('position', {}))

            if not points_and_rotations:
                log_warning(f"No insertion points found for block insert '{name}'")
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

            # Determine layer for block insert and ensure it exists (centralized)
            layer_name = self._ensure_entity_layer_exists(doc, config)

            block_ref = add_block_reference(
                target_space,
                config['blockName'],
                point,
                layer_name,
                scale=config.get('scale', 1.0),
                rotation=final_rotation
            )

            if block_ref:
                # Attach custom metadata for sync tracking
                self._attach_entity_metadata(block_ref, config)
                log_debug(f"Created block insert '{name}' from YAML config")
                return block_ref
            else:
                log_warning(f"Failed to create block insert '{name}' - add_block_reference returned None")
                return None

        except Exception as e:
            log_error(f"Error creating block insert '{name}': {str(e)}")
            return None

    def _sync_pull(self, doc, space, config):
        """Extract block insert properties from DXF to update YAML configuration."""
        name = config.get('name', 'unnamed')

        try:
            # Find the DXF entity
            dxf_entity = self._find_entity_by_name(doc, name)
            if not dxf_entity:
                log_warning(f"Cannot pull block insert '{name}' - not found in AutoCAD")
                return None

            # Extract properties from DXF entity
            dxf_properties = self._extract_dxf_entity_properties_for_hash(dxf_entity)

            # Update YAML config with DXF properties
            updated_config = config.copy()

            # Update core properties from DXF
            if 'blockName' in dxf_properties:
                updated_config['blockName'] = dxf_properties['blockName']
            if 'scale' in dxf_properties:
                updated_config['scale'] = dxf_properties['scale']
            if 'rotation' in dxf_properties:
                updated_config['rotation'] = dxf_properties['rotation']
            if 'position' in dxf_properties:
                updated_config['position'] = dxf_properties['position']
            if 'paperspace' in dxf_properties:
                updated_config['paperspace'] = dxf_properties['paperspace']

            log_debug(f"Updated block insert '{name}' from DXF properties")
            return {'entity': dxf_entity, 'yaml_updated': True, 'updated_config': updated_config}

        except Exception as e:
            log_error(f"Error pulling block insert '{name}': {str(e)}")
            return None

    def _find_entity_by_name(self, doc, entity_name):
        """Find block insert entity in DXF by name using XDATA."""
        try:
            log_info(f"🔍 DEBUG: Searching for block '{entity_name}' with script ID '{self.script_identifier}'")

            # Search modelspace first (where most block inserts like equipment symbols are), then paperspace
            spaces = [doc.modelspace(), doc.paperspace()]

            for space in spaces:
                log_info(f"🔍 DEBUG: Searching in {space}")

                # Try to find the specific entity
                entity = find_entity_by_xdata_name(space, entity_name, ['INSERT'])
                if entity and entity.dxftype() == 'INSERT':
                    log_info(f"🔍 DEBUG: ✅ Found block insert '{entity_name}' in {space}")

                    # Validate entity handle (auto sync integrity check)
                    if self._validate_entity_handle(entity, entity_name):
                        return entity
                    else:
                        log_info(f"🔍 DEBUG: ❌ Block insert '{entity_name}' failed handle validation (copied entity)")
                        return None  # Treat as missing to trigger push

            log_info(f"🔍 DEBUG: ❌ Block insert '{entity_name}' not found in any space")
            return None

        except Exception as e:
            import traceback
            log_warning(f"Error finding block insert '{entity_name}': {repr(e)}")
            log_warning(f"Full traceback: {traceback.format_exc()}")
            return None

    def _find_entity_by_handle_first(self, doc, config):
        """
        Override base class to search both spaces for blocks.

        Block inserts can be in either modelspace or paperspace,
        so we need to search both spaces even for handle-first search.

        Args:
            doc: DXF document
            config: Entity configuration

        Returns:
            DXF entity or None if not found
        """
        if not config:
            log_warning("Config is None in _find_entity_by_handle_first")
            return None

        entity_name = config.get('name', 'unnamed')
        sync_metadata = config.get('_sync', {})
        stored_handle = sync_metadata.get('dxf_handle') if sync_metadata else None

        # STEP 1: Try handle-first search in both spaces (block-specific behavior)
        if stored_handle:
            # Prioritize modelspace first since most block inserts are design elements in modelspace
            spaces = [doc.modelspace(), doc.paperspace()]
            for space in spaces:
                try:
                    entity = space.get_entity_by_handle(stored_handle)
                    if entity:
                        log_debug(f"Found block '{entity_name}' by handle {stored_handle} in {space}")

                        # Update entity name in XDATA if it changed
                        self._update_entity_name_in_xdata(entity, entity_name)

                        return entity
                except Exception as e:
                    log_debug(f"Handle search failed in {space} for '{entity_name}' (handle: {stored_handle}): {str(e)}")
                    continue

        # STEP 2: Fallback to name-based search using existing method
        log_debug(f"Falling back to name search for block '{entity_name}'")
        return self._find_entity_by_name(doc, entity_name)

    # _calculate_entity_hash is now implemented in UnifiedSyncProcessor

    def _extract_dxf_entity_properties_for_hash(self, entity):
        """Extract properties from DXF entity for hash calculation."""
        # Determine paperspace using shared reliable detection
        paperspace = detect_entity_paperspace(entity)
        if paperspace is None:
            paperspace = False  # Fallback for hash consistency

        properties = {
            'position': {
                'x': round(entity.dxf.insert.x, 6),
                'y': round(entity.dxf.insert.y, 6)
            },
            'block_name': entity.dxf.name,
            'layer': entity.dxf.layer,
            'scale': getattr(entity.dxf, 'xscale', 1.0),
            'rotation': round(math.degrees(getattr(entity.dxf, 'rotation', 0.0)), 6),
            'paperspace': paperspace
        }

        return properties

    # Abstract methods required by UnifiedSyncProcessor
    def _get_fallback_default_layer(self):
        """Get fallback default layer name for block entities."""
        fallbacks = {
            'viewport': 'VIEWPORTS',
            'text': 'Plantext',
            'block': 'BLOCKS'
        }
        return fallbacks.get(self.entity_type, 'DEFAULT_LAYER')

    def _resolve_entity_layer(self, config):
        """
        Resolve the layer for a block entity using unified layer logic.

        Args:
            config: Block entity configuration dictionary

        Returns:
            str: Layer name to use for this block entity
        """
        # Check for individual layer override first
        entity_layer = config.get('layer')
        if entity_layer:
            return entity_layer

        # Fall back to global default layer
        return self.default_layer

    def _calculate_entity_hash(self, config):
        """
        Calculate content hash for block entity configuration.
        Centralized implementation that works for all entity types.

        Args:
            config: Block entity configuration dictionary

        Returns:
            str: Content hash for the configuration
        """
        try:
            from src.sync_hash_utils import calculate_entity_content_hash
            return calculate_entity_content_hash(config, self.entity_type)
        except Exception as e:
            log_warning(f"Error calculating hash for {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
            return "error_hash"

    # _write_entity_yaml is now implemented in UnifiedSyncProcessor



    # _attach_entity_metadata is now implemented in UnifiedSyncProcessor



    def _discover_unknown_entities(self, doc, space):
        """Discover unknown block inserts in the DXF file."""
        # Use centralized discovery logic from UnifiedSyncProcessor
        return super()._discover_unknown_entities(doc, space)

    def _handle_entity_deletions(self, doc, space):
        """Handle deletion of block entities that exist in YAML but not in AutoCAD."""
        deleted_configs = []

        try:
            # Only check entities that are in 'pull' mode (AutoCAD is source of truth)
            entity_configs = [
                config for config in self._get_entity_configs()
                if self._get_sync_direction(config) == 'pull'
            ]

            for config in entity_configs:
                entity_name = config.get('name', 'unnamed')
                existing_entity = self._find_entity_by_name(doc, entity_name)

                if not existing_entity:
                    # Entity exists in YAML but not in AutoCAD
                    deletion_policy = self.project_settings.get('block_deletion_policy', 'confirm')

                    if deletion_policy == 'auto':
                        deleted_configs.append(config)
                        log_info(f"Auto-deleted missing block insert '{entity_name}' from YAML")
                    elif deletion_policy == 'confirm':
                        log_warning(f"Block insert '{entity_name}' exists in YAML but not in AutoCAD")
                        response = input(f"Delete '{entity_name}' from configuration? (y/n): ").lower().strip()
                        if response == 'y':
                            deleted_configs.append(config)
                            log_info(f"Deleted missing block insert '{entity_name}' from YAML")
                    # For 'ignore' policy, do nothing

            # Remove deleted configs from project settings
            if deleted_configs:
                current_configs = self._get_entity_configs()
                remaining_configs = [
                    config for config in current_configs
                    if config not in deleted_configs
                ]
                self.project_settings[self._get_config_key()] = remaining_configs

            return deleted_configs

        except Exception as e:
            log_error(f"Error handling block insert deletions: {str(e)}")
            return []

    def _extract_entity_properties(self, entity, base_config):
        """Extract entity properties from AutoCAD block insert entity."""
        try:
            # Start with base config (contains at least 'name')
            properties = base_config.copy()

            # Extract properties from DXF entity using existing method
            dxf_properties = self._extract_dxf_entity_properties_for_hash(entity)

            # Update properties with DXF data
            properties.update(dxf_properties)

            # Set some defaults for discovered entities
            if 'sync' not in properties:
                properties['sync'] = 'skip'  # Don't auto-update discovered blocks

            log_debug(f"Extracted properties for block insert '{properties.get('name', 'unnamed')}'")
            return properties

        except Exception as e:
            log_warning(f"Error extracting block insert properties: {str(e)}")
            # Return minimal config on error
            return {
                'name': base_config.get('name', 'unnamed'),
                'blockName': 'Unknown',
                'position': {'type': 'absolute', 'x': 0.0, 'y': 0.0},
                'sync': 'skip'
            }

    # Abstract method implementations for centralized discovery
    # ========================================================

    def _get_entity_types(self):
        """Block entities: INSERT only."""
        return ['INSERT']

    def _get_discovery_spaces(self, doc):
        """Block entities can be in both spaces - prioritize modelspace for efficiency since most blocks are in modelspace."""
        # Prioritize modelspace first since most block inserts (equipment symbols, etc.) are in modelspace
        return [doc.modelspace(), doc.paperspace()]

    def _generate_entity_name(self, entity, counter):
        """Generate name based on block name and counter."""
        # Use the block definition name if available
        block_name = getattr(entity.dxf, 'name', 'Unknown')
        return f"Block_{block_name}_{counter:03d}"

    def _should_skip_entity(self, entity):
        """No special skip logic for block entities."""
        return False

    def _get_entity_types_for_search(self):
        """Get DXF entity types for block insert search."""
        return ['INSERT']

    def _extract_entity_properties_for_discovery(self, entity):
        """Extract block insert properties for auto-discovery."""
        try:
            # Determine paperspace using shared reliable detection
            paperspace = detect_entity_paperspace(entity)
            if paperspace is None:
                paperspace = False  # Fallback for discovery

            position = {'type': 'absolute', 'x': float(entity.dxf.insert[0]), 'y': float(entity.dxf.insert[1])}
            return {
                'blockName': entity.dxf.name,
                'position': position,
                'scale': float(getattr(entity.dxf, 'xscale', 1.0)),
                'rotation': float(getattr(entity.dxf, 'rotation', 0.0)),
                'layer': entity.dxf.layer,
                'paperspace': paperspace
            }
        except Exception as e:
            log_warning(f"Error extracting block insert properties: {str(e)}")
            return {
                'blockName': 'Unknown',
                'position': {'type': 'absolute', 'x': 0, 'y': 0},
                'scale': 1.0,
                'rotation': 0.0,
                'layer': 'DEFAULT',
                'paperspace': False
            }

    # _get_config_key is now implemented in UnifiedSyncProcessor
