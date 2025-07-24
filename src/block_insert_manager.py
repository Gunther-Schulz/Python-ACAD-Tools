import random
import math
from shapely.geometry import Point
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_block_reference, remove_entities_by_layer, attach_custom_data, find_entity_by_xdata_name, XDATA_APP_ID
from src.sync_manager_base import SyncManagerBase
from src.sync_hash_utils import calculate_entity_content_hash, clean_entity_config_for_yaml_output


class BlockInsertManager(SyncManagerBase):
    """Manager for block insert synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_loader, all_layers, script_identifier):
        # Initialize base class (use 'block' as entity_type)
        super().__init__(project_loader.project_settings, script_identifier, 'block', project_loader)

        # Block insert specific dependencies
        self.all_layers = all_layers

    def process_block_inserts(self, msp):
        """Process block inserts using the sync-based BlockInsertManager."""
        block_configs = self.project_settings.get('blockInserts', [])
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
        """Clean target layers for block configs that will be processed."""
        layers_to_clean = set()
        for config in configs_to_process:
            sync_direction = self._get_sync_direction(config)
            if sync_direction == 'push':
                # Use unified layer resolution
                layer_name = self._resolve_entity_layer(config)
                layers_to_clean.add(layer_name)

        # Remove existing block references from layers that will be updated
        for layer_name in layers_to_clean:
            # Blocks can be in both model space and paper space
            spaces = [doc.modelspace(), doc.paperspace()]
            for space in spaces:
                log_debug(f"Cleaning block entities from layer: {layer_name} in {space}")
                remove_entities_by_layer(space, layer_name, self.script_identifier)

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
                    log_warning(f"Unsupported insert type '{insert_type}' for config '{name}'. Only 'block' is supported.")

            except Exception as e:
                log_error(f"Error processing {insert_type} insert '{config.get('name')}': {str(e)}")
                continue

        log_debug(f"Finished processing all {insert_type} insert configurations")

    def insert_blocks(self, space, config):
        points_and_rotations = self.get_insertion_points(config.get('position', {}))
        name = config.get('name')

        # Determine layer for block insert
        layer_name = self._resolve_entity_layer(config)

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
    # SyncManagerBase Abstract Method Implementations
    # ============================================================================

    def _get_entity_configs(self):
        """Get block insert configurations from project settings."""
        return self.project_settings.get('blockInserts', []) or []

    def _sync_push(self, doc, space, config):
        """Create block insert in AutoCAD from YAML configuration."""
        name = config.get('name', 'unnamed')

        try:
            # Use existing insert_blocks method but for single config
            # Get the correct space for this insert
            target_space = doc.paperspace() if config.get('paperspace', False) else doc.modelspace()

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

            # Determine layer for block insert
            layer_name = self._resolve_entity_layer(config)

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
                log_warning(f"Failed to create block insert '{name}'")
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

            # Search in both model space and paper space
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

    def _calculate_entity_hash(self, config):
        """Calculate content hash for block insert configuration."""
        try:
            return calculate_entity_content_hash(config, 'block')
        except Exception as e:
            log_warning(f"Error calculating hash for block insert '{config.get('name', 'unnamed')}': {str(e)}")
            return "error_hash"

    def _extract_dxf_entity_properties_for_hash(self, dxf_entity):
        """Extract properties from DXF block insert entity for hash calculation."""
        try:
            properties = {}

            # Extract block name
            if hasattr(dxf_entity.dxf, 'name'):
                properties['blockName'] = dxf_entity.dxf.name

            # Extract scale (use xscale as primary, assuming uniform scaling)
            if hasattr(dxf_entity.dxf, 'xscale'):
                properties['scale'] = float(dxf_entity.dxf.xscale)
            else:
                properties['scale'] = 1.0

            # Extract rotation
            if hasattr(dxf_entity.dxf, 'rotation'):
                properties['rotation'] = float(dxf_entity.dxf.rotation)
            else:
                properties['rotation'] = 0.0

            # Extract position (insertion point)
            if hasattr(dxf_entity.dxf, 'insert'):
                insert_point = dxf_entity.dxf.insert
                properties['position'] = {
                    'type': 'absolute',
                    'x': float(insert_point[0]),
                    'y': float(insert_point[1])
                }
            else:
                properties['position'] = {'type': 'absolute', 'x': 0.0, 'y': 0.0}

            # Determine if in paperspace
            properties['paperspace'] = hasattr(dxf_entity, 'doc') and dxf_entity.doc and \
                                     any(dxf_entity in layout for layout in dxf_entity.doc.layouts if layout.name != 'Model')

            # Add entity name from XDATA if available (use centralized method)
            properties['name'] = self._get_entity_name_from_xdata(dxf_entity)

            log_debug(f"Extracted DXF properties for block insert: {properties}")
            return properties

        except Exception as e:
            log_warning(f"Error extracting DXF properties for block insert: {str(e)}")
            return {}

    def _write_entity_yaml(self):
        """Write updated block insert configuration back to YAML file."""
        if not self.project_loader:
            log_warning("Cannot write block insert YAML - no project_loader available")
            return False

        try:
            # Clean and prepare block insert configurations for YAML output
            cleaned_block_inserts = []
            for block_config in self.project_settings.get('blockInserts', []):
                # Clean the configuration for YAML output (handles sync metadata properly)
                cleaned_config = clean_entity_config_for_yaml_output(block_config)
                cleaned_block_inserts.append(cleaned_config)

            # Prepare block insert data structure
            block_data = {
                'blockInserts': cleaned_block_inserts
            }

            # Add global block insert settings
            if 'block_discovery' in self.project_settings:
                block_data['discovery'] = self.project_settings['block_discovery']
            if 'block_deletion_policy' in self.project_settings:
                block_data['deletion_policy'] = self.project_settings['block_deletion_policy']
            if 'block_default_layer' in self.project_settings:
                block_data['default_layer'] = self.project_settings['block_default_layer']
            if 'block_sync' in self.project_settings:
                block_data['sync'] = self.project_settings['block_sync']

            # Write back to block_inserts.yaml
            success = self.project_loader.write_yaml_file('block_inserts.yaml', block_data)
            if success:
                log_info("Successfully updated block_inserts.yaml with sync changes")
            else:
                log_error("Failed to write block insert configuration back to YAML")
            return success

        except Exception as e:
            log_error(f"Error writing block insert YAML: {str(e)}")
            return False



    def _attach_entity_metadata(self, entity, config):
        """Attach metadata to block insert entity for sync tracking."""
        try:
            entity_name = config.get('name', 'unnamed')
            log_info(f"🔧 DEBUG: Attaching XDATA to block '{entity_name}'")
            log_info(f"🔧 DEBUG: Block entity type: {entity.dxftype()}")
            log_info(f"🔧 DEBUG: Block layer: {getattr(entity.dxf, 'layer', 'unknown')}")

            # Calculate content hash for the entity
            content_hash = self._calculate_entity_hash(config)

            # Attach custom data with content hash
            attach_custom_data(
                entity,
                self.script_identifier,
                entity_name=entity_name,
                entity_type='block',
                content_hash=content_hash
            )

            # Verify XDATA was attached
            if hasattr(entity, 'get_xdata'):
                xdata = entity.get_xdata(XDATA_APP_ID)
                if xdata:
                    log_info(f"🔧 DEBUG: XDATA successfully attached: {xdata}")
                else:
                    log_warning(f"🔧 DEBUG: XDATA attachment failed - no XDATA found!")
            else:
                log_warning(f"🔧 DEBUG: Entity doesn't support XDATA!")

            log_debug(f"Attached metadata to block insert '{entity_name}'")

        except Exception as e:
            import traceback
            log_warning(f"Failed to attach metadata to block insert: {repr(e)}")
            log_warning(f"Full traceback: {traceback.format_exc()}")



    def _discover_unknown_entities(self, doc, space):
        """Discover unknown block inserts in the DXF file."""
        # Use centralized discovery logic from SyncManagerBase
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
                current_configs = self.project_settings.get('blockInserts', [])
                remaining_configs = [
                    config for config in current_configs
                    if config not in deleted_configs
                ]
                self.project_settings['blockInserts'] = remaining_configs

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
            if 'updateDxf' not in properties:
                properties['updateDxf'] = False  # Don't auto-update discovered blocks

            log_debug(f"Extracted properties for block insert '{properties.get('name', 'unnamed')}'")
            return properties

        except Exception as e:
            log_warning(f"Error extracting block insert properties: {str(e)}")
            # Return minimal config on error
            return {
                'name': base_config.get('name', 'unnamed'),
                'blockName': 'Unknown',
                'position': {'type': 'absolute', 'x': 0.0, 'y': 0.0},
                'updateDxf': False
            }

    # Abstract method implementations for centralized discovery
    # ========================================================

    def _get_entity_types(self):
        """Block entities: INSERT only."""
        return ['INSERT']

    def _get_discovery_spaces(self, doc):
        """Block entities can be in both model space and paper space."""
        return [doc.modelspace(), doc.paperspace()]

    def _generate_entity_name(self, entity, counter):
        """Generate name based on block name and counter."""
        # Use the block definition name if available
        block_name = getattr(entity.dxf, 'name', 'Unknown')
        return f"Block_{block_name}_{counter:03d}"

    def _should_skip_entity(self, entity):
        """No special skip logic for block entities."""
        return False

    def _get_config_key(self):
        """Override to use 'blockInserts' instead of 'blocks'."""
        return 'blockInserts'
