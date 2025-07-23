import hashlib
import json
from src.utils import log_info, log_warning, log_error, log_debug


def calculate_entity_content_hash(entity_data, entity_type):
    """
    Calculate a consistent content hash for an entity.

    Args:
        entity_data: Dictionary containing entity properties
        entity_type: Type of entity ('viewport', 'text', etc.)

    Returns:
        str: SHA-256 hash of entity content
    """
    # Create a clean copy excluding sync metadata
    clean_data = {}

    if entity_type == 'viewport':
        # Include only content properties for viewports
        content_keys = [
            'name', 'center', 'width', 'height', 'viewCenter', 'scale',
            'frozenLayers', 'visibleLayers', 'lockZoom', 'color', 'layer'
        ]
        for key in content_keys:
            if key in entity_data:
                clean_data[key] = entity_data[key]

    elif entity_type == 'text':
        # Include only content properties for text inserts
        content_keys = [
            'name', 'text', 'position', 'targetLayer', 'paperspace',
            'style', 'justification', 'height', 'color', 'rotation'
        ]
        for key in content_keys:
            if key in entity_data:
                clean_data[key] = entity_data[key]
    else:
        # For unknown types, include everything except sync metadata
        clean_data = {k: v for k, v in entity_data.items() if not k.startswith('_sync')}

    # Create deterministic JSON representation
    json_str = json.dumps(clean_data, sort_keys=True, separators=(',', ':'))

    # Calculate SHA-256 hash
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    return hash_obj.hexdigest()


def get_sync_metadata(entity_config):
    """
    Extract sync metadata from entity configuration.

    Args:
        entity_config: Entity configuration dictionary

    Returns:
        dict: Sync metadata with default values
    """
    sync_meta = entity_config.get('_sync', {})
    return {
        'content_hash': sync_meta.get('content_hash'),
        'last_sync_time': sync_meta.get('last_sync_time'),
        'sync_source': sync_meta.get('sync_source'),
        'conflict_policy': sync_meta.get('conflict_policy')
    }


def update_sync_metadata(entity_config, content_hash, sync_source, conflict_policy=None):
    """
    Update sync metadata in entity configuration.

    Args:
        entity_config: Entity configuration dictionary to update
        content_hash: New content hash
        sync_source: Source of the sync ('yaml' or 'dxf')
        conflict_policy: Optional conflict resolution policy
    """
    import time

    if '_sync' not in entity_config:
        entity_config['_sync'] = {}

    entity_config['_sync']['content_hash'] = content_hash
    entity_config['_sync']['last_sync_time'] = int(time.time())
    entity_config['_sync']['sync_source'] = sync_source

    if conflict_policy:
        entity_config['_sync']['conflict_policy'] = conflict_policy


def detect_entity_changes(yaml_config, dxf_entity, entity_type, entity_manager=None):
    """
    Detect changes in entity by comparing content hashes.

    Args:
        yaml_config: Entity configuration from YAML
        dxf_entity: DXF entity object (or None if not found)
        entity_type: Type of entity for hash calculation
        entity_manager: Entity manager instance (ViewportManager, TextInsertManager, etc.)

    Returns:
        dict: Change detection results
    """
    # Get current and stored hashes
    current_yaml_hash = calculate_entity_content_hash(yaml_config, entity_type)
    sync_meta = get_sync_metadata(yaml_config)
    stored_hash = sync_meta['content_hash']

    # Calculate DXF hash if entity exists
    current_dxf_hash = None
    if dxf_entity and entity_manager:
        # Use entity manager's method to extract DXF properties
        if hasattr(entity_manager, '_extract_dxf_entity_properties_for_hash'):
            dxf_properties = entity_manager._extract_dxf_entity_properties_for_hash(dxf_entity)
            current_dxf_hash = calculate_entity_content_hash(dxf_properties, entity_type)
        else:
            log_warning(f"Entity manager {type(entity_manager)} missing _extract_dxf_entity_properties_for_hash method")

    # Determine changes
    yaml_changed = current_yaml_hash != stored_hash if stored_hash else True
    dxf_changed = current_dxf_hash != stored_hash if stored_hash and current_dxf_hash else False

    # Handle case where no stored hash exists (first time sync)
    if not stored_hash:
        if current_dxf_hash:
            # Compare current hashes to see if they differ
            yaml_changed = current_yaml_hash != current_dxf_hash
            dxf_changed = False  # Assume YAML is the source if no stored hash
        else:
            # No DXF entity exists, YAML should be pushed
            yaml_changed = True
            dxf_changed = False

    return {
        'yaml_changed': yaml_changed,
        'dxf_changed': dxf_changed,
        'current_yaml_hash': current_yaml_hash,
        'current_dxf_hash': current_dxf_hash,
        'stored_hash': stored_hash,
        'has_conflict': yaml_changed and dxf_changed
    }


def extract_dxf_entity_properties(entity, entity_type):
    """
    Extract properties from DXF entity for hash calculation.
    This is a fallback function - entity managers should implement their own.

    Args:
        entity: DXF entity object
        entity_type: Type of entity

    Returns:
        dict: Entity properties for hash calculation
    """
    log_warning(f"Using fallback DXF property extraction for {entity_type} - implement in entity manager")
    return {'fallback': 'properties_not_extracted'}


def resolve_sync_conflict(entity_name, yaml_config, dxf_entity, project_settings):
    """
    Resolve sync conflict when both YAML and DXF have changed.

    Args:
        entity_name: Name of the conflicted entity
        yaml_config: YAML entity configuration
        dxf_entity: DXF entity object
        project_settings: Project settings for global policies

    Returns:
        str: Resolution decision ('yaml_wins', 'dxf_wins', 'skip')
    """
    # Get conflict policy hierarchy
    sync_meta = get_sync_metadata(yaml_config)
    entity_policy = sync_meta.get('conflict_policy')
    global_policy = project_settings.get('auto_conflict_resolution', 'prompt')

    # Use entity policy if specified, otherwise global policy
    policy = entity_policy if entity_policy else global_policy

    if policy == 'yaml_wins':
        log_info(f"Conflict resolved: YAML wins for entity '{entity_name}' (policy: {policy})")
        return 'yaml_wins'
    elif policy == 'dxf_wins':
        log_info(f"Conflict resolved: DXF wins for entity '{entity_name}' (policy: {policy})")
        return 'dxf_wins'
    elif policy == 'skip':
        log_warning(f"Conflict detected: Skipping entity '{entity_name}' (policy: {policy})")
        return 'skip'
    elif policy == 'prompt':
        return prompt_user_for_conflict_resolution(entity_name, yaml_config, dxf_entity)
    else:
        log_warning(f"Unknown conflict policy '{policy}' for entity '{entity_name}', defaulting to prompt")
        return prompt_user_for_conflict_resolution(entity_name, yaml_config, dxf_entity)


def prompt_user_for_conflict_resolution(entity_name, yaml_config, dxf_entity):
    """
    Prompt user to resolve sync conflict interactively.

    Args:
        entity_name: Name of the conflicted entity
        yaml_config: YAML entity configuration
        dxf_entity: DXF entity object

    Returns:
        str: User choice ('yaml_wins', 'dxf_wins', 'skip')
    """
    print(f"\n⚠️  SYNC CONFLICT DETECTED for entity '{entity_name}'")
    print("Both YAML and DXF versions have been modified.")
    print("\nWhat would you like to do?")
    print("1. Use YAML version (overwrite DXF)")
    print("2. Use DXF version (overwrite YAML)")
    print("3. Skip this entity (leave both unchanged)")
    print("4. Show details")

    while True:
        try:
            choice = input("\nEnter your choice (1-4): ").strip()

            if choice == '1':
                log_info(f"User chose: YAML wins for entity '{entity_name}'")
                return 'yaml_wins'
            elif choice == '2':
                log_info(f"User chose: DXF wins for entity '{entity_name}'")
                return 'dxf_wins'
            elif choice == '3':
                log_info(f"User chose: Skip entity '{entity_name}'")
                return 'skip'
            elif choice == '4':
                show_conflict_details(entity_name, yaml_config, dxf_entity)
                continue
            else:
                print("Invalid choice. Please enter 1, 2, 3, or 4.")

        except KeyboardInterrupt:
            print("\n\nSync cancelled by user.")
            log_info(f"User cancelled sync during conflict resolution for '{entity_name}'")
            return 'skip'
        except EOFError:
            print("\n\nDefaulting to skip due to input error.")
            log_warning(f"Input error during conflict resolution for '{entity_name}', defaulting to skip")
            return 'skip'


def show_conflict_details(entity_name, yaml_config, dxf_entity):
    """
    Show detailed information about conflicted entity.

    Args:
        entity_name: Name of the conflicted entity
        yaml_config: YAML entity configuration
        dxf_entity: DXF entity object
    """
    print(f"\n📋 CONFLICT DETAILS for '{entity_name}':")
    print("\n--- YAML Version ---")

    # Show key YAML properties (exclude sync metadata)
    yaml_content = {k: v for k, v in yaml_config.items() if not k.startswith('_')}
    for key, value in yaml_content.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for sub_key, sub_value in value.items():
                print(f"    {sub_key}: {sub_value}")
        else:
            print(f"  {key}: {value}")

    print("\n--- DXF Version ---")
    print("  (DXF properties would be extracted here)")
    # This would show extracted DXF properties in real implementation

    print("\n--- End Details ---")


def initialize_sync_metadata_if_missing(entity_config, entity_type, entity_manager=None):
    """
    Initialize sync metadata for entity if missing or incomplete.

    Args:
        entity_config: Entity configuration dictionary
        entity_type: Type of entity ('viewport', 'text', etc.)
        entity_manager: Optional entity manager for DXF property extraction

    Returns:
        bool: True if metadata was initialized/updated, False if already complete
    """
    sync_meta = entity_config.get('_sync', {})

    # Check if initialization is needed
    needs_init = not sync_meta or not sync_meta.get('content_hash')

    if needs_init:
        log_debug(f"Initializing sync metadata for entity '{entity_config.get('name', 'unnamed')}'")

        # Calculate current hash from YAML content
        current_hash = calculate_entity_content_hash(entity_config, entity_type)

        # Initialize metadata with current state
        update_sync_metadata(entity_config, current_hash, 'yaml')

        log_info(f"Initialized sync metadata for '{entity_config.get('name')}' with hash: {current_hash[:12]}...")
        return True

    return False


def validate_and_repair_sync_metadata(entity_config, entity_type, dxf_entity=None, entity_manager=None):
    """
    Validate sync metadata and repair if corrupted or inconsistent.

    Args:
        entity_config: Entity configuration dictionary
        entity_type: Type of entity
        dxf_entity: Optional DXF entity for cross-validation
        entity_manager: Optional entity manager for DXF property extraction

    Returns:
        dict: Validation results and actions taken
    """
    entity_name = entity_config.get('name', 'unnamed')
    sync_meta = get_sync_metadata(entity_config)

    validation_result = {
        'valid': True,
        'repairs_made': [],
        'warnings': []
    }

    # Check for missing sync metadata
    if not sync_meta.get('content_hash'):
        log_warning(f"Missing content hash for entity '{entity_name}', initializing...")
        initialize_sync_metadata_if_missing(entity_config, entity_type, entity_manager)
        validation_result['repairs_made'].append('initialized_missing_metadata')
        validation_result['valid'] = False

    # Validate hash format
    stored_hash = sync_meta.get('content_hash')
    if stored_hash and (not isinstance(stored_hash, str) or len(stored_hash) != 64):
        log_warning(f"Invalid hash format for entity '{entity_name}', recalculating...")
        current_hash = calculate_entity_content_hash(entity_config, entity_type)
        update_sync_metadata(entity_config, current_hash, 'yaml')
        validation_result['repairs_made'].append('fixed_invalid_hash')
        validation_result['valid'] = False

    # Cross-validate with DXF if available
    if dxf_entity and entity_manager and hasattr(entity_manager, '_extract_dxf_entity_properties_for_hash'):
        try:
            dxf_properties = entity_manager._extract_dxf_entity_properties_for_hash(dxf_entity)
            dxf_hash = calculate_entity_content_hash(dxf_properties, entity_type)
            yaml_hash = calculate_entity_content_hash(entity_config, entity_type)

            # If stored hash doesn't match either current hash, there might be an issue
            if stored_hash != yaml_hash and stored_hash != dxf_hash:
                validation_result['warnings'].append('stored_hash_matches_neither_current_state')
                log_debug(f"Stored hash for '{entity_name}' doesn't match current YAML or DXF state")
        except Exception as e:
            log_warning(f"Could not cross-validate entity '{entity_name}': {str(e)}")
            validation_result['warnings'].append('cross_validation_failed')

    # Validate timestamp
    sync_time = sync_meta.get('last_sync_time')
    if sync_time and (not isinstance(sync_time, int) or sync_time < 0):
        log_warning(f"Invalid sync timestamp for entity '{entity_name}', resetting...")
        entity_config['_sync']['last_sync_time'] = int(time.time())
        validation_result['repairs_made'].append('fixed_invalid_timestamp')

    return validation_result


def ensure_sync_metadata_complete(entity_configs, entity_type, entity_manager=None):
    """
    Ensure all entities with auto sync have complete metadata.

    Args:
        entity_configs: List of entity configuration dictionaries
        entity_type: Type of entities
        entity_manager: Optional entity manager instance

    Returns:
        dict: Summary of initialization actions
    """
    import time

    summary = {
        'initialized_count': 0,
        'validated_count': 0,
        'repaired_count': 0
    }

    for config in entity_configs:
        entity_name = config.get('name', 'unnamed')
        sync_direction = config.get('sync', 'skip')

        # Only process entities using auto sync
        if sync_direction == 'auto':
            # Initialize if missing
            if initialize_sync_metadata_if_missing(config, entity_type, entity_manager):
                summary['initialized_count'] += 1

            # Validate and repair
            validation = validate_and_repair_sync_metadata(config, entity_type, None, entity_manager)
            summary['validated_count'] += 1

            if validation['repairs_made']:
                summary['repaired_count'] += 1
                log_info(f"Repaired sync metadata for '{entity_name}': {', '.join(validation['repairs_made'])}")

    if summary['initialized_count'] > 0:
        log_info(f"Initialized sync metadata for {summary['initialized_count']} {entity_type}(s)")
    if summary['repaired_count'] > 0:
        log_info(f"Repaired sync metadata for {summary['repaired_count']} {entity_type}(s)")

    return summary


def clean_entity_config_for_yaml_output(entity_config):
    """
    Clean entity configuration for YAML output, ensuring sync metadata is properly formatted.

    Args:
        entity_config: Entity configuration dictionary

    Returns:
        dict: Cleaned configuration ready for YAML output
    """
    # Create a copy to avoid modifying original
    clean_config = dict(entity_config)

    # Ensure sync metadata is properly structured
    if '_sync' in clean_config:
        sync_meta = clean_config['_sync']

        # Remove null values
        sync_meta = {k: v for k, v in sync_meta.items() if v is not None}

        # Ensure proper data types
        if 'last_sync_time' in sync_meta and sync_meta['last_sync_time'] is not None:
            sync_meta['last_sync_time'] = int(sync_meta['last_sync_time'])

        if 'content_hash' in sync_meta and sync_meta['content_hash'] is not None:
            sync_meta['content_hash'] = str(sync_meta['content_hash'])

        # Only include sync metadata if it has meaningful content
        if sync_meta:
            clean_config['_sync'] = sync_meta
        else:
            # Remove empty sync metadata
            del clean_config['_sync']

    return clean_config
