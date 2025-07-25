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
        self.default_sync = project_settings.get(sync_key, 'skip')

        # Extract generalized discovery and deletion settings
        discovery_key = f'{entity_type}_discovery'
        deletion_key = f'{entity_type}_deletion_policy'

        self.discovery_enabled = project_settings.get(discovery_key, False)
        self.deletion_policy = project_settings.get(deletion_key, 'auto')

        # Extract discovery layers setting
        discovery_layers_key = f'{entity_type}_discover_untracked_layers'
        self.discovery_layers = project_settings.get(discovery_layers_key, 'all')

        # Extract default layer setting for unified layer handling
        default_layer_key = f'{entity_type}_default_layer'
        self.default_layer = project_settings.get(default_layer_key, self._get_fallback_default_layer())

        # Validate settings
        self._validate_settings()

    def _validate_settings(self):
        """Validate sync processor settings."""
        # Validate deletion policy
        valid_deletion_policies = {'auto', 'confirm', 'ignore'}
        if self.deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid {self.entity_type} deletion policy '{self.deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using 'auto'.")
            self.deletion_policy = 'auto'

        # Validate default sync direction
        valid_sync_values = {'push', 'pull', 'skip', 'auto'}
        if self.default_sync not in valid_sync_values:
            log_warning(f"Invalid global {self.entity_type}_sync value '{self.default_sync}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using 'skip'.")
            self.default_sync = 'skip'

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

        # Step 5: Handle discovery and deletion if enabled
        if self.discovery_enabled:
            discovery_results = self._handle_discovery(doc, space)
            if discovery_results.get('yaml_updated'):
                yaml_updated = True

        # Step 6: Write back YAML changes if needed
        if yaml_updated and self.project_loader:
            self._write_entity_yaml()

        log_debug(f"Processed {len(processed_entities)} {self.entity_type} entities")
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

                # Find existing entity
                existing_entity, duplicate_entities = self._find_entity_with_duplicate_handling(doc, config)

                # Handle duplicates if any
                if duplicate_entities:
                    discovered_configs = self._discover_duplicates_as_new_entities(duplicate_entities, config)
                    if discovered_configs:
                        self._add_discovered_entities_to_yaml(discovered_configs)
                        yaml_updated = True

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

    # Default implementations for optional methods
    def _find_entity_with_duplicate_handling(self, doc, config):
        """Find entity with duplicate detection. Default implementation."""
        entity = self._find_entity_by_name(doc, config.get('name', 'unnamed'))
        return entity, []

    def _discover_duplicates_as_new_entities(self, duplicate_entities, config):
        """Discover duplicates as new entities. Default implementation."""
        return []

    def _add_discovered_entities_to_yaml(self, discovered_configs):
        """Add discovered entities to YAML. Default implementation."""
        pass

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

        # Find existing DXF entity and handle duplicates
        existing_entity, duplicate_entities = self._find_entity_with_duplicate_handling(doc, config)

        # Handle discovered duplicates if any
        if duplicate_entities:
            discovered_configs = self._discover_duplicates_as_new_entities(duplicate_entities, config)
            if discovered_configs:
                self._add_discovered_entities_to_yaml(discovered_configs)

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
                # Entity was tracked before but now missing from DXF
                # User likely deleted it - remove from YAML to maintain sync integrity
                log_info(f"🔄 AUTO: Entity '{entity_name}' was tracked but missing from DXF - removing from YAML (user deleted)")
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
        """Handle entity discovery. Default implementation."""
        return {'yaml_updated': False}

    def _write_entity_yaml(self):
        """Write entity configurations back to YAML. Default implementation."""
        if self.project_loader:
            log_debug(f"Writing {self.entity_type} configurations back to YAML")

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

    def _get_target_space(self, doc, config):
        """
        Get the target space (model or paper) for an entity.

        Args:
            doc: DXF document
            config: Entity configuration dictionary

        Returns:
            Space object (doc.modelspace() or doc.paperspace())
        """
        return doc.paperspace() if config.get('paperspace', False) else doc.modelspace()

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
        Attach custom metadata to an entity to mark it as managed by this script.
        Centralized implementation that works for all entity types.

        Args:
            entity: DXF entity object
            config: Entity configuration dictionary
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
            if '_sync' not in config:
                config['_sync'] = {}
            config['_sync']['dxf_handle'] = entity_handle

            log_debug(f"Attached metadata to {self.entity_type} '{entity_name}' with handle {entity_handle}")

        except Exception as e:
            log_warning(f"Failed to attach metadata to {self.entity_type}: {str(e)}")

    def _validate_entity_handle(self, entity, entity_name):
        """
        Validate that an entity's actual handle matches its stored XDATA handle.
        If handles don't match (copied entity), clean the stale XDATA.

        Args:
            entity: DXF entity to validate
            entity_name: Name of the entity for logging

        Returns:
            bool: True if entity is valid/cleaned, False if entity should be treated as missing
        """
        if not entity:
            return False

        try:
            # Check if entity has our XDATA
            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                # No XDATA - entity is unmanaged, treat as missing for auto sync
                return False

            # Extract stored handle from XDATA
            from src.dxf_utils import extract_handle_from_xdata
            stored_handle = extract_handle_from_xdata(entity)
            actual_handle = str(entity.dxf.handle)

            if stored_handle == actual_handle:
                # Valid handle - entity is properly managed
                return True
            else:
                # Handle mismatch - this is a copied entity with stale XDATA
                log_info(f"Auto sync detected copied {self.entity_type} '{entity_name}' with stale XDATA: "
                        f"stored_handle={stored_handle}, actual_handle={actual_handle}")

                # Clean stale XDATA to prevent confusion
                try:
                    entity.discard_xdata(XDATA_APP_ID)
                    log_debug(f"Cleaned stale XDATA from copied {self.entity_type} entity '{entity_name}'")
                except Exception as e:
                    log_warning(f"Failed to clean stale XDATA from '{entity_name}': {str(e)}")

                # Treat as missing entity (will trigger push to recreate proper tracking)
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
