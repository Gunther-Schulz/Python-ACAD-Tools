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
    - skip: No processing
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



        # Step 6: Write back YAML changes if needed
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

        return entities_by_mode

    def _process_push_mode_entities(self, doc, space, configs):
        """
        Process push mode entities with bulk layer replacement.
        This is the traditional behavior for generated content.
        """
        if not configs:
            return {'entities': {}, 'yaml_updated': False}

        log_debug(f"Processing {len(configs)} push mode {self.entity_type} entities")

        # Step 1: Bulk clean target layers (traditional approach)
        self._bulk_clean_target_layers(doc, configs)

        # Step 2: Create all entities from YAML configs
        processed_entities = {}
        yaml_updated = False

        for config in configs:
            try:
                entity_name = config.get('name', 'unnamed')
                result = self._sync_push(doc, space, config)

                if result:
                    processed_entities[entity_name] = result
                    # Update sync metadata for push mode
                    content_hash = self._calculate_entity_hash(config)
                    entity_handle = str(result.dxf.handle)
                    update_sync_metadata(config, content_hash, 'yaml', entity_handle=entity_handle)
                    yaml_updated = True

            except Exception as e:
                log_error(f"Error processing push mode {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
                continue

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
        """
        target_layers = set()
        for config in configs:
            layer_name = self._resolve_entity_layer(config)
            target_layers.add(layer_name)

        # Clean layers using traditional approach
        for layer_name in target_layers:
            log_debug(f"Bulk cleaning {self.entity_type} entities from layer: {layer_name}")
            self._clean_layer_entities(doc, layer_name)

    def _clean_layer_entities(self, doc, layer_name):
        """
        Clean entities from a specific layer.
        Can be overridden by subclasses for space-specific handling.
        """
        # Default: clean from both model and paper space
        spaces = [doc.modelspace(), doc.paperspace()]
        for space in spaces:
            from src.dxf_utils import remove_entities_by_layer
            remove_entities_by_layer(space, layer_name, self.script_identifier)

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

    def _get_entity_name_from_xdata(self, entity):
        """Extract entity name from XDATA."""
        try:
            from src.dxf_utils import XDATA_ENTITY_NAME_KEY
            xdata = entity.get_xdata(XDATA_APP_ID)
            if xdata:
                in_entity_section = False
                for code, value in xdata:
                    if code == 1000 and value == XDATA_ENTITY_NAME_KEY:
                        in_entity_section = True
                    elif in_entity_section and code == 1000:
                        return value  # This is the entity name
            return None
        except Exception:
            return None

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
                    # Really not found anywhere - NOW we can assume deletion
                    log_warning(f"🗑️  Entity '{entity_name}' not found by handle OR name - assuming user deletion")
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
                log_debug(f"🔄 AUTO: '{entity_name}' unchanged - maintaining current state")
                return {'entity': existing_entity, 'yaml_updated': False}

        else:
            # This shouldn't happen (yaml_exists is always True in this context)
            log_error(f"🔄 AUTO: Unexpected state for '{entity_name}' - YAML missing")
            return None

    def _handle_discovery(self, doc, space):
        """Handle entity discovery with proper implementation."""

        if not self._is_discovery_enabled():
            log_info(f"🔍 DEBUG: Discovery not enabled for {self.entity_type}")
            return {'yaml_updated': False}

        log_info(f"🔍 DEBUG: Running discovery for {self.entity_type} entities on layers: {self.discovery_layers}")

        # Discover untracked entities
        discovered_entities = self._discover_unknown_entities(doc, space)
        log_info(f"🔍 DEBUG: Found {len(discovered_entities)} untracked entities")

        if not discovered_entities:
            log_info(f"🔍 DEBUG: No untracked {self.entity_type} entities found")
            return {'yaml_updated': False}

        # Add discovered entities to configuration
        config_key = self._get_config_key()
        entity_configs = self.project_settings.get(config_key, [])
        log_info(f"🔍 DEBUG: Current config has {len(entity_configs)} existing entities")

        yaml_updated = False
        for discovery in discovered_entities:
            entity = discovery['entity']
            entity_name = discovery['name']

            log_info(f"🔍 DEBUG: Processing discovered entity '{entity_name}' (handle: {entity.dxf.handle})")

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
            log_info(f"🔍 DEBUG: Updated project settings with {len(entity_configs)} total entities")

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
        log_info(f"🔍 DEBUG: _discover_unknown_entities called for {self.entity_type} in {space}")
        discovered = []

        # Get entity types from child class implementation
        try:
            entity_types = self._get_entity_types()
            log_info(f"🔍 DEBUG: Entity types: {entity_types}")
        except (NotImplementedError, AttributeError):
            log_warning(f"Child class doesn't implement _get_entity_types() - skipping discovery")
            return discovered

        # Build query string for all entity types
        query_string = ' '.join(entity_types)
        log_info(f"🔍 DEBUG: Query string: '{query_string}'")

        # Search for entities in the current space
        all_entities = list(space.query(query_string))
        log_info(f"🔍 DEBUG: Found {len(all_entities)} entities of matching types")

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
                log_info(f"🔍 DEBUG: Entity {entity.dxf.handle} is properly tracked, skipping")
                continue  # Properly tracked, skip

            log_info(f"🔍 DEBUG: Entity {entity.dxf.handle} on layer {entity_layer} is untracked!")

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
                entity = target_space.get_entity_by_handle(entity_handle)

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
