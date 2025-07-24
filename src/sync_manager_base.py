from abc import ABC, abstractmethod
from src.utils import log_info, log_warning, log_error, log_debug
from src.sync_hash_utils import (
    detect_entity_changes, resolve_sync_conflict, update_sync_metadata,
    ensure_sync_metadata_complete
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

        # Validate deletion policy
        valid_deletion_policies = {'auto', 'confirm', 'ignore'}
        if self.deletion_policy not in valid_deletion_policies:
            log_warning(f"Invalid {entity_type}_deletion_policy '{self.deletion_policy}'. "
                       f"Valid values are: {', '.join(valid_deletion_policies)}. Using 'auto'.")
            self.deletion_policy = 'auto'

        log_debug(f"{self.__class__.__name__} initialized with entity_type={entity_type}, "
                 f"default_sync={self.default_sync}, discovery={self.discovery_enabled}, "
                 f"deletion_policy={self.deletion_policy}")

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

        # Step 3: Handle discovered entities
        if discovered_entities:
            new_configs = self._process_discovered_entities(discovered_entities)
            if new_configs:
                # Add discovered entities to configuration
                config_key = f'{self.entity_type}s'  # e.g., 'viewports', 'texts'
                if self.project_settings.get(config_key) is None:
                    self.project_settings[config_key] = []
                self.project_settings[config_key].extend(new_configs)
                yaml_updated = True
                log_info(f"Added {len(new_configs)} discovered {self.entity_type}s to configuration")

        # Step 4: Handle entity deletions according to deletion policy
        deleted_configs = self._handle_entity_deletions(doc, space)
        if deleted_configs:
            yaml_updated = True
            log_info(f"Removed {len(deleted_configs)} deleted {self.entity_type}s from configuration")

        # Step 5: Write back YAML if any changes were made
        if yaml_updated and self.project_loader:
            self._write_entity_yaml()

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
                # Update sync metadata after successful push
                content_hash = self._calculate_entity_hash(config)
                update_sync_metadata(config, content_hash, 'yaml')
            return {'entity': result, 'yaml_updated': True} if result else None
        elif sync_direction == 'pull':
            # AutoCAD → YAML: Update YAML config from AutoCAD entity
            result = self._sync_pull(doc, space, config)
            if result and result.get('yaml_updated'):
                # Update sync metadata after successful pull
                content_hash = self._calculate_entity_hash(config)
                update_sync_metadata(config, content_hash, 'dxf')
            return result if result else None
        else:
            log_warning(f"Unknown sync direction '{sync_direction}' for {self.entity_type} {entity_name}")
            return None

    def _process_auto_sync(self, doc, space, config):
        """
        Process entity using automatic hash-based sync direction detection.

        Args:
            doc: DXF document
            space: Model space or paper space
            config: Entity configuration

        Returns:
            dict: Result dictionary with 'entity' and 'yaml_updated' keys
        """
        entity_name = config.get('name', 'unnamed')

        # Find existing DXF entity
        existing_entity = self._find_entity_by_name(doc, entity_name)

        # Detect changes using hash comparison, passing self as entity manager
        changes = detect_entity_changes(config, existing_entity, self.entity_type, self)

        log_debug(f"Auto sync analysis for '{entity_name}': "
                 f"YAML changed: {changes['yaml_changed']}, "
                 f"DXF changed: {changes['dxf_changed']}")

        # Handle different change scenarios
        if not changes['yaml_changed'] and not changes['dxf_changed']:
            # No changes detected
            log_debug(f"No changes detected for {self.entity_type} '{entity_name}', skipping sync")
            return None

        elif changes['yaml_changed'] and not changes['dxf_changed']:
            # Only YAML changed - push to DXF
            log_debug(f"YAML changed for '{entity_name}', pushing to DXF")
            result = self._sync_push(doc, space, config)
            if result:
                update_sync_metadata(config, changes['current_yaml_hash'], 'yaml')
            return {'entity': result, 'yaml_updated': True} if result else None

        elif not changes['yaml_changed'] and changes['dxf_changed']:
            # DXF changed - check if missing or modified
            if changes['current_dxf_hash'] is None:
                # DXF entity missing - push YAML to recreate it
                log_debug(f"DXF entity '{entity_name}' missing, pushing from YAML to recreate")
                result = self._sync_push(doc, space, config)
                if result:
                    update_sync_metadata(config, changes['current_yaml_hash'], 'yaml')
                return {'entity': result, 'yaml_updated': True} if result else None
            else:
                # DXF entity modified - pull from DXF
                log_debug(f"DXF changed for '{entity_name}', pulling to YAML")
                result = self._sync_pull(doc, space, config)
                if result and result.get('yaml_updated'):
                    update_sync_metadata(config, changes['current_dxf_hash'], 'dxf')
                return result if result else None

        elif changes['has_conflict']:
            # Both sides changed - resolve conflict
            log_info(f"Conflict detected for {self.entity_type} '{entity_name}' - both YAML and DXF changed")

            resolution = resolve_sync_conflict(entity_name, config, existing_entity, self.project_settings)

            if resolution == 'yaml_wins':
                log_info(f"Resolving conflict for '{entity_name}': YAML wins")
                result = self._sync_push(doc, space, config)
                if result:
                    update_sync_metadata(config, changes['current_yaml_hash'], 'yaml')
                return {'entity': result, 'yaml_updated': True} if result else None

            elif resolution == 'dxf_wins':
                log_info(f"Resolving conflict for '{entity_name}': DXF wins")
                result = self._sync_pull(doc, space, config)
                if result and result.get('yaml_updated'):
                    update_sync_metadata(config, changes['current_dxf_hash'], 'dxf')
                return result if result else None

            else:  # resolution == 'skip'
                log_info(f"Skipping conflicted entity '{entity_name}' per user/policy choice")
                return None

        return None

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

        config_key = f'{self.entity_type}s'  # e.g., 'viewports', 'texts'
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

    @abstractmethod
    def _write_entity_yaml(self):
        """
        Write updated entity configuration back to YAML file.
        Should include both entity configs and global settings.

        Returns:
            bool: True if successful, False otherwise
        """
        pass

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
    def _calculate_entity_hash(self, config):
        """
        Calculate content hash for an entity configuration.

        Args:
            config: Entity configuration dictionary

        Returns:
            str: Content hash for the entity
        """
        pass

    # Centralized XDATA and Discovery Methods
    # =======================================

    def _get_entity_name_from_xdata(self, entity):
        """
        Extract entity name from XDATA attached to DXF entity.

        This method is centralized to ensure consistent XDATA parsing across all entity types.

        Args:
            entity: DXF entity object

        Returns:
            str: Entity name if found, "unknown" if not found
        """
        try:
            xdata = entity.get_xdata(XDATA_APP_ID)
            if xdata:
                found_name_key = False
                for code, value in xdata:
                    if code == 1000 and value == "ENTITY_NAME":
                        found_name_key = True
                    elif found_name_key and code == 1000:
                        return value
        except Exception:
            pass
        return "unknown"

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

        # Search in all relevant spaces for this entity type
        for search_space in self._get_discovery_spaces(doc):
            log_debug(f"Searching for unknown {self.entity_type} entities in {search_space}")

            for entity in search_space:
                if entity.dxftype() in self._get_entity_types():
                    try:
                        # Check if entity should be skipped (e.g., system viewports)
                        if self._should_skip_entity(entity):
                            continue

                        # Check if this entity has our script metadata
                        has_our_metadata = False
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

                        # Skip if name already exists in configuration
                        if entity_name in configured_names:
                            entity_counter += 1
                            continue

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
