from abc import ABC, abstractmethod
from src.utils import log_info, log_warning, log_error, log_debug
from src.sync_hash_utils import (
    detect_entity_changes, resolve_sync_conflict, update_sync_metadata,
    ensure_sync_metadata_complete, clean_entity_config_for_yaml_output
)
from src.dxf_utils import XDATA_APP_ID, attach_custom_data


class SyncManagerBase(ABC):
    """Abstract base class for managing entity synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_settings, script_identifier, entity_type, project_loader=None):
        """
        Initialize the sync manager.

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

        # Validate deletion policy
        valid_deletion_policies = {'auto', 'confirm', 'ignore'}
        if self.deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid {entity_type} deletion policy '{self.deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using 'auto'.")
            self.deletion_policy = 'auto'

        # Validate default layer
        if not isinstance(self.default_layer, str) or not self.default_layer.strip():
            fallback = self._get_fallback_default_layer()
            log_warning(f"Invalid {entity_type} default layer '{self.default_layer}'. Using '{fallback}'.")
            self.default_layer = fallback

        log_debug(f"{self.__class__.__name__} initialized with entity_type={entity_type}, "
                 f"default_sync={self.default_sync}, discovery={self.discovery_enabled}, "
                 f"deletion_policy={self.deletion_policy}")

    def _get_fallback_default_layer(self):
        """Get fallback default layer name for this entity type."""
        fallbacks = {
            'viewport': 'VIEWPORTS',
            'text': 'Plantext',
            'block': 'BLOCKS'
        }
        return fallbacks.get(self.entity_type, 'DEFAULT_LAYER')

    def _resolve_entity_layer(self, config):
        """
        Resolve the layer for an entity using unified layer logic.

        Args:
            config: Entity configuration dictionary

        Returns:
            str: Layer name to use for this entity
        """
        # Check for individual layer override first
        entity_layer = config.get('layer')
        if entity_layer:
            return entity_layer

        # Fall back to global default layer
        return self.default_layer

    def _get_sync_direction(self, config):
        """
        Determine sync direction for an entity config.
        Uses per-entity sync if specified, otherwise falls back to global sync setting.

        Args:
            config: Entity configuration dictionary

        Returns:
            str: Sync direction ('push', 'pull', 'skip', or 'auto')
        """
        entity_name = config.get('name', 'unnamed')

        # Use per-entity sync if specified, otherwise use global default
        if 'sync' in config:
            sync = config['sync']
        else:
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

    def _validate_global_sync(self, sync_value):
        """
        Validate global sync setting.

        Args:
            sync_value: The sync value to validate

        Returns:
            str: Valid sync value ('push', 'pull', or 'skip')
        """
        valid_sync_values = {'push', 'pull', 'skip'}
        if sync_value not in valid_sync_values:
            log_warning(f"Invalid global {self.entity_type}_sync value '{sync_value}'. "
                       f"Valid values are: {', '.join(valid_sync_values)}. Using 'skip'.")
            return 'skip'
        return sync_value

    def process_entities(self, doc, space):
        """
        Main processing method for entity synchronization with discovery and deletion support.

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
            yaml_updated = True  # Metadata changes require YAML update

        # Step 1: Discover unknown entities in AutoCAD if enabled
        discovered_entities = []
        if self.discovery_enabled:
            discovered_entities = self._discover_unknown_entities(doc, space)
            if discovered_entities:
                log_info(f"Discovered {len(discovered_entities)} unknown {self.entity_type}s")

        # Step 2: Process configured entities according to sync direction
        for config in entity_configs:
            try:
                entity_name = config.get('name', 'unnamed')
                sync_direction = self._get_sync_direction(config)

                if sync_direction == 'skip':
                    log_debug(f"Skipping {self.entity_type} '{entity_name}' (sync: skip)")
                    continue

                result = self._process_entity_sync(doc, space, config, sync_direction)
                if result:
                    if result.get('entity'):
                        processed_entities[entity_name] = result['entity']
                    if result.get('yaml_updated'):
                        yaml_updated = True

            except Exception as e:
                log_error(f"Error processing {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
                continue

        # Step 2b: Remove entities marked for deletion by auto sync
        entities_to_delete = [config for config in entity_configs if config.get('_delete_from_yaml')]
        if entities_to_delete:
            config_key = self._get_config_key()
            current_configs = self.project_settings.get(config_key, [])

            # Remove marked entities
            remaining_configs = [
                config for config in current_configs
                if not config.get('_delete_from_yaml')
            ]

            self.project_settings[config_key] = remaining_configs
            yaml_updated = True

            deleted_names = [config.get('name', 'unnamed') for config in entities_to_delete]
            log_info(f"🔄 AUTO: Removed {len(entities_to_delete)} {self.entity_type}(s) from YAML: {', '.join(deleted_names)}")

        # Step 3: Handle discovered entities
        if discovered_entities:
            log_debug(f"🔍 DISCOVERY DEBUG: Processing {len(discovered_entities)} discovered {self.entity_type} entities")
            new_configs = self._process_discovered_entities(discovered_entities)
            log_debug(f"🔍 DISCOVERY DEBUG: Created {len(new_configs)} configs from discovered entities")

            if new_configs:
                # Add discovered entities to configuration
                config_key = self._get_config_key()

                # Log current state
                current_count = len(self.project_settings.get(config_key, []))
                log_debug(f"🔍 DISCOVERY DEBUG: Current {config_key} count: {current_count}")

                if self.project_settings.get(config_key) is None:
                    self.project_settings[config_key] = []

                self.project_settings[config_key].extend(new_configs)
                new_count = len(self.project_settings.get(config_key, []))

                yaml_updated = True
                log_info(f"Added {len(new_configs)} discovered {self.entity_type}s to configuration")
                log_debug(f"🔍 DISCOVERY DEBUG: New {config_key} count: {new_count} (added {new_count - current_count})")
            else:
                log_warning(f"🔍 DISCOVERY DEBUG: No configs created from {len(discovered_entities)} discovered entities!")

        # Step 4: Handle entity deletions according to deletion policy
        deleted_configs = self._handle_entity_deletions(doc, space)
        if deleted_configs:
            yaml_updated = True
            log_info(f"Removed {len(deleted_configs)} deleted {self.entity_type}s from configuration")

        # Step 4b: Handle orphaned DXF entities (exist in DXF but not in YAML) for auto sync
        orphaned_count = self._handle_orphaned_dxf_entities(doc, space)
        if orphaned_count > 0:
            log_info(f"Removed {orphaned_count} orphaned {self.entity_type}s from DXF")

        # Step 5: Write back YAML if any changes were made
        if yaml_updated and self.project_loader:
            log_debug(f"🔍 DISCOVERY DEBUG: Writing YAML for {self.entity_type}s (yaml_updated={yaml_updated})")
            result = self._write_entity_yaml()
            log_debug(f"🔍 DISCOVERY DEBUG: YAML write result: {result}")
        elif yaml_updated and not self.project_loader:
            log_warning(f"🔍 DISCOVERY DEBUG: YAML update needed but no project_loader available!")
        else:
            log_debug(f"🔍 DISCOVERY DEBUG: No YAML write needed (yaml_updated={yaml_updated})")

        return processed_entities

    def _process_entity_sync(self, doc, space, config, sync_direction):
        """
        Process a single entity according to its sync direction.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration
            sync_direction: Sync direction ('push', 'pull', 'skip', or 'auto')

        Returns:
            dict: Result dictionary with 'entity' and 'yaml_updated' keys
        """
        entity_name = config.get('name', 'unnamed')

        if sync_direction == 'auto':
            # Use hash-based auto sync
            return self._process_auto_sync(doc, space, config)
        elif sync_direction == 'push':
            # YAML → AutoCAD: Create/update entity from YAML config
            result = self._sync_push(doc, space, config)
            if result:
                # Update sync metadata after successful push with handle tracking
                content_hash = self._calculate_entity_hash(config)
                entity_handle = str(result.dxf.handle)
                from src.sync_hash_utils import update_sync_metadata
                update_sync_metadata(config, content_hash, 'yaml', entity_handle=entity_handle)
            return {'entity': result, 'yaml_updated': True} if result else None
        elif sync_direction == 'pull':
            # AutoCAD → YAML: Update YAML config from AutoCAD entity
            result = self._sync_pull(doc, space, config)
            if result and result.get('yaml_updated'):
                # Update sync metadata after successful pull with handle tracking
                content_hash = self._calculate_entity_hash(config)
                # Get entity handle from existing entity for pull operations
                existing_entity = self._find_entity_by_name(doc, entity_name)
                entity_handle = str(existing_entity.dxf.handle) if existing_entity else None
                from src.sync_hash_utils import update_sync_metadata
                update_sync_metadata(config, content_hash, 'dxf', entity_handle=entity_handle)
            return result if result else None
        else:
            log_warning(f"Unknown sync direction '{sync_direction}' for {self.entity_type} {entity_name}")
            return None

    def _process_auto_sync(self, doc, space, config):
        """
        Process entity using state-based automatic sync with proper change detection.

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

        # Detect changes using hash comparison, passing self as entity manager
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
                # Only YAML changed - push to DXF
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
                return None

        else:
            # This shouldn't happen (yaml_exists is always True in this context)
            log_error(f"🔄 AUTO: Unexpected state for '{entity_name}' - YAML missing")
            return None

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

    def _process_discovered_entities(self, discovered_entities):
        """
        Process discovered entities and create YAML configurations for them.

        Args:
            discovered_entities: List of discovered entity dictionaries

        Returns:
            list: List of new configuration dictionaries
        """
        new_configs = []

        for discovered in discovered_entities:
            try:
                entity = discovered['entity']
                name = discovered['name']

                # Extract properties and create configuration
                config = self._extract_entity_properties(entity, {'name': name})

                # For discovered entities, only set explicit sync if global default is different from desired behavior
                # Discovered entities logically should pull from AutoCAD since they originated there
                if self.default_sync not in ['pull', 'auto']:
                    config['sync'] = 'pull'

                # Add metadata to the discovered entity
                self._attach_entity_metadata(entity, config)

                new_configs.append(config)

            except Exception as e:
                log_warning(f"Failed to process discovered {self.entity_type} {discovered['name']}: {str(e)}")
                continue

        return new_configs

    def _auto_delete_missing_entities(self, missing_entities):
        """
        Automatically delete missing entities from configuration.

        Args:
            missing_entities: List of entity configurations to remove

        Returns:
            list: List of removed configurations
        """
        log_info(f"Auto-deleting {len(missing_entities)} missing {self.entity_type}s from configuration")

        config_key = self._get_config_key()
        entity_configs = self.project_settings.get(config_key, []) or []
        original_count = len(entity_configs)

        # Remove missing entities from configuration
        for missing_entity in missing_entities:
            entity_name = missing_entity.get('name')
            entity_configs = [e for e in entity_configs if e.get('name') != entity_name]

        # Update the project settings
        self.project_settings[config_key] = entity_configs

        deleted_count = original_count - len(entity_configs)
        log_info(f"Successfully removed {deleted_count} missing {self.entity_type}s from configuration")
        return missing_entities

    def _confirm_delete_missing_entities(self, missing_entities):
        """
        Ask user confirmation before deleting missing entities.

        Args:
            missing_entities: List of entity configurations to remove

        Returns:
            list: List of removed configurations (empty if cancelled)
        """
        entity_names = [e.get('name', 'unnamed') for e in missing_entities]

        log_warning(f"\nFound {len(missing_entities)} {self.entity_type}s in YAML that no longer exist in AutoCAD:")
        for name in entity_names:
            log_warning(f"- {name}")

        # Ask for confirmation
        response = input(f"\nDo you want to remove these {len(missing_entities)} {self.entity_type}s from the YAML configuration? (y/N): ").lower()
        if response == 'y':
            return self._auto_delete_missing_entities(missing_entities)
        else:
            log_info(f"{self.entity_type.title()} deletion cancelled by user")
            return []

    @abstractmethod
    def _discover_unknown_entities(self, doc, space):
        """
        Discover entities in AutoCAD that aren't managed by this script.

        Args:
            doc: DXF document
            space: Model space or paper space

        Returns:
            list: List of discovered entity dictionaries with 'entity', 'name', and optional metadata
        """
        pass

    @abstractmethod
    def _handle_entity_deletions(self, doc, space):
        """
        Handle deletion of entities that exist in YAML but not in AutoCAD.

        IMPORTANT: Only entities in 'pull' mode should be checked for deletion.
        - Pull mode: AutoCAD is source of truth → remove missing entities from YAML
        - Push mode: YAML is source of truth → create missing entities in AutoCAD
        - Skip mode: No synchronization → ignore

        Args:
            doc: DXF document
            space: Model space or paper space

        Returns:
            list: List of deleted entity configurations
        """
        pass

    def _handle_orphaned_dxf_entities(self, doc, space):
        """
        Handle orphaned DXF entities that exist in DXF but are no longer in YAML.
        This handles the reverse deletion case for auto sync mode.

        Args:
            doc: DXF document
            space: Model space or paper space

        Returns:
            int: Number of orphaned entities removed
        """
        if self.deletion_policy == 'ignore':
            return 0

        # Get all currently configured entity names in YAML
        yaml_entity_names = set()
        current_configs = self._get_entity_configs()
        for config in current_configs:
            entity_name = config.get('name')
            if entity_name:
                yaml_entity_names.add(entity_name)

        # Find all managed entities in DXF (entities with our XDATA)
        orphaned_entities = []
        entity_types = self._get_entity_types_for_search()

        for entity in space:
            if entity_types and entity.dxftype() not in entity_types:
                continue

            try:
                # Check if entity has our XDATA (is managed by us)
                xdata = entity.get_xdata(XDATA_APP_ID)
                if not xdata:
                    continue

                # Check if entity was created by THIS sync manager's script_identifier
                # (not by other app facilities like DXFExporter, LegendCreator, etc.)
                entity_script_id = None
                for code, value in xdata:
                    if code == 1000:  # First string in XDATA is always script_identifier
                        entity_script_id = value
                        break

                if entity_script_id != self.script_identifier:
                    continue  # Skip entities created by other parts of the app

                # Extract entity name from XDATA
                entity_name = self._get_entity_name_from_xdata(entity)

                # Check if entity exists in current YAML configuration
                if entity_name not in yaml_entity_names:
                    orphaned_entities.append((entity, entity_name))
                    log_info(f"Found orphaned {self.entity_type} '{entity_name}' in DXF (not in YAML)")

            except Exception as e:
                log_debug(f"Error checking entity for orphaned status: {str(e)}")
                continue

        if not orphaned_entities:
            return 0

        # Handle orphaned entities according to deletion policy
        if self.deletion_policy == 'auto':
            return self._auto_delete_orphaned_entities(orphaned_entities)
        elif self.deletion_policy == 'confirm':
            return self._confirm_delete_orphaned_entities(orphaned_entities)
        else:
            log_warning(f"Unknown deletion policy '{self.deletion_policy}' - skipping orphaned entity deletions")
            return 0

    def _auto_delete_orphaned_entities(self, orphaned_entities):
        """
        Automatically delete orphaned entities from DXF using centralized deletion utilities.

        Args:
            orphaned_entities: List of (entity, entity_name) tuples

        Returns:
            int: Number of entities deleted
        """
        from src.dxf_utils import delete_entities_clean

        # Use centralized deletion function from dxf_utils
        deleted_count = delete_entities_clean(orphaned_entities)

        if deleted_count > 0:
            log_info(f"🗑️  AUTO-DELETED: {deleted_count} orphaned {self.entity_type}s from DXF")

        return deleted_count

    def _confirm_delete_orphaned_entities(self, orphaned_entities):
        """
        Confirm deletion of orphaned entities with user prompt.

        Args:
            orphaned_entities: List of (entity, entity_name) tuples

        Returns:
            int: Number of entities deleted
        """
        if not orphaned_entities:
            return 0

        entity_names = [name for _, name in orphaned_entities]
        log_info(f"⚠️  ORPHANED {self.entity_type.upper()}S FOUND IN DXF:")
        for name in entity_names:
            log_info(f"  - {name}")

        log_info(f"These {self.entity_type}s exist in DXF but are no longer in YAML configuration.")
        log_info(f"Deletion policy is 'confirm' - skipping automatic deletion.")
        log_info(f"To delete: set deletion_policy to 'auto' or remove manually.")

        return 0  # No entities deleted in confirm mode

    @abstractmethod
    def _extract_entity_properties(self, entity, base_config):
        """
        Extract entity properties from AutoCAD entity.

        Args:
            entity: AutoCAD entity object
            base_config: Base configuration with at least 'name'

        Returns:
            dict: Complete entity configuration dictionary
        """
        pass

    @abstractmethod
    def _attach_entity_metadata(self, entity, config):
        """
        Attach custom metadata to an entity to mark it as managed by this script.

        Args:
            entity: AutoCAD entity object
            config: Entity configuration dictionary
        """
        pass

    @abstractmethod
    def _get_entity_configs(self):
        """
        Get entity configurations from project settings.

        Returns:
            list: List of entity configuration dictionaries
        """
        pass

    @abstractmethod
    def _sync_push(self, doc, space, config):
        """
        Create or update entity in AutoCAD from YAML configuration.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration dictionary

        Returns:
            Entity object if successful, None otherwise
        """
        pass

    @abstractmethod
    def _sync_pull(self, doc, space, config):
        """
        Extract entity properties from AutoCAD and update YAML configuration.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration dictionary

        Returns:
            dict: Result with 'entity' and 'yaml_updated' keys, or None if failed
        """
        pass

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
            'discover_untracked': f'{prefix}discovery',
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

    def _calculate_entity_hash(self, config):
        """
        Calculate content hash for entity configuration.
        Centralized implementation that works for all entity types.

        Args:
            config: Entity configuration dictionary

        Returns:
            str: Content hash for the configuration
        """
        try:
            from src.sync_hash_utils import calculate_entity_content_hash
            return calculate_entity_content_hash(config, self.entity_type)
        except Exception as e:
            log_warning(f"Error calculating hash for {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
            return "error_hash"

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

            # Use unified XDATA function with content hash and handle
            from src.dxf_utils import attach_custom_data
            attach_custom_data(
                entity,
                self.script_identifier,
                entity_name=entity_name,
                entity_type=self.entity_type.upper(),
                content_hash=content_hash,
                entity_handle=entity_handle
            )

            # Store handle in sync metadata for handle-based tracking
            if '_sync' not in config:
                config['_sync'] = {}
            config['_sync']['dxf_handle'] = entity_handle

            log_debug(f"Attached metadata to {self.entity_type} '{entity_name}' with handle {entity_handle}")

        except Exception as e:
            log_warning(f"Failed to attach metadata to {self.entity_type}: {str(e)}")

    def _centralize_target_layer_cleaning(self, doc, configs_to_process):
        """
        Centralized target layer cleaning for entities.
        Can be overridden by subclasses for entity-specific space handling.

        Args:
            doc: DXF document
            configs_to_process: List of configurations to process

        Returns:
            set: Set of layer names that were cleaned
        """
        target_layers = set()
        for config in configs_to_process:
            sync_direction = self._get_sync_direction(config)
            if sync_direction == 'push':
                layer_name = self._resolve_entity_layer(config)
                target_layers.add(layer_name)

        # Remove existing entities from layers that will be updated
        # Default: clean from both model and paper space
        for layer_name in target_layers:
            spaces = [doc.modelspace(), doc.paperspace()]
            for space in spaces:
                log_debug(f"Cleaning {self.entity_type} entities from layer: {layer_name} in {space}")
                from src.dxf_utils import remove_entities_by_layer
                remove_entities_by_layer(space, layer_name, self.script_identifier)

        return target_layers

    def _should_write_explicit_sync(self, entity_sync, global_sync):
        """
        Determine if sync should be written explicitly to entity config.
        Only write if it differs from the global default.

        Args:
            entity_sync: The entity's sync setting
            global_sync: The global sync setting

        Returns:
            bool: True if should write explicit sync, False otherwise
        """
        return entity_sync != global_sync

    def _find_entity_by_name(self, doc, entity_name):
        """
        Find an entity by name. Default implementation - should be overridden by subclasses.

        Args:
            doc: DXF document
            entity_name: Name of entity to find

        Returns:
            Entity object if found, None otherwise
        """
        # This is a placeholder - each entity manager should implement their own
        log_debug(f"Default _find_entity_by_name called for '{entity_name}' - should be overridden")
        return None

    @abstractmethod
    def _get_entity_types(self):
        """
        Get the DXF entity types that this manager handles.

        Returns:
            List[str]: List of DXF entity types (e.g., ['TEXT', 'MTEXT'], ['VIEWPORT'], ['INSERT'])
        """
        pass

    @abstractmethod
    def _get_discovery_spaces(self, doc):
        """
        Get the DXF spaces where this entity type should be discovered.

        Args:
            doc: DXF document

        Returns:
            List: List of DXF spaces to search for entities
        """
        pass

    @abstractmethod
    def _generate_entity_name(self, entity, counter):
        """
        Generate a name for a discovered entity.

        Args:
            entity: DXF entity object
            counter: Sequential counter for naming

        Returns:
            str: Generated name for the entity
        """
        pass

    @abstractmethod
    def _should_skip_entity(self, entity):
        """
        Check if a specific entity should be skipped during discovery.

        Args:
            entity: DXF entity object

        Returns:
            bool: True if entity should be skipped, False otherwise
        """
        pass

    def _get_config_key(self):
        """
        Get the configuration key for this entity type in project_settings.
        Uses consistent simple pluralization pattern.

        Returns:
            str: Configuration key for project_settings
        """
        return f'{self.entity_type}s'

    def _should_discover_from_layer(self, entity):
        """
        Check if an entity should be discovered based on its layer.

        Args:
            entity: DXF entity object

        Returns:
            bool: True if entity should be discovered, False otherwise
        """
        # If discovery_layers is 'all', discover from all layers
        if self.discovery_layers == 'all':
            return True

        # Get entity layer
        try:
            entity_layer = getattr(entity.dxf, 'layer', '0')  # Default to layer '0'
        except:
            entity_layer = '0'

        # Check if entity layer is in the discovery layers list
        return entity_layer in self.discovery_layers

    def _has_stale_xdata(self, entity):
        """
        Check if entity has stale XDATA (handle mismatch indicates duplicate).

        Args:
            entity: DXF entity to check

        Returns:
            bool: True if entity has stale XDATA (is a duplicate), False otherwise
        """
        if not entity:
            return False

        try:
            # Check if entity has our XDATA
            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                return False

            # Extract stored handle from XDATA
            from src.dxf_utils import extract_handle_from_xdata
            stored_handle = extract_handle_from_xdata(entity)
            actual_handle = str(entity.dxf.handle)

            # Stale XDATA = handle mismatch
            return stored_handle != actual_handle

        except Exception:
            return True  # Corrupted XDATA = treat as stale

    def _find_all_entities_by_xdata_name(self, space, entity_name, entity_types):
        """
        Find ALL entities with matching XDATA name (not just first match).

        Args:
            space: DXF space to search
            entity_name: Name to search for
            entity_types: List of entity types to search

        Returns:
            list: All entities with matching name
        """
        matching_entities = []

        for entity in space:
            if entity_types and entity.dxftype() not in entity_types:
                continue

            try:
                xdata = entity.get_xdata(XDATA_APP_ID)
                if xdata:
                    # Extract entity name from XDATA
                    in_entity_section = False
                    found_name = None

                    for code, value in xdata:
                        if code == 1000 and value == "entity_name":
                            in_entity_section = True
                        elif in_entity_section and code == 1000:
                            found_name = value
                            break

                    if found_name == entity_name:
                        matching_entities.append(entity)
            except Exception:
                continue

        return matching_entities

    def _find_original_and_duplicates(self, space, entity_name, entity_types):
        """
        Find the original tracked entity and any duplicates by analyzing XDATA handles.

        Args:
            space: DXF space to search
            entity_name: Name to search for
            entity_types: List of entity types to search

        Returns:
            tuple: (original_entity, duplicate_entities_list)
        """
        # Find all entities with this name
        all_entities = self._find_all_entities_by_xdata_name(space, entity_name, entity_types)

        original_entity = None
        duplicate_entities = []

        for entity in all_entities:
            if self._has_stale_xdata(entity):
                duplicate_entities.append(entity)  # Stale XDATA = duplicate
            else:
                original_entity = entity  # Valid XDATA = original

        return original_entity, duplicate_entities

    def _generate_unique_entity_name(self, base_name, copy_number):
        """
        Generate unique name for discovered duplicate.

        Args:
            base_name: Original entity name
            copy_number: Copy number (1, 2, 3, etc.)

        Returns:
            str: Unique entity name
        """
        import time

        # Try simple pattern first
        candidate_name = f"{base_name}_copy{copy_number}"

        # Check if name already exists in current configs
        existing_names = {config.get('name') for config in self._get_entity_configs()}

        # If conflict, add timestamp
        if candidate_name in existing_names:
            timestamp = int(time.time()) % 10000  # Last 4 digits
            candidate_name = f"{base_name}_copy{copy_number}_{timestamp}"

        return candidate_name

    def _discover_duplicates_as_new_entities(self, duplicate_entities, original_config):
        """
        Convert duplicate entities into new managed entities with unique names.

        Args:
            duplicate_entities: List of duplicate entities to discover
            original_config: Configuration of the original entity

        Returns:
            list: List of new entity configurations for discovered duplicates
        """
        discovered_configs = []

        for i, duplicate_entity in enumerate(duplicate_entities, 1):
            try:
                # Generate unique name
                original_name = original_config.get('name', 'unnamed')
                new_name = self._generate_unique_entity_name(original_name, i)

                # Clean stale XDATA
                duplicate_entity.discard_xdata(XDATA_APP_ID)

                # Extract properties from duplicate entity
                new_config = self._extract_entity_properties_for_discovery(duplicate_entity)
                new_config['name'] = new_name

                # Inherit key settings from original
                for key in ['layer', 'paperspace']:
                    if key in original_config:
                        new_config[key] = original_config[key]

                # Add tracking metadata with new handle
                content_hash = self._calculate_entity_hash(new_config)
                self._attach_entity_metadata(duplicate_entity, new_config)

                # Add sync metadata
                import time
                new_config['_sync'] = {
                    'content_hash': content_hash,
                    'dxf_handle': str(duplicate_entity.dxf.handle),
                    'last_sync_time': int(time.time()),
                    'sync_source': 'auto_discovery',
                    'discovered_from': original_name
                }

                discovered_configs.append(new_config)
                log_info(f"🔍 AUTO-DISCOVERED: Duplicate of '{original_name}' as new entity '{new_name}'")

            except Exception as e:
                log_warning(f"Failed to discover duplicate entity: {str(e)}")
                continue

        return discovered_configs

    def _extract_entity_properties_for_discovery(self, entity):
        """
        Extract entity properties for auto-discovery.
        This method should be overridden by subclasses for entity-specific extraction.

        Args:
            entity: DXF entity to extract properties from

        Returns:
            dict: Entity configuration extracted from DXF
        """
        # This is a fallback implementation
        # Subclasses should override this for proper entity-specific extraction
        log_warning(f"Using fallback property extraction for {entity.dxftype()} entity discovery")
        return {
            'name': 'discovered_entity',
            'layer': getattr(entity.dxf, 'layer', 'DEFAULT'),
            'paperspace': False
        }

    def _add_discovered_entities_to_yaml(self, discovered_configs):
        """
        Add newly discovered entities to YAML configuration.

        Args:
            discovered_configs: List of discovered entity configurations
        """
        if not discovered_configs:
            return

        # Add to current project settings
        config_key = self._get_config_key()
        current_configs = self._get_entity_configs()
        current_configs.extend(discovered_configs)

        # Update project settings
        self.project_settings[config_key] = current_configs

        log_info(f"📝 Added {len(discovered_configs)} discovered entities to {config_key} configuration")

    def _find_entity_with_duplicate_handling(self, doc, config):
        """
        Find entity using handle-first search with duplicate detection and handling.

        Args:
            doc: DXF document
            config: Entity configuration

        Returns:
            tuple: (original_entity, duplicate_entities_list)
        """
        entity_name = config.get('name', 'unnamed')

        # STEP 1: Try handle-first search for the original entity
        original_entity = self._find_entity_by_handle_first(doc, config)

        # STEP 2: Look for duplicates using name-based search
        duplicate_entities = []

        # Only search for duplicates if we found an original entity
        if original_entity:
            paperspace = config.get('paperspace', False)
            target_space = doc.paperspace() if paperspace else doc.modelspace()
            entity_types = self._get_entity_types_for_search()

            # Find all entities with this name
            all_entities = self._find_all_entities_by_xdata_name(target_space, entity_name, entity_types)

            # Separate duplicates from original
            for entity in all_entities:
                if entity != original_entity and self._has_stale_xdata(entity):
                    duplicate_entities.append(entity)

        return original_entity, duplicate_entities

    def _get_entity_types_for_search(self):
        """
        Get the DXF entity types that this manager searches for.
        Should be overridden by subclasses.

        Returns:
            list: List of DXF entity type strings
        """
        # Default implementation - subclasses should override
        return []

    def _find_entity_by_handle_first(self, doc, config):
        """
        Find entity using handle-first logic with name fallback.

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

        # Determine target space
        paperspace = config.get('paperspace', False)
        target_space = doc.paperspace() if paperspace else doc.modelspace()

        # STEP 1: Try handle-first search (most reliable)
        if stored_handle:
            try:
                entity = target_space.get_entity_by_handle(stored_handle)
                if entity:
                    log_debug(f"Found entity '{entity_name}' by handle: {stored_handle}")

                    # Update entity name in XDATA if it changed
                    self._update_entity_name_in_xdata(entity, entity_name)

                    return entity
            except Exception as e:
                log_debug(f"Handle search failed for '{entity_name}' (handle: {stored_handle}): {str(e)}")

        # STEP 2: Fallback to name-based search using existing method
        log_debug(f"Falling back to name search for entity '{entity_name}'")
        return self._find_entity_by_name(doc, entity_name)

    def _update_entity_name_in_xdata(self, entity, new_name):
        """
        Update the entity name in XDATA if it has changed.

        Args:
            entity: DXF entity
            new_name: New entity name
        """
        try:
            # Get current name from XDATA
            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                return

            # Extract current name
            current_name = None
            in_entity_section = False
            for code, value in xdata:
                if code == 1000 and value == "entity_name":
                    in_entity_section = True
                elif in_entity_section and code == 1000:
                    current_name = value
                    break

            # Update name if it changed
            if current_name and current_name != new_name:
                log_debug(f"Updating entity name in XDATA: '{current_name}' → '{new_name}'")

                # Re-attach metadata with new name
                from src.dxf_utils import attach_custom_data

                # Get existing metadata
                content_hash = None
                entity_handle = str(entity.dxf.handle)

                # Extract content hash from XDATA
                for code, value in xdata:
                    if code == 1000 and value.startswith('hash:'):
                        content_hash = value[5:]  # Remove 'hash:' prefix
                        break

                # Re-attach with updated name
                attach_custom_data(
                    entity,
                    self.script_identifier,
                    entity_name=new_name,
                    entity_type=self.entity_type.upper(),
                    content_hash=content_hash,
                    entity_handle=entity_handle
                )

        except Exception as e:
            log_warning(f"Failed to update entity name in XDATA: {str(e)}")

    def _get_entity_name_from_xdata(self, entity):
        """
        Extract entity name from XDATA.

        Args:
            entity: DXF entity with XDATA

        Returns:
            str: Entity name or 'unnamed' if not found
        """
        try:
            from src.dxf_utils import XDATA_APP_ID, XDATA_ENTITY_NAME_KEY

            xdata = entity.get_xdata(XDATA_APP_ID)
            if not xdata:
                return 'unnamed'

            # Extract entity name
            in_entity_section = False
            for code, value in xdata:
                if code == 1000 and value == XDATA_ENTITY_NAME_KEY:  # Use correct constant
                    in_entity_section = True
                elif in_entity_section and code == 1000:
                    return value

            return 'unnamed'
        except Exception:
            return 'unnamed'

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
            return True  # Assume valid to avoid breaking existing functionality

    def _discover_unknown_entities(self, doc, space):
        """
        Centralized discovery logic for unmanaged entities.

        This method provides consistent discovery behavior across all entity types,
        with entity-specific behavior delegated to abstract methods.

        Args:
            doc: DXF document
            space: DXF space (ignored, uses _get_discovery_spaces instead)

        Returns:
            List[dict]: List of discovered entity configurations
        """
        discovered = []
        entity_counter = 1

        # Get configured entity names to avoid duplicates
        try:
            configured_names = {config.get('name') for config in self._get_entity_configs()}
        except:
            configured_names = set()

        # Log discovery configuration
        if self.discovery_layers == 'all':
            log_debug(f"Discovery configured for ALL layers")
        else:
            log_debug(f"Discovery configured for specific layers: {self.discovery_layers}")

        # Search in all relevant spaces for this entity type
        for search_space in self._get_discovery_spaces(doc):
            log_debug(f"Searching for unknown {self.entity_type} entities in {search_space}")

            for entity in search_space:
                if entity.dxftype() in self._get_entity_types():
                    try:
                        # Check if entity should be skipped (e.g., system viewports)
                        if self._should_skip_entity(entity):
                            continue

                        # Check if entity layer matches discovery filter
                        if not self._should_discover_from_layer(entity):
                            entity_layer = getattr(entity.dxf, 'layer', '0')
                            log_debug(f"Skipping {entity.dxftype()} on layer '{entity_layer}' (not in discovery layers)")
                            continue

                        # Check if this entity has our script metadata and validate handle
                        has_our_metadata = False
                        has_valid_metadata = False
                        try:
                            xdata = entity.get_xdata(XDATA_APP_ID)
                            if xdata:
                                for code, value in xdata:
                                    if code == 1000 and value == self.script_identifier:
                                        has_our_metadata = True
                                        break
                        except:
                            has_our_metadata = False

                        # Skip entities that are already managed by our script
                        if has_our_metadata:
                            continue

                        # Generate a name for this unmanaged entity
                        entity_name = self._generate_entity_name(entity, entity_counter)

                        # Ensure unique name by incrementing counter if needed
                        while entity_name in configured_names:
                            entity_counter += 1
                            entity_name = self._generate_entity_name(entity, entity_counter)

                        log_info(f"Discovered unmanaged {self.entity_type} entity, assigned name: {entity_name}")

                        # Attach XDATA to mark this entity as managed
                        attach_custom_data(entity, self.script_identifier, entity_name, self.entity_type.upper())

                        # Add to discovered list
                        discovered.append({
                            'entity': entity,
                            'name': entity_name,
                            'space': search_space
                        })

                        configured_names.add(entity_name)  # Prevent duplicate names
                        entity_counter += 1

                    except Exception as e:
                        log_error(f"Error checking {self.entity_type} entity metadata: {str(e)}")
                        continue

        log_info(f"Discovery completed: Found {len(discovered)} unknown {self.entity_type} entities")
        return discovered
