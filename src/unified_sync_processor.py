from abc import ABC, abstractmethod
from src.utils import log_info, log_warning, log_error, log_debug
from src.sync_hash_utils import (
    detect_entity_changes, resolve_sync_conflict, update_sync_metadata,
    ensure_sync_metadata_complete, clean_entity_config_for_yaml_output
)
from src.dxf_utils import XDATA_APP_ID, attach_custom_data


class UnifiedSyncProcessor(ABC):
    """
    Unified sync processor that handles all sync modes (push/auto/pull/skip) with appropriate layer cleaning.

    This replaces the old pattern of mixed updateDxf flags and sync modes with a clean, unified approach:
    - push: Bulk replacement (for generated content like geom_layers)
    - auto: Selective updates (for manual content like text_inserts)
    - pull: Read-only (update YAML from DXF)
    - skip: HANDS-OFF - entity properties never modified, only XDATA sync_mode aligned
    
    SKIP MODE GUARANTEES:
    - No metadata initialization (no _sync added to YAML)
    - No sync processing of entity properties
    - No YAML updates
    - No DXF property modifications (geometry, text, position, etc.)
    - ONLY XDATA sync_mode aligned to 'skip' for state consistency
    - Protected from orphan cleanup (even if XDATA has old sync_mode)
    - Protected from bulk layer cleaning
    """

    def __init__(self, project_settings, script_identifier, entity_type, project_loader=None):
        """
        Initialize the unified sync processor.

        Args:
            project_settings: Dictionary containing all project settings
            script_identifier: Unique identifier for this script's entities
            entity_type: Type of entity being managed (e.g., 'viewport', 'text')
            project_loader: Optional project loader for YAML write-back functionality
        """
        self.project_settings = project_settings
        self.script_identifier = script_identifier
        self.entity_type = entity_type
        self.project_loader = project_loader

        # Extract global sync setting (e.g., 'viewport_sync', 'text_sync')
        sync_key = f'{entity_type}_sync'
        self.default_sync = project_settings[sync_key]  # Should always be present from ProjectLoader

        # Extract deletion settings
        deletion_key = f'{entity_type}_deletion_policy'
        self.deletion_policy = project_settings[deletion_key]  # Should always be present from ProjectLoader

        # Extract discovery layers setting - this is the only discovery control
        discovery_layers_key = f'{entity_type}_discover_untracked_layers'
        self.discovery_layers = project_settings.get(discovery_layers_key, [])  # Default to empty list (disabled)

        # Extract default layer setting for unified layer handling
        default_layer_key = f'{entity_type}_default_layer'
        self.default_layer = project_settings.get(default_layer_key, self._get_fallback_default_layer())

        # Validate settings
        self._validate_settings()

    def _is_discovery_enabled(self):
        """
        Check if discovery is enabled based on layer settings.

        Returns:
            bool: True if discovery should run, False otherwise
        """
        # Discovery is enabled if:
        # 1. discovery_layers is "all" (string)
        # 2. discovery_layers is a non-empty list
        # Discovery is disabled if:
        # 1. discovery_layers is an empty list []
        # 2. discovery_layers is None

        if self.discovery_layers == "all":
            return True
        elif isinstance(self.discovery_layers, list) and len(self.discovery_layers) > 0:
            return True
        else:
            return False

    def _validate_settings(self):
        """Validate sync processor settings."""
        # Note: Validation is now handled in ProjectLoader
        # This method is kept for potential future use but settings should already be validated
        pass

    def process_entities(self, doc, space):
        """
        Main processing method for entity synchronization with mode-specific handling.

        Args:
            doc: DXF document
            space: Model space or paper space

        Returns:
            dict: Dictionary of processed entities
        """
        entity_configs = self._get_entity_configs()
        processed_entities = {}
        yaml_updated = False

        log_debug(f"Processing {len(entity_configs)} {self.entity_type} configurations")

        # Step 0: Initialize sync metadata for auto sync entities
        metadata_summary = ensure_sync_metadata_complete(entity_configs, self.entity_type, self)
        if metadata_summary['initialized_count'] > 0 or metadata_summary['repaired_count'] > 0:
            yaml_updated = True

        # Step 1: Group entities by sync mode for efficient processing
        entities_by_mode = self._group_entities_by_sync_mode(entity_configs)

        # Step 2: Process push mode entities (bulk replacement)
        if entities_by_mode['push']:
            push_results = self._process_push_mode_entities(doc, space, entities_by_mode['push'])
            processed_entities.update(push_results.get('entities', {}))
            if push_results.get('yaml_updated'):
                yaml_updated = True

        # Step 3: Process auto mode entities (selective updates)
        if entities_by_mode['auto']:
            auto_results = self._process_auto_mode_entities(doc, space, entities_by_mode['auto'])
            processed_entities.update(auto_results.get('entities', {}))
            if auto_results.get('yaml_updated'):
                yaml_updated = True

        # Step 4: Process pull mode entities (read-only)
        if entities_by_mode['pull']:
            pull_results = self._process_pull_mode_entities(doc, space, entities_by_mode['pull'])
            processed_entities.update(pull_results.get('entities', {}))
            if pull_results.get('yaml_updated'):
                yaml_updated = True

        # Step 5: Handle discovery if layer-based discovery is enabled
        if self._is_discovery_enabled():
            discovery_results = self._handle_discovery(doc, space)
            if discovery_results.get('yaml_updated'):
                yaml_updated = True

        # Step 5.5: Align XDATA sync_mode for skip entities (state consistency)
        if entities_by_mode['skip']:
            self._align_skip_entity_metadata(doc, space, entities_by_mode['skip'])

        # Step 6: Clean up orphaned entities (entities in DXF but removed from YAML)
        if entities_by_mode['auto'] or entities_by_mode['push']:
            orphan_results = self._handle_orphaned_entities(doc, space, entity_configs)
            if orphan_results.get('deleted_count', 0) > 0:
                log_info(f"🗑️ Cleaned up {orphan_results['deleted_count']} orphaned {self.entity_type} entities")

        # Step 7: Write back YAML changes if needed
        if yaml_updated and self.project_loader:
            self._write_entity_yaml()

        total_processed = len(processed_entities)
        log_debug(f"Processed {total_processed} {self.entity_type} entities")
        return processed_entities

    def _group_entities_by_sync_mode(self, entity_configs):
        """Group entities by their sync mode for efficient batch processing."""
        entities_by_mode = {
            'push': [],
            'auto': [],
            'pull': [],
            'skip': []
        }

        for config in entity_configs:
            sync_mode = self._get_sync_direction(config)
            entities_by_mode[sync_mode].append(config)

        log_debug(f"Grouped {self.entity_type} entities: push={len(entities_by_mode['push'])}, "
                 f"auto={len(entities_by_mode['auto'])}, pull={len(entities_by_mode['pull'])}, "
                 f"skip={len(entities_by_mode['skip'])}")
        
        # Log skip entities explicitly - they will NOT be touched
        if entities_by_mode['skip']:
            skip_names = [config.get('name', 'unnamed') for config in entities_by_mode['skip']]
            log_debug(f"⏭️  SKIP mode: {len(entities_by_mode['skip'])} {self.entity_type} entities will be left completely alone: {', '.join(skip_names)}")

        return entities_by_mode

    def _process_push_mode_entities(self, doc, space, configs):
        """
        Process push mode entities with bulk layer replacement.
        This is the traditional behavior for generated content.
        
        Handle Preservation: If entities have existing handles in YAML,
        those handles are preserved when recreating entities. This ensures
        stable references when switching between push and auto modes.
        """
        if not configs:
            return {'entities': {}, 'yaml_updated': False}

        log_debug(f"Processing {len(configs)} push mode {self.entity_type} entities")

        # Step 1: Collect old handles BEFORE cleaning (for handle preservation)
        old_handles = {}
        for config in configs:
            entity_name = config.get('name', 'unnamed')
            sync_metadata = config.get('_sync', {})
            if 'dxf_handle' in sync_metadata:
                old_handles[entity_name] = sync_metadata['dxf_handle']
                log_debug(f"Preserving handle {old_handles[entity_name]} for {self.entity_type} '{entity_name}'")

        # Step 2: Bulk clean target layers (traditional approach)
        self._bulk_clean_target_layers(doc, configs)

        # Step 3: Create all entities from YAML configs with handle preservation
        processed_entities = {}
        yaml_updated = False

        for config in configs:
            try:
                entity_name = config.get('name', 'unnamed')
                result = self._sync_push(doc, space, config)

                if result:
                    # HANDLE PRESERVATION: Reuse old handle if it existed
                    if entity_name in old_handles:
                        old_handle = old_handles[entity_name]
                        new_handle = str(result.dxf.handle)
                        
                        if old_handle != new_handle:
                            log_debug(f"Preserving handle for '{entity_name}': {new_handle} → {old_handle}")
                            
                            # Remove entity from database with auto-assigned handle
                            try:
                                del doc.entitydb[new_handle]
                            except KeyError:
                                pass
                            
                            # Set entity to use the old handle
                            result.dxf.handle = old_handle
                            
                            # Re-add entity to database with preserved handle
                            doc.entitydb[old_handle] = result
                            
                            log_debug(f"✓ Handle preserved for {self.entity_type} '{entity_name}': {old_handle}")
                    
                    processed_entities[entity_name] = result
                    # Update sync metadata for push mode
                    content_hash = self._calculate_entity_hash(config)
                    entity_handle = str(result.dxf.handle)  # Use final handle (preserved or new)
                    update_sync_metadata(config, content_hash, 'yaml', entity_handle=entity_handle)
                    yaml_updated = True

            except Exception as e:
                log_error(f"Error processing push mode {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
                import traceback
                log_debug(f"Traceback: {traceback.format_exc()}")
                continue

        if old_handles:
            log_info(f"✓ Preserved {len(old_handles)} handles for {self.entity_type} entities in push mode")

        return {'entities': processed_entities, 'yaml_updated': yaml_updated}

    def _process_auto_mode_entities(self, doc, space, configs):
        """
        Process auto mode entities with selective updates.
        Only update entities that have actually changed.
        """
        if not configs:
            return {'entities': {}, 'yaml_updated': False}

        log_debug(f"Processing {len(configs)} auto mode {self.entity_type} entities")

        processed_entities = {}
        yaml_updated = False
        configs_to_delete = []  # Track configs marked for deletion

        for config in configs:
            try:
                entity_name = config.get('name', 'unnamed')

                # Find existing entity (simplified - no duplicate handling)
                entity_name = config.get('name', 'unnamed')
                existing_entity = self._find_entity_by_name(doc, entity_name)

                # Perform intelligent sync
                result = self._process_auto_sync(doc, space, config)

                if result:
                    # Check if entity was marked for deletion
                    if result.get('deleted'):
                        configs_to_delete.append(config)
                        yaml_updated = True
                    elif result.get('entity'):
                        processed_entities[entity_name] = result['entity']
                    if result.get('yaml_updated'):
                        yaml_updated = True

            except Exception as e:
                log_error(f"Error processing auto mode {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
                continue



        # Remove configs marked for deletion from the entity configs list
        if configs_to_delete:
            entity_configs = self._get_entity_configs()
            for config_to_delete in configs_to_delete:
                if config_to_delete in entity_configs:
                    entity_configs.remove(config_to_delete)
                    log_debug(f"Removed {self.entity_type} '{config_to_delete.get('name', 'unnamed')}' from YAML")
            yaml_updated = True

        return {'entities': processed_entities, 'yaml_updated': yaml_updated}

    def _process_pull_mode_entities(self, doc, space, configs):
        """
        Process pull mode entities (read-only).
        Update YAML from DXF without changing DXF.
        """
        if not configs:
            return {'entities': {}, 'yaml_updated': False}

        log_debug(f"Processing {len(configs)} pull mode {self.entity_type} entities")

        processed_entities = {}
        yaml_updated = False

        for config in configs:
            try:
                entity_name = config.get('name', 'unnamed')
                result = self._sync_pull(doc, space, config)

                if result and result.get('yaml_updated'):
                    # Update sync metadata for pull mode
                    content_hash = self._calculate_entity_hash(config)
                    existing_entity = self._find_entity_by_name(doc, entity_name)
                    entity_handle = str(existing_entity.dxf.handle) if existing_entity else None
                    update_sync_metadata(config, content_hash, 'dxf', entity_handle=entity_handle)

                    if result.get('entity'):
                        processed_entities[entity_name] = result['entity']
                    yaml_updated = True

            except Exception as e:
                log_error(f"Error processing pull mode {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
                continue

        return {'entities': processed_entities, 'yaml_updated': yaml_updated}

    def _bulk_clean_target_layers(self, doc, configs):
        """
        Bulk clean target layers for push mode entities.
        This is the traditional layer cleaning approach.
        
        CRITICAL: Must protect skip entities on the same layer!
        """
        target_layers = set()
        for config in configs:
            layer_name = self._resolve_entity_layer(config)
            target_layers.add(layer_name)

        # Get ALL configs to protect non-push entities on same layers
        # CRITICAL: Push mode should only delete/recreate ITS OWN entities, not auto/pull/skip entities!
        all_configs = self._get_entity_configs()
        protected_entity_names = {config.get('name') for config in all_configs 
                                 if config.get('name') and self._get_sync_direction(config) in ['skip', 'auto', 'pull']}

        # Clean layers using traditional approach, but protect non-push entities
        for layer_name in target_layers:
            log_debug(f"Bulk cleaning {self.entity_type} entities from layer: {layer_name}")
            if protected_entity_names:
                log_debug(f"Protecting {len(protected_entity_names)} non-push entities from bulk cleaning: {', '.join(list(protected_entity_names)[:5])}...")
            self._clean_layer_entities(doc, layer_name, protected_entity_names)

    def _clean_layer_entities(self, doc, layer_name, skip_entity_names=None):
        """
        Clean entities from a specific layer.
        Can be overridden by subclasses for space-specific handling.
        
        Args:
            doc: DXF document
            layer_name: Layer to clean
            skip_entity_names: Set of entity names to SKIP (don't delete)
        """
        if skip_entity_names is None:
            skip_entity_names = set()
        
        # CRITICAL: Clean from modelspace AND all paperspace layouts
        spaces = [doc.modelspace()]
        spaces.extend(layout for layout in doc.layouts if layout.name != 'Model')
        
        for space in spaces:
            from src.dxf_utils import remove_entities_by_layer
            remove_entities_by_layer(space, layer_name, self.script_identifier, skip_entity_names)

    def _get_sync_direction(self, config):
        """
        Determine sync direction for an entity config.
        Uses only the new sync field - no legacy support.
        """
        entity_name = config.get('name', 'unnamed')

        # Check for sync field
        if 'sync' in config:
            sync = config['sync']
        else:
            # Use global default
            sync = self.default_sync
            log_debug(f"{self.entity_type.title()} '{entity_name}' using global sync setting: {sync}")

        # Validate sync direction
        valid_sync_values = {'push', 'pull', 'skip', 'auto'}
        if sync in valid_sync_values:
            return sync
        else:
            log_warning(f"Invalid sync direction '{sync}' for {self.entity_type} {entity_name}. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using 'skip'.")
            return 'skip'

    # Abstract methods that must be implemented by subclasses
    @abstractmethod
    def _get_entity_configs(self):
        """Get entity configurations from project settings."""
        pass

    @abstractmethod
    def _sync_push(self, doc, space, config):
        """Push entity from YAML to DXF."""
        pass

    @abstractmethod
    def _sync_pull(self, doc, space, config):
        """Pull entity from DXF to YAML."""
        pass

    @abstractmethod
    def _find_entity_by_name(self, doc, entity_name):
        """Find entity by name in DXF."""
        pass

    @abstractmethod
    def _find_entity_by_name_ignoring_handle_validation(self, doc, entity_name):
        """Find entity by name without handle validation for recovery purposes."""
        pass

    @abstractmethod
    def _calculate_entity_hash(self, config):
        """Calculate content hash for entity config."""
        pass

    @abstractmethod
    def _resolve_entity_layer(self, config):
        """Resolve the layer name for an entity."""
        pass

    @abstractmethod
    def _get_fallback_default_layer(self):
        """Get fallback default layer name."""
        pass

    def _repair_entity_handle_tracking(self, entity, config):
        """
        Repair handle tracking for recovered entity.

        Args:
            entity: DXF entity that was recovered
            config: Entity configuration to update

        Returns:
            bool: True if repair was successful, False otherwise
        """
        try:
            new_handle = str(entity.dxf.handle)
            entity_name = config.get('name', 'unnamed')

            # Update YAML metadata
            if '_sync' not in config:
                config['_sync'] = {}
            config['_sync']['dxf_handle'] = new_handle

            # Update XDATA with new handle
            from src.dxf_utils import attach_custom_data
            # Re-attach metadata with correct handle
            attach_custom_data(
                entity,
                self.script_identifier,
                entity_name=entity_name,
                entity_type=self.entity_type.upper(),
                content_hash=self._calculate_entity_hash(config),
                entity_handle=new_handle,
                sync_mode=self._get_sync_direction(config)
            )

            log_info(f"✅ REPAIRED: {self.entity_type} '{entity_name}' handle tracking updated to {new_handle}")
            return True
        except Exception as e:
            log_warning(f"Failed to repair handle tracking for {self.entity_type}: {str(e)}")
            return False

    def _continue_with_recovered_entity(self, doc, space, config, recovered_entity):
        """
        Continue auto sync processing with recovered entity after handle repair.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration
            recovered_entity: The recovered DXF entity

        Returns:
            dict: Result dictionary with 'entity' and 'yaml_updated' keys
        """
        try:
            entity_name = config.get('name', 'unnamed')

            # Re-run change detection with recovered entity
            from src.sync_hash_utils import detect_entity_changes
            changes = detect_entity_changes(config, recovered_entity, self.entity_type, self)

            # Now process normally based on changes
            if changes['yaml_changed'] and not changes['dxf_changed']:
                # YAML has changes to push
                log_info(f"🔄 RECOVERED+PUSH: Updating '{entity_name}' in DXF (YAML changed)")
                result = self._sync_push(doc, space, config)
                if result:
                    entity_handle = str(result.dxf.handle)
                    from src.sync_hash_utils import update_sync_metadata
                    update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
                return {'entity': result, 'yaml_updated': True} if result else None

            elif not changes['yaml_changed'] and changes['dxf_changed']:
                # DXF has changes to pull
                log_info(f"🔄 RECOVERED+PULL: Pulling changes from DXF to YAML for '{entity_name}' (DXF changed)")
                result = self._sync_pull(doc, space, config)
                if result and result.get('yaml_updated'):
                    entity_handle = str(recovered_entity.dxf.handle)
                    from src.sync_hash_utils import update_sync_metadata
                    update_sync_metadata(config, changes['current_dxf_hash'], 'dxf', entity_handle=entity_handle)
                return result if result else None

            elif changes['yaml_changed'] and changes['dxf_changed']:
                # Conflict - use existing conflict resolution
                log_warning(f"🔄 RECOVERED+CONFLICT: Both YAML and DXF changed for '{entity_name}'")
                # Let the normal conflict resolution handle this
                return self._handle_sync_conflict(doc, space, config, recovered_entity, changes)

            else:
                # No changes detected - just update metadata and continue
                log_info(f"🔄 RECOVERED+SYNC: Entity '{entity_name}' recovered, no changes detected")
                entity_handle = str(recovered_entity.dxf.handle)
                from src.sync_hash_utils import update_sync_metadata
                update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
                return {'entity': recovered_entity, 'yaml_updated': True}

        except Exception as e:
            log_warning(f"Failed to continue with recovered entity '{entity_name}': {str(e)}")
            # Fallback to push if recovery continuation fails
            result = self._sync_push(doc, space, config)
            return {'entity': result, 'yaml_updated': True} if result else None

    def _handle_sync_conflict(self, doc, space, config, dxf_entity, changes):
        """
        Handle sync conflict when both YAML and DXF have changed.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration
            dxf_entity: DXF entity object
            changes: Change detection results

        Returns:
            dict: Result dictionary with 'entity' and 'yaml_updated' keys
        """
        entity_name = config.get('name', 'unnamed')
        log_warning(f"⚠️  SYNC CONFLICT: Both YAML and DXF changed for '{entity_name}'")

        # Use the existing conflict resolution system
        from src.sync_hash_utils import resolve_sync_conflict
        resolution = resolve_sync_conflict(entity_name, config, dxf_entity, self.project_settings)

        if resolution == 'yaml_wins':
            log_info(f"🔄 CONFLICT RESOLVED: YAML wins for '{entity_name}'")
            result = self._sync_push(doc, space, config)
            if result:
                entity_handle = str(result.dxf.handle)
                from src.sync_hash_utils import update_sync_metadata
                update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
            return {'entity': result, 'yaml_updated': True} if result else None

        elif resolution == 'dxf_wins':
            log_info(f"🔄 CONFLICT RESOLVED: DXF wins for '{entity_name}'")
            result = self._sync_pull(doc, space, config)
            if result and result.get('yaml_updated'):
                entity_handle = str(dxf_entity.dxf.handle) if dxf_entity else None
                from src.sync_hash_utils import update_sync_metadata
                update_sync_metadata(config, changes['current_dxf_hash'], 'dxf', entity_handle=entity_handle)
            return result if result else None

        else:  # resolution == 'skip'
            log_info(f"🔄 CONFLICT RESOLVED: Skipping '{entity_name}' per conflict resolution policy")
            return None

    # Default implementations for optional methods

    def _ensure_xdata_name_sync(self, entity, expected_name):
        """
        Option 1: Auto-update XDATA name to match YAML name during normal processing.

        This ensures that when users rename entities in YAML, the DXF XDATA is automatically
        updated to match, preventing sync issues.

        Args:
            entity: DXF entity to check and potentially update
            expected_name: Expected name from YAML configuration
        """
        try:
            current_xdata_name = self._get_entity_name_from_xdata(entity)

            if current_xdata_name and current_xdata_name != expected_name:
                log_info(f"🔄 AUTO-SYNC: Updating XDATA name '{current_xdata_name}' → '{expected_name}' "
                        f"for {self.entity_type} entity {entity.dxf.handle}")
                self._update_entity_xdata_name(entity, expected_name)

        except Exception as e:
            log_warning(f"Error syncing XDATA name for entity {entity.dxf.handle}: {str(e)}")

    def _update_entity_xdata_name(self, entity, new_name):
        """Update entity name in XDATA."""
        try:
            from src.dxf_utils import XDATA_APP_ID, XDATA_ENTITY_NAME_KEY

            # Get current XDATA
            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                return False

            # Build new XDATA with updated name
            new_xdata = []
            in_entity_section = False
            name_updated = False

            for code, value in xdata:
                if code == 1000 and value == XDATA_ENTITY_NAME_KEY:
                    in_entity_section = True
                    new_xdata.append((code, value))
                elif in_entity_section and code == 1000 and not name_updated:
                    # Replace the old name with new name
                    new_xdata.append((code, new_name))
                    name_updated = True
                    in_entity_section = False
                else:
                    new_xdata.append((code, value))

            # Update the entity's XDATA
            entity.set_xdata(XDATA_APP_ID, new_xdata)
            return True

        except Exception as e:
            log_error(f"Error updating entity XDATA name: {str(e)}")
            return False



    def _find_all_entities_with_xdata_name(self, doc, entity_name):
        """Find all entities with matching XDATA name. Entity-specific implementation required."""
        # This method should be overridden by entity managers to provide entity-specific search logic
        # Default implementation: just find by name (no XDATA search)
        entity = self._find_entity_by_name(doc, entity_name)
        return [entity] if entity else []

    def _should_skip_entity(self, entity):
        """
        Determine if an entity should be skipped during processing.
        Default implementation: don't skip any entities.

        Entity managers can override this to implement entity-specific skip logic.
        For example, ViewportManager skips the main viewport (ID=1).

        Args:
            entity: DXF entity to check

        Returns:
            bool: True if entity should be skipped, False otherwise
        """
        return False

    def _process_auto_sync(self, doc, space, config):
        """
        Process entity using state-based automatic sync with selective updates.
        This preserves entity handles by only updating what actually changed.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration

        Returns:
            dict: Result dictionary with 'entity' and 'yaml_updated' keys
        """
        entity_name = config.get('name', 'unnamed')

        # Find existing DXF entity (simplified - no duplicate handling)
        existing_entity = self._find_entity_by_name(doc, entity_name)

        # Detect changes using hash comparison
        from src.sync_hash_utils import detect_entity_changes
        changes = detect_entity_changes(config, existing_entity, self.entity_type, self)

        # State-based sync logic
        yaml_exists = True  # We have config (always true in this context)
        dxf_exists = existing_entity is not None

        log_debug(f"Auto sync analysis for '{entity_name}': "
                 f"YAML exists: {yaml_exists}, DXF exists: {dxf_exists}, "
                 f"YAML changed: {changes['yaml_changed']}, DXF changed: {changes['dxf_changed']}")

        # PRIORITY 1: State-based logic - ensure desired state exists
        if yaml_exists and not dxf_exists:
            # Check if entity was previously tracked
            sync_metadata = config.get('_sync', {})
            stored_handle = sync_metadata.get('dxf_handle') if sync_metadata else None

            if stored_handle:
                # BEFORE assuming deletion, try name-based recovery
                log_warning(f"⚠️  Entity '{entity_name}' not found by handle {stored_handle} - attempting name-based recovery")

                # Try to find by name without handle validation for recovery
                recovered_entity = self._find_entity_by_name_ignoring_handle_validation(doc, entity_name)
                if recovered_entity:
                    # Found by name! Handle probably changed - update tracking
                    new_handle = str(recovered_entity.dxf.handle)
                    log_info(f"✅ RECOVERED: Entity '{entity_name}' found with new handle {new_handle} (was {stored_handle})")

                    # Repair handle tracking
                    if self._repair_entity_handle_tracking(recovered_entity, config):
                        # Re-run auto sync with recovered entity - continue with normal change detection
                        return self._continue_with_recovered_entity(doc, space, config, recovered_entity)
                    else:
                        log_warning(f"Failed to repair handle tracking for '{entity_name}', falling back to push")
                        # Fallback to push if repair fails
                        result = self._sync_push(doc, space, config)
                        if result:
                            entity_handle = str(result.dxf.handle)
                            from src.sync_hash_utils import update_sync_metadata
                            update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
                        return {'entity': result, 'yaml_updated': True} if result else None
                else:
                    # Really not found anywhere - check deletion policy before removing
                    log_warning(f"⚠️  Entity '{entity_name}' not found by handle OR name")
                    
                    # Respect deletion policy
                    if self.deletion_policy == 'ignore':
                        log_info(f"Keeping '{entity_name}' in YAML (deletion_policy=ignore)")
                        return None
                    elif self.deletion_policy == 'confirm':
                        # Ask user for confirmation
                        deleted_configs = self._confirm_delete_missing_entities([config])
                        if deleted_configs:
                            log_info(f"User confirmed deletion of '{entity_name}'")
                            return self._handle_yaml_deletion(config)
                        else:
                            log_info(f"User declined deletion of '{entity_name}'")
                            return None
                    else:  # 'auto' policy
                        log_warning(f"🗑️  Entity '{entity_name}' - auto-deleting from YAML (deletion_policy=auto)")
                        return self._handle_yaml_deletion(config)
            else:
                # No sync history - entity never existed, should be created
                log_info(f"🔄 AUTO: Creating missing entity '{entity_name}' in DXF (never existed)")
                result = self._sync_push(doc, space, config)
                if result:
                    entity_handle = str(result.dxf.handle)
                    from src.sync_hash_utils import update_sync_metadata
                    update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
                return {'entity': result, 'yaml_updated': True} if result else None

        # PRIORITY 2: Change-based logic for existing entities
        elif yaml_exists and dxf_exists:
            if changes['yaml_changed'] and not changes['dxf_changed']:
                # Only YAML changed - push to DXF (selective update, preserving handle)
                log_info(f"🔄 AUTO: Updating '{entity_name}' in DXF (YAML changed)")
                result = self._sync_push(doc, space, config)
                if result:
                    entity_handle = str(result.dxf.handle)
                    from src.sync_hash_utils import update_sync_metadata
                    update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
                return {'entity': result, 'yaml_updated': True} if result else None

            elif not changes['yaml_changed'] and changes['dxf_changed']:
                # Only DXF changed - pull from DXF
                log_info(f"🔄 AUTO: Pulling changes from DXF to YAML for '{entity_name}' (DXF changed)")
                result = self._sync_pull(doc, space, config)
                if result and result.get('yaml_updated'):
                    # Get handle from existing entity for tracking
                    entity_handle = str(existing_entity.dxf.handle) if existing_entity else None
                    from src.sync_hash_utils import update_sync_metadata
                    update_sync_metadata(config, changes['current_dxf_hash'], 'dxf', entity_handle=entity_handle)
                return result if result else None

            elif changes['yaml_changed'] and changes['dxf_changed']:
                # Both changed - resolve conflict using settings
                log_info(f"⚠️  AUTO: Conflict detected for '{entity_name}' - both YAML and DXF changed")

                from src.sync_hash_utils import resolve_sync_conflict
                resolution = resolve_sync_conflict(entity_name, config, existing_entity, self.project_settings)

                if resolution == 'yaml_wins':
                    log_info(f"🔄 AUTO: Resolving conflict for '{entity_name}': YAML wins")
                    result = self._sync_push(doc, space, config)
                    if result:
                        entity_handle = str(result.dxf.handle)
                        from src.sync_hash_utils import update_sync_metadata
                        update_sync_metadata(config, changes['current_yaml_hash'], 'yaml', entity_handle=entity_handle)
                    return {'entity': result, 'yaml_updated': True} if result else None

                elif resolution == 'dxf_wins':
                    log_info(f"🔄 AUTO: Resolving conflict for '{entity_name}': DXF wins")
                    result = self._sync_pull(doc, space, config)
                    if result and result.get('yaml_updated'):
                        entity_handle = str(existing_entity.dxf.handle) if existing_entity else None
                        from src.sync_hash_utils import update_sync_metadata
                        update_sync_metadata(config, changes['current_dxf_hash'], 'dxf', entity_handle=entity_handle)
                    return result if result else None

                else:  # resolution == 'skip'
                    log_info(f"🔄 AUTO: Skipping conflicted entity '{entity_name}' per conflict resolution policy")
                    return None

            else:
                # No changes detected - both exist and are synchronized
                # However, check if XDATA sync_mode needs updating (e.g., switched from skip → auto)
                from src.dxf_utils import _extract_sync_mode_from_xdata
                dxf_sync_mode = _extract_sync_mode_from_xdata(existing_entity)
                yaml_sync_mode = self._get_sync_direction(config)
                
                if dxf_sync_mode and dxf_sync_mode != yaml_sync_mode:
                    log_info(f"🔄 AUTO: Sync mode changed for '{entity_name}' (DXF: {dxf_sync_mode} → YAML: {yaml_sync_mode}) - updating XDATA")
                    self._attach_entity_metadata(existing_entity, config)
                    # Note: No need to update stored hash since content unchanged
                else:
                    log_debug(f"🔄 AUTO: '{entity_name}' unchanged - maintaining current state")
                
                return {'entity': existing_entity, 'yaml_updated': False}

        else:
            # This shouldn't happen (yaml_exists is always True in this context)
            log_error(f"🔄 AUTO: Unexpected state for '{entity_name}' - YAML missing")
            return None

    def _handle_discovery(self, doc, space):
        """Handle entity discovery with proper implementation."""

        if not self._is_discovery_enabled():
            log_debug(f"🔍 DEBUG: Discovery not enabled for {self.entity_type}")
            return {'yaml_updated': False}

        log_debug(f"🔍 DEBUG: Running discovery for {self.entity_type} entities on layers: {self.discovery_layers}")

        # Discover untracked entities
        discovered_entities = self._discover_unknown_entities(doc, space)
        log_debug(f"🔍 DEBUG: Found {len(discovered_entities)} untracked entities")

        if not discovered_entities:
            log_debug(f"🔍 DEBUG: No untracked {self.entity_type} entities found")
            return {'yaml_updated': False}

        # Add discovered entities to configuration
        config_key = self._get_config_key()
        entity_configs = self.project_settings.get(config_key, [])
        log_debug(f"🔍 DEBUG: Current config has {len(entity_configs)} existing entities")

        yaml_updated = False
        for discovery in discovered_entities:
            entity = discovery['entity']
            entity_name = discovery['name']

            log_debug(f"🔍 DEBUG: Processing discovered entity '{entity_name}' (handle: {entity.dxf.handle})")

            # Extract entity properties for configuration
            entity_config = self._extract_entity_properties(entity, {'name': entity_name})

            # Set default sync mode for discovered entities
            entity_config['sync'] = 'auto'  # Default for discovered entities

            # Add to configurations
            entity_configs.append(entity_config)

            # Attach metadata to mark as managed
            self._attach_entity_metadata(entity, entity_config)

            # CRITICAL: Populate complete sync metadata for discovered entities
            content_hash = self._calculate_entity_hash(entity_config)
            entity_handle = str(entity.dxf.handle)
            from src.sync_hash_utils import update_sync_metadata
            update_sync_metadata(entity_config, content_hash, 'dxf', entity_handle=entity_handle)

            log_info(f"🔍 Discovered new {self.entity_type} entity: '{entity_name}' on layer '{entity.dxf.layer}' with complete sync metadata")
            yaml_updated = True

        # Update project settings
        if yaml_updated:
            self.project_settings[config_key] = entity_configs
            log_debug(f"🔍 DEBUG: Updated project settings with {len(entity_configs)} total entities")

        return {'yaml_updated': yaml_updated}

    def _discover_unknown_entities(self, doc, space):
        """
        Find entities that exist in DXF but aren't properly tracked.

        This method searches for entities that either:
        1. Have no XDATA (completely untracked)
        2. Have invalid XDATA (wrong handle due to copying)

        Args:
            doc: DXF document
            space: Model space or paper space

        Returns:
            list: List of discovered entities with format [{'entity': entity, 'name': name}, ...]
        """
        log_debug(f"🔍 DEBUG: _discover_unknown_entities called for {self.entity_type} in {space}")
        discovered = []

        # Get entity types from child class implementation
        try:
            entity_types = self._get_entity_types()
            log_debug(f"🔍 DEBUG: Entity types: {entity_types}")
        except (NotImplementedError, AttributeError):
            log_warning(f"Child class doesn't implement _get_entity_types() - skipping discovery")
            return discovered

        # Build query string for all entity types
        query_string = ' '.join(entity_types)
        log_debug(f"🔍 DEBUG: Query string: '{query_string}'")

        # Search for entities in the current space
        all_entities = list(space.query(query_string))
        log_debug(f"🔍 DEBUG: Found {len(all_entities)} entities of matching types")

        for entity in all_entities:
            # Skip entities based on manager-specific logic
            if self._should_skip_entity(entity):
                continue

            # Check if entity is on a discovery layer
            entity_layer = getattr(entity.dxf, 'layer', None)
            if not entity_layer:
                continue

            # Filter by discovery layers
            if self.discovery_layers != "all" and entity_layer not in self.discovery_layers:
                continue

            # Check if entity has valid tracking (handle validation)
            if self._validate_entity_handle(entity, "discovery_check"):
                log_debug(f"🔍 DEBUG: Entity {entity.dxf.handle} is properly tracked, skipping")
                continue  # Properly tracked, skip

            log_debug(f"🔍 DEBUG: Entity {entity.dxf.handle} on layer {entity_layer} is untracked!")

            # Entity is untracked - discover it
            try:
                entity_name = self._generate_entity_name(entity, len(discovered))

                # Ensure name is unique within current configurations
                entity_name = self._ensure_unique_entity_name(entity_name)

                discovered.append({
                    'entity': entity,
                    'name': entity_name,
                    'layer': entity_layer,
                    'handle': str(entity.dxf.handle)
                })

                log_debug(f"Discovered untracked {self.entity_type}: '{entity_name}' (handle: {entity.dxf.handle})")

            except Exception as e:
                log_warning(f"Error processing discovered {self.entity_type} entity {entity.dxf.handle}: {str(e)}")
                continue

        return discovered

    def _ensure_unique_entity_name(self, base_name):
        """
        Ensure the generated entity name is unique within current configurations.

        Args:
            base_name: The base name to make unique

        Returns:
            str: A unique name
        """
        config_key = self._get_config_key()
        entity_configs = self.project_settings.get(config_key, [])
        existing_names = {config.get('name') for config in entity_configs}

        # If base name is unique, use it
        if base_name not in existing_names:
            return base_name

        # Generate numbered variations
        counter = 1
        while f"{base_name}_{counter}" in existing_names:
            counter += 1

        return f"{base_name}_{counter}"

    def _write_entity_yaml(self):
        """
        Write updated entity configuration back to YAML file.
        Centralized implementation that works for all entity types.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.project_loader:
            log_warning(f"Cannot write {self.entity_type} YAML - no project_loader available")
            return False

        try:
            # Get entity configurations and clean them for YAML output
            config_key = self._get_config_key()
            entity_configs = self.project_settings.get(config_key, [])

            cleaned_configs = []
            for config in entity_configs:
                cleaned_config = clean_entity_config_for_yaml_output(config)
                cleaned_configs.append(cleaned_config)

            # Prepare entity data structure
            yaml_data = {config_key: cleaned_configs}

            # Add global settings using entity type prefix
            global_settings = self._get_global_settings_for_yaml()
            yaml_data.update(global_settings)

            # Get YAML filename
            yaml_filename = self._get_yaml_filename()

            # Write back to YAML file
            success = self.project_loader.write_yaml_file(yaml_filename, yaml_data)
            if success:
                log_info(f"Successfully updated {yaml_filename} with sync changes")
            else:
                log_error(f"Failed to write {self.entity_type} configuration back to YAML")
            return success

        except Exception as e:
            log_error(f"Error writing {self.entity_type} YAML: {str(e)}")
            return False

    def _get_global_settings_for_yaml(self):
        """Get global settings for this entity type to include in YAML."""
        settings = {}
        prefix = f'{self.entity_type}_'

        # Standard global settings all entity types support
        setting_mappings = {
            'discover_untracked_layers': f'{prefix}discover_untracked_layers',
            'deletion_policy': f'{prefix}deletion_policy',
            'default_layer': f'{prefix}default_layer',
            'sync': f'{prefix}sync'
        }

        for yaml_key, project_key in setting_mappings.items():
            if project_key in self.project_settings:
                settings[yaml_key] = self.project_settings[project_key]

        return settings

    def _get_yaml_filename(self):
        """Get the YAML filename for this entity type with appropriate folder prefix."""
        # All sync manager entities are interactive content in interactive/ folder
        if self.entity_type == 'viewport':
            return 'interactive/viewports.yaml'
        elif self.entity_type == 'text':
            return 'interactive/text_inserts.yaml'
        elif self.entity_type == 'block':
            return 'interactive/block_inserts.yaml'
        else:
            return f'interactive/{self.entity_type}_inserts.yaml'

    def _get_config_key(self):
        """
        Get the configuration key for this entity type in project_settings.
        Uses consistent simple pluralization pattern.

        Returns:
            str: Configuration key for project_settings
        """
        return f'{self.entity_type}s'

    def _centralize_target_layer_cleaning(self, doc, configs_to_process):
        """
        Centralized target layer cleaning for entities.
        Backward compatibility method that delegates to the new unified logic.

        Args:
            doc: DXF document
            configs_to_process: List of configurations to process

        Returns:
            set: Set of layer names that were cleaned
        """
        # Only clean layers for push mode entities (maintains the old behavior)
        push_configs = [c for c in configs_to_process if self._get_sync_direction(c) == 'push']

        if push_configs:
            self._bulk_clean_target_layers(doc, push_configs)

        # Return the set of layers that were cleaned for backward compatibility
        target_layers = set()
        for config in push_configs:
            layer_name = self._resolve_entity_layer(config)
            target_layers.add(layer_name)

        return target_layers

    # Note: _get_target_space is implemented here in UnifiedSyncProcessor
    def _get_target_space(self, doc, config):
        """
        Get the target space (model or paper) for an entity with owner-based verification.

        Args:
            doc: DXF document
            config: Entity configuration dictionary

        Returns:
            Space object (doc.modelspace() or doc.paperspace())
        """
        config_paperspace = config.get('paperspace', False)
        target_space = doc.paperspace() if config_paperspace else doc.modelspace()

        # For existing entities, verify config matches actual location
        if '_sync' in config and 'dxf_handle' in config['_sync']:
            try:
                from src.dxf_utils import detect_entity_paperspace
                entity_handle = config['_sync']['dxf_handle']
                # Use doc.entitydb to get entity (works for all spaces/layouts)
                entity = doc.entitydb.get(entity_handle)

                if entity:
                    actual_paperspace = detect_entity_paperspace(entity)
                    if actual_paperspace is not None and actual_paperspace != config_paperspace:
                        entity_name = config.get('name', 'unnamed')
                        log_debug(f"Space mismatch for '{entity_name}': config says {'paperspace' if config_paperspace else 'modelspace'}, "
                                f"but entity is in {'paperspace' if actual_paperspace else 'modelspace'}")
                        # Return actual space to handle entity where it really is
                        return doc.paperspace() if actual_paperspace else doc.modelspace()
            except Exception as e:
                log_debug(f"Error verifying target space: {str(e)}")

        return target_space

    def _ensure_entity_layer_exists(self, doc, config):
        """
        Ensure the target layer for an entity exists in the document.

        Args:
            doc: DXF document
            config: Entity configuration dictionary

        Returns:
            str: The layer name that was ensured to exist
        """
        from src.dxf_utils import ensure_layer_exists

        layer_name = self._resolve_entity_layer(config)
        ensure_layer_exists(doc, layer_name)
        return layer_name

    def _attach_entity_metadata(self, entity, config):
        """
        Attach metadata to DXF entity for tracking.

        This method attaches XDATA to the entity for identification and management.
        It's careful not to overwrite sync metadata that's already been properly populated.
        """
        try:
            entity_name = config.get('name', 'unnamed')

            # Calculate content hash for the configuration
            content_hash = self._calculate_entity_hash(config)

            # Get entity handle for tracking
            entity_handle = str(entity.dxf.handle)

            # Get sync mode for XDATA
            sync_mode = self._get_sync_direction(config)

            # Use unified XDATA function with content hash, handle, and sync mode
            from src.dxf_utils import attach_custom_data
            attach_custom_data(
                entity,
                self.script_identifier,
                entity_name=entity_name,
                entity_type=self.entity_type.upper(),
                content_hash=content_hash,
                entity_handle=entity_handle,
                sync_mode=sync_mode
            )

            # Store handle in sync metadata for handle-based tracking
            # Only set basic handle if sync metadata doesn't already exist
            if '_sync' not in config:
                config['_sync'] = {}

            # Always update the handle (it should be the same anyway)
            config['_sync']['dxf_handle'] = entity_handle

            # Don't overwrite other sync metadata if it already exists
            # (this preserves complete metadata set during discovery)

            log_debug(f"Attached metadata to {self.entity_type} '{entity_name}' with handle {entity_handle}")

        except Exception as e:
            log_warning(f"Failed to attach metadata to {self.entity_type}: {str(e)}")

    def _find_entity_config_by_name(self, entity_name):
        """
        Find entity configuration by name.

        Args:
            entity_name: Name of the entity to find

        Returns:
            dict: Entity configuration or None if not found
        """
        config_key = self._get_config_key()
        entity_configs = self.project_settings.get(config_key, [])

        for config in entity_configs:
            if config.get('name') == entity_name:
                return config
        return None

    def _validate_entity_handle(self, entity, entity_name):
        """
        Validate that an entity's actual handle matches its stored XDATA handle.
        Simplified version without duplicate copy handling.

        Args:
            entity: DXF entity to validate
            entity_name: Name of the entity for logging

        Returns:
            bool: True if entity handle is valid, False otherwise
        """
        if not entity:
            return False

        try:
            # Check if entity has our XDATA
            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                # No XDATA - entity is unmanaged
                return False

            # Extract stored handle from XDATA
            from src.dxf_utils import extract_handle_from_xdata
            stored_handle = extract_handle_from_xdata(entity)
            actual_handle = str(entity.dxf.handle)

            if stored_handle == actual_handle:
                # Valid handle - entity is properly managed
                return True
            else:
                # Handle mismatch - invalid entity, clean stale XDATA
                log_debug(f"Handle mismatch for {self.entity_type} '{entity_name}': "
                         f"stored={stored_handle}, actual={actual_handle}")
                try:
                    entity.discard_xdata(XDATA_APP_ID)
                    log_debug(f"Cleaned stale XDATA from {self.entity_type} entity '{entity_name}'")
                except Exception as e:
                    log_warning(f"Failed to clean stale XDATA from '{entity_name}': {str(e)}")
                return False

        except Exception as e:
            log_warning(f"Error validating handle for {self.entity_type} '{entity_name}': {str(e)}")
            return False



    def _get_entity_name_from_xdata(self, entity):
        """
        Extract entity name from XDATA.

        Args:
            entity: DXF entity with XDATA

        Returns:
            str: Entity name or 'unnamed' if not found
        """
        try:
            from src.dxf_utils import XDATA_ENTITY_NAME_KEY

            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                return 'unnamed'

            # Extract entity name
            in_entity_section = False
            for code, value in xdata:
                if code == 1000 and value == XDATA_ENTITY_NAME_KEY:
                    in_entity_section = True
                elif in_entity_section and code == 1000:
                    return value

            return 'unnamed'
        except Exception:
            return 'unnamed'

    def _handle_yaml_deletion(self, config):
        """
        Handle deletion of entity from YAML when it was tracked but missing from DXF.

        This indicates the user deleted the entity from DXF, so we should remove
        it from YAML to maintain sync integrity.

        Args:
            config: Entity configuration to be removed

        Returns:
            dict: Result indicating YAML should be updated with entity removal
        """
        entity_name = config.get('name', 'unnamed')

        # Mark this config for deletion by adding a deletion marker
        # The calling process_entities method will handle the actual removal
        config['_delete_from_yaml'] = True

        log_debug(f"Marked {self.entity_type} '{entity_name}' for deletion from YAML")

        # Return result indicating YAML needs updating (entity will be removed)
        return {'entity': None, 'yaml_updated': True, 'deleted': True}

    def _auto_delete_missing_entities(self, missing_entities):
        """
        Automatically delete missing entities from YAML configuration.

        Args:
            missing_entities: List of entity configurations to delete

        Returns:
            list: List of deleted entity configurations
        """
        for config in missing_entities:
            entity_name = config.get('name', 'unnamed')
            log_info(f"Auto-deleted missing {self.entity_type} '{entity_name}' from YAML")
        
        return missing_entities

    def _confirm_delete_missing_entities(self, missing_entities):
        """
        Prompt user to confirm deletion of missing entities from YAML configuration.

        Args:
            missing_entities: List of entity configurations to potentially delete

        Returns:
            list: List of confirmed deleted entity configurations
        """
        deleted_configs = []
        
        for config in missing_entities:
            entity_name = config.get('name', 'unnamed')
            log_warning(f"{self.entity_type.capitalize()} '{entity_name}' exists in YAML but not found in AutoCAD")
            
            try:
                response = input(f"Delete '{entity_name}' from configuration? (y/N): ").lower().strip()
                # Default to "n" (no) if user just presses Enter - safer for destructive operations
                if not response:
                    response = 'n'
                
                if response == 'y':
                    deleted_configs.append(config)
                    log_info(f"User confirmed deletion of {self.entity_type} '{entity_name}' from YAML")
                else:
                    log_info(f"User declined deletion of {self.entity_type} '{entity_name}'")
            except (EOFError, KeyboardInterrupt):
                log_warning(f"User input interrupted - skipping deletion of '{entity_name}'")
                break
        
        return deleted_configs

    def _align_skip_entity_metadata(self, doc, space, skip_configs):
        """
        Align XDATA sync_mode for skip entities to maintain state consistency.
        
        Even though skip = hands-off, we update JUST the sync_mode metadata
        so XDATA matches YAML. This is a minimal touch for clarity and consistency.
        
        Args:
            doc: DXF document
            space: Model space or paper space
            skip_configs: List of entity configs with sync='skip'
        """
        aligned_count = 0
        
        for config in skip_configs:
            try:
                entity_name = config.get('name', 'unnamed')
                
                # Find entity in DXF
                entity = self._find_entity_by_name(doc, entity_name)
                if not entity:
                    continue
                
                # Check current XDATA sync_mode
                from src.dxf_utils import _extract_sync_mode_from_xdata
                dxf_sync_mode = _extract_sync_mode_from_xdata(entity)
                
                # Only update if XDATA sync_mode differs from 'skip'
                if dxf_sync_mode and dxf_sync_mode != 'skip':
                    # Update ONLY the sync_mode in XDATA (minimal touch)
                    self._attach_entity_metadata(entity, config)
                    log_debug(f"⏭️  Aligned XDATA sync_mode to 'skip' for '{entity_name}' (was '{dxf_sync_mode}')")
                    aligned_count += 1
                    
            except Exception as e:
                log_debug(f"Error aligning skip entity metadata for '{config.get('name', 'unnamed')}': {str(e)}")
                continue
        
        if aligned_count > 0:
            log_info(f"⏭️  Aligned XDATA sync_mode for {aligned_count} skip {self.entity_type} entities")

    def _handle_orphaned_entities(self, doc, space, current_configs):
        """
        Clean up entities that exist in DXF but are no longer in YAML configuration.

        This handles the case where entities were previously managed but their YAML
        configs have been removed/commented out. Only affects auto/push mode entities
        where YAML is the source of truth.

        Args:
            doc: DXF document
            space: Model space or paper space
            current_configs: List of currently active entity configurations

        Returns:
            dict: Result with deleted_count
        """
        # SAFETY: Skip orphaned cleanup only for 'ignore' policy
        # With 'confirm' policy, orphan cleanup runs but prompts user for confirmation
        if self.deletion_policy == 'ignore':
            log_debug(f"Orphaned entity cleanup skipped - deletion policy is 'ignore'")
            return {'deleted_count': 0}

        # CRITICAL: Get current config names for comparison
        # This MUST include all entities that exist in YAML, even if they couldn't be found in DXF
        current_names = {config.get('name') for config in current_configs if config.get('name')}
        # Also create normalized version for robust matching (case-insensitive, whitespace-stripped)
        current_names_normalized = {name.lower().strip() for name in current_names if name}
        
        # CRITICAL FIX: Build set of SKIP entity names from YAML
        # Entities with sync: skip in YAML should NEVER be considered orphaned,
        # even if their DXF XDATA still says 'push' or 'auto' from before they were changed to skip
        skip_entity_names = {config.get('name') for config in current_configs 
                            if config.get('name') and self._get_sync_direction(config) == 'skip'}
        skip_entity_names_normalized = {name.lower().strip() for name in skip_entity_names if name}

        # Find orphaned entities managed by our script
        orphaned_entities = []

        try:
            from src.dxf_utils import is_created_by_script, _extract_sync_mode_from_xdata

            # CRITICAL: Search ALL spaces (modelspace + all layouts), not just the passed space
            # The space parameter is kept for backward compatibility but we search everywhere
            spaces_to_search = [doc.modelspace()]
            spaces_to_search.extend(layout for layout in doc.layouts if layout.name != 'Model')
            
            for search_space in spaces_to_search:
                for entity in search_space:
                    if is_created_by_script(entity, self.script_identifier):
                        entity_name = self._get_entity_name_from_xdata(entity)
                        entity_sync_mode = _extract_sync_mode_from_xdata(entity)

                        # Normalize entity name for matching
                        entity_name_normalized = entity_name.lower().strip() if entity_name else None
                        
                        # CRITICAL: Check if entity is marked as 'skip' in YAML
                        # Skip entities should NEVER be considered orphaned, regardless of XDATA sync_mode
                        is_skip_in_yaml = (entity_name in skip_entity_names or 
                                          entity_name_normalized in skip_entity_names_normalized)
                        
                        # Check if entity is still in current configs
                        is_in_current_configs = (entity_name in current_names or 
                                                entity_name_normalized in current_names_normalized)
                        
                        # Only consider entity orphaned if:
                        # 1. XDATA says it's auto/push mode (YAML was source of truth)
                        # 2. Entity name exists
                        # 3. NOT in current YAML configs (was removed from YAML)
                        # 4. NOT marked as 'skip' in YAML (skip entities are intentionally left alone)
                        if (entity_sync_mode in ['auto', 'push'] and
                            entity_name and
                            not is_in_current_configs and
                            not is_skip_in_yaml):
                            orphaned_entities.append((entity, entity_name))
                            log_debug(f"Found orphaned {self.entity_type} entity: '{entity_name}' (XDATA sync_mode: {entity_sync_mode})")

        except Exception as e:
            log_warning(f"Error scanning for orphaned {self.entity_type} entities: {str(e)}")
            return {'deleted_count': 0}

        if not orphaned_entities:
            log_debug(f"No orphaned {self.entity_type} entities found")
            return {'deleted_count': 0}

        # Apply deletion policy
        if self.deletion_policy == 'auto':
            return self._auto_delete_orphaned_entities(orphaned_entities)
        elif self.deletion_policy == 'confirm':
            return self._confirm_delete_orphaned_entities(orphaned_entities)
        else:
            log_warning(f"Unknown deletion policy '{self.deletion_policy}' - skipping orphaned entity cleanup")
            return {'deleted_count': 0}

    def _auto_delete_orphaned_entities(self, orphaned_entities):
        """Automatically delete orphaned entities."""
        try:
            from src.dxf_utils import delete_entities_clean

            deleted_count = delete_entities_clean(orphaned_entities)
            log_info(f"Auto-deleted {deleted_count} orphaned {self.entity_type} entities")

            return {'deleted_count': deleted_count}

        except Exception as e:
            log_error(f"Error auto-deleting orphaned {self.entity_type} entities: {str(e)}")
            return {'deleted_count': 0}

    def _confirm_delete_orphaned_entities(self, orphaned_entities):
        """Confirm before deleting orphaned entities."""
        if not orphaned_entities:
            return {'deleted_count': 0}

        # Show summary of orphaned entities
        log_warning(f"\nFound {len(orphaned_entities)} orphaned {self.entity_type} entities:")
        for entity, entity_name in orphaned_entities:
            log_warning(f"  - '{entity_name}' (exists in DXF but not in YAML)")

        # Ask for confirmation
        response = input(f"\nDelete these {len(orphaned_entities)} orphaned {self.entity_type} entities? (y/N): ").lower().strip()
        # Default to "n" (no) if user just presses Enter - safer for destructive operations
        if not response:
            response = 'n'

        if response == 'y':
            try:
                from src.dxf_utils import delete_entities_clean

                deleted_count = delete_entities_clean(orphaned_entities)
                log_info(f"Confirmed deletion of {deleted_count} orphaned {self.entity_type} entities")

                return {'deleted_count': deleted_count}

            except Exception as e:
                log_error(f"Error deleting confirmed orphaned {self.entity_type} entities: {str(e)}")
                return {'deleted_count': 0}
        else:
            log_info(f"Orphaned {self.entity_type} entity deletion cancelled by user")
            return {'deleted_count': 0}
