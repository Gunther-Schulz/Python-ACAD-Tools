import random
import math
from shapely.geometry import Point
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_block_reference, remove_entities_by_layer, attach_custom_data, find_entity_by_xdata_name, XDATA_APP_ID, detect_entity_paperspace
from src.unified_sync_processor import UnifiedSyncProcessor
from src.sync_hash_utils import clean_entity_config_for_yaml_output
from src.block_placement_utils import BlockPlacementUtils


class BlockInsertManager(UnifiedSyncProcessor):
    """Manager for block insert synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_loader, all_layers, script_identifier):
        # Initialize base class (use 'block' as entity_type)
        super().__init__(project_loader.project_settings, script_identifier, 'block', project_loader)

        # Block insert specific dependencies
        self.all_layers = all_layers

    def process_block_inserts(self, msp):
        """Process block inserts using the sync-based BlockInsertManager."""
        log_info("=" * 80)
        log_info("🔷 STARTING BLOCK INSERT PROCESSING")
        log_info("=" * 80)
        
        block_configs = self._get_entity_configs()
        log_info(f"Found {len(block_configs)} block insert configurations")
        
        if not block_configs:
            log_debug("No block inserts found in project settings")
            return

        # Log each config
        for i, config in enumerate(block_configs, 1):
            log_info(f"  [{i}] {config.get('name')} - blockName: {config.get('blockName')}, sync: {config.get('sync')}")

        # Clean target layers before processing (only for entities that will be pushed)
        configs_to_process = [c for c in block_configs if self._get_sync_direction(c) == 'push']
        log_info(f"Processing {len(configs_to_process)} block inserts in push mode")
        self.clean_target_layers(msp.doc, configs_to_process)

        # Process using sync manager in BOTH spaces (modelspace and paperspace)
        # Block entities can be in either space, so we need to process both
        log_info("Processing blocks in modelspace...")
        processed_blocks_msp = self.process_entities(msp.doc, msp)
        log_info("Processing blocks in paperspace...")
        processed_blocks_psp = self.process_entities(msp.doc, msp.doc.paperspace())

        total_processed = len(processed_blocks_msp) + len(processed_blocks_psp)
        log_info(f"✅ Processed {total_processed} block inserts using sync system (MSP: {len(processed_blocks_msp)}, PSP: {len(processed_blocks_psp)})")
        log_info("=" * 80)

    def clean_target_layers(self, doc, configs_to_process):
        """Clean target layers for block configs (both spaces). Uses centralized logic."""
        return self._centralize_target_layer_cleaning(doc, configs_to_process)

    def insert_blocks(self, space, config):
        """Insert blocks using shared placement utilities for bulk operations."""
        # Determine layer for block insert and ensure it exists (centralized)
        layer_name = self._ensure_entity_layer_exists(space.doc, config)

        # Update config with resolved layer name for the placement utilities
        config_with_layer = config.copy()
        config_with_layer['layer'] = layer_name

        # Use shared utilities for bulk block placement
        created_blocks = BlockPlacementUtils.place_blocks_bulk(
            space, config_with_layer, self.all_layers, self.script_identifier
        )

        log_debug(f"Inserted {len(created_blocks)} blocks for '{config.get('name')}'")
        return created_blocks

    def get_insertion_points(self, position_config):
        """Common method to get insertion points for both blocks and text."""
        return BlockPlacementUtils.get_insertion_points(position_config, self.all_layers)

    def get_insert_point(self, geometry, position_config):
        """Get insertion point for a specific geometry."""
        return BlockPlacementUtils.get_insert_point(geometry, position_config, self.all_layers)

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

            # Determine layer for block insert and ensure it exists (centralized)
            layer_name = self._ensure_entity_layer_exists(doc, config)

            # Prepare config with resolved layer name for placement utilities
            config_with_layer = config.copy()
            config_with_layer['layer'] = layer_name

            # Use shared placement utilities for single block placement
            block_ref = BlockPlacementUtils.place_block_single(
                target_space, config_with_layer, self.all_layers, self.script_identifier
            )

            if block_ref:
                # Attach custom metadata for sync tracking (sync-specific)
                self._attach_entity_metadata(block_ref, config)
                log_debug(f"Created block insert '{name}' from YAML config")
                return block_ref
            else:
                log_warning(f"Failed to create block insert '{name}' using shared utilities")
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
            log_debug(f"🔍 DEBUG: Searching for block '{entity_name}' with script ID '{self.script_identifier}'")

            # Search modelspace first (where most block inserts like equipment symbols are), then paperspace
            spaces = [doc.modelspace(), doc.paperspace()]

            for space in spaces:
                log_debug(f"🔍 DEBUG: Searching in {space}")

                # Try to find the specific entity
                entity = find_entity_by_xdata_name(space, entity_name, ['INSERT'])
                if entity and entity.dxftype() == 'INSERT':
                    log_debug(f"🔍 DEBUG: ✅ Found block insert '{entity_name}' in {space}")

                    # Validate entity handle (auto sync integrity check)
                    if self._validate_entity_handle(entity, entity_name):
                        return entity
                    else:
                        log_debug(f"🔍 DEBUG: ❌ Block insert '{entity_name}' failed handle validation (copied entity)")
                        return None  # Treat as missing to trigger push

            log_debug(f"🔍 DEBUG: ❌ Block insert '{entity_name}' not found in any space")
            return None

        except Exception as e:
            import traceback
            log_warning(f"Error finding block insert '{entity_name}': {repr(e)}")
            log_warning(f"Full traceback: {traceback.format_exc()}")
            return None

    def _find_entity_by_name_ignoring_handle_validation(self, doc, entity_name):
        """Find block insert entity in DXF by name without handle validation for recovery purposes."""
        try:
            log_debug(f"🔍 RECOVERY: Searching for block '{entity_name}' without handle validation")

            # Search modelspace first (where most block inserts like equipment symbols are), then paperspace
            spaces = [doc.modelspace(), doc.paperspace()]

            for space in spaces:
                # Try to find the specific entity
                entity = find_entity_by_xdata_name(space, entity_name, ['INSERT'])
                if entity and entity.dxftype() == 'INSERT':
                    log_debug(f"🔍 RECOVERY: ✅ Found block insert '{entity_name}' in {space} (no validation)")
                    # Return entity without handle validation for recovery
                    return entity

            log_debug(f"🔍 RECOVERY: ❌ Block insert '{entity_name}' not found in any space")
            return None

        except Exception as e:
            log_warning(f"Error in recovery search for block insert '{entity_name}': {repr(e)}")
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
        discovered = super()._discover_unknown_entities(doc, space)

        # BlockInsertManager doesn't need additional entity-specific behavior
        # Base implementation handles all the discovery logic
        return discovered

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
                    deletion_policy = self.project_settings['block_deletion_policy']  # Always present from ProjectLoader

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



    def _get_entity_types_for_search(self):
        """Get DXF entity types for block insert search."""
        return ['INSERT']



    def _find_all_entities_with_xdata_name(self, doc, entity_name):
        """Find all block inserts with matching XDATA name. Block-specific implementation."""
        matching_entities = []
        from src.dxf_utils import XDATA_APP_ID

        # Search in both model space and all paper spaces
        spaces_to_search = [doc.modelspace()]
        spaces_to_search.extend(layout for layout in doc.layouts if layout.name != 'Model')

        for space in spaces_to_search:
            for insert in space.query('INSERT'):
                # Skip entities based on manager-specific skip logic
                if self._should_skip_entity(insert):
                    continue

                # Check if this insert has our XDATA with matching name
                try:
                    xdata_name = self._get_entity_name_from_xdata(insert)
                    if xdata_name == entity_name:
                        matching_entities.append(insert)
                except:
                    continue

        return matching_entities

    # _get_config_key is now implemented in UnifiedSyncProcessor
