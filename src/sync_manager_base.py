from abc import ABC, abstractmethod
from src.utils import log_info, log_warning, log_error, log_debug


class SyncManagerBase(ABC):
    """Abstract base class for managing entity synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_settings, script_identifier, entity_type, project_loader=None):
        """
        Initialize the sync manager.

        Args:
            project_settings: Dictionary containing all project settings
            script_identifier: Unique identifier for this script's entities
            entity_type: Type of entity being managed (e.g., 'viewport', 'text_insert')
            project_loader: Optional project loader for YAML write-back functionality
        """
        self.project_settings = project_settings
        self.script_identifier = script_identifier
        self.entity_type = entity_type
        self.project_loader = project_loader

        # Extract global sync setting (e.g., 'viewport_sync', 'text_sync')
        sync_key = f'{entity_type}_sync'
        self.default_sync = project_settings.get(sync_key, 'skip')

        log_debug(f"{self.__class__.__name__} initialized with entity_type={entity_type}, "
                 f"default_sync={self.default_sync}")

    def _get_sync_direction(self, config):
        """
        Determine sync direction for an entity config.
        Uses per-entity sync if specified, otherwise falls back to global sync setting.

        Args:
            config: Entity configuration dictionary

        Returns:
            str: Sync direction ('push', 'pull', or 'skip')
        """
        entity_name = config.get('name', 'unnamed')

        # Check for deprecated updateDxf usage and provide migration guidance
        if 'updateDxf' in config:
            log_warning(f"{self.entity_type.title()} '{entity_name}' uses deprecated 'updateDxf' flag. "
                       f"Use 'sync: push' instead of 'updateDxf: true' or 'sync: skip' instead of 'updateDxf: false'.")

        # Use per-entity sync if specified, otherwise use global default
        if 'sync' in config:
            sync = config['sync']
        else:
            sync = self.default_sync
            log_debug(f"{self.entity_type.title()} '{entity_name}' using global sync setting: {sync}")

        # Validate sync direction
        valid_sync_values = {'push', 'pull', 'skip'}
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
        Main processing method for entity synchronization.

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

        # Write back YAML if any changes were made
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
            sync_direction: Sync direction ('push' or 'pull')

        Returns:
            dict: Result dictionary with 'entity' and 'yaml_updated' keys
        """
        entity_name = config.get('name', 'unnamed')

        if sync_direction == 'push':
            # YAML → AutoCAD: Create/update entity from YAML config
            result = self._sync_push(doc, space, config)
            return {'entity': result, 'yaml_updated': False} if result else None

        elif sync_direction == 'pull':
            # AutoCAD → YAML: Update YAML config from AutoCAD entity
            result = self._sync_pull(doc, space, config)
            return result if result else None

        else:
            log_warning(f"Unknown sync direction '{sync_direction}' for {self.entity_type} {entity_name}")
            return None

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
