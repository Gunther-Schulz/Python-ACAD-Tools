import hashlib
import json
from src.utils import log_info, log_warning, log_error, log_debug
from src.sync_property_schemas import extract_canonical_sync_properties
from typing import Dict, Any


def calculate_entity_content_hash(entity_data, entity_type):
    """
    Calculate a consistent content hash for an entity using canonical property schemas.

    Args:
        entity_data: Dictionary containing entity properties
        entity_type: Type of entity ('viewport', 'text', etc.)

    Returns:
        str: SHA-256 hash of entity content
    """
    from src.sync_property_schemas import extract_canonical_sync_properties

    # Extract only the properties that should be used for sync comparison
    canonical_data = extract_canonical_sync_properties(entity_data, entity_type)

    # Convert to JSON string for consistent hashing
    json_str = json.dumps(canonical_data, sort_keys=True, ensure_ascii=True)

    # Calculate SHA-256 hash
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))

    log_debug(f"Hash calculation for {entity_type} '{entity_data.get('name', 'unnamed')}': "
          f"canonical_props={list(canonical_data.keys())}, hash={hash_obj.hexdigest()[:12]}...")
    log_debug(f"  JSON: {json_str}")

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
        'sync_source': sync_meta.get('sync_source'),
        'conflict_policy': sync_meta.get('conflict_policy')
    }


def update_sync_metadata(entity_config, content_hash, sync_source, conflict_policy=None, entity_handle=None):
    """
    Update sync metadata in entity configuration.

    Args:
        entity_config: Entity configuration dictionary to update
        content_hash: New content hash
        sync_source: Source of the sync ('yaml' or 'dxf')
        conflict_policy: Optional conflict resolution policy
        entity_handle: Optional entity handle for identity tracking (stored as dxf_handle)
    """
    if not entity_config:
        from src.utils import log_warning
        log_warning("entity_config is None in update_sync_metadata")
        return

    if '_sync' not in entity_config or entity_config['_sync'] is None:
        entity_config['_sync'] = {}

    entity_config['_sync']['content_hash'] = content_hash
    entity_config['_sync']['sync_source'] = sync_source

    if entity_handle:
        entity_config['_sync']['dxf_handle'] = entity_handle
        # Remove redundant entity_handle field - we only need dxf_handle

    if conflict_policy:
        entity_config['_sync']['conflict_policy'] = conflict_policy


def detect_entity_changes(yaml_config, dxf_entity, entity_type, entity_manager):
    """
    Detect changes in entity by comparing content hashes.

    Args:
        yaml_config: Entity configuration from YAML
        dxf_entity: Corresponding DXF entity (or None if not found)
        entity_type: Type of entity for hash calculation
        entity_manager: Manager instance with hash extraction method

    Returns:
        dict: Change detection results
    """
    if not yaml_config:
        from src.utils import log_warning
        log_warning("yaml_config is None in detect_entity_changes")
        return {
            'yaml_changed': False,
            'dxf_changed': False,
            'has_conflict': False,
            'current_yaml_hash': None,
            'current_dxf_hash': None,
            'stored_hash': None,
            'sync_meta': {}
        }

    entity_name = yaml_config.get('name', 'unnamed')
    sync_meta = yaml_config.get('_sync', {}) or {}

    log_debug(f"🔍 HASH DEBUG for '{entity_name}' ({entity_type})")

    # Get current and stored hashes
    current_yaml_hash = calculate_entity_content_hash(yaml_config, entity_type)

    stored_hash = sync_meta.get('content_hash')

    log_debug(f"  📝 YAML hash: {current_yaml_hash}")
    log_debug(f"  💾 Stored hash: {stored_hash}")

    # Calculate DXF hash if entity exists
    current_dxf_hash = None
    if dxf_entity:
        if hasattr(entity_manager, '_extract_dxf_entity_properties_for_hash'):
            dxf_properties = entity_manager._extract_dxf_entity_properties_for_hash(dxf_entity)

            current_dxf_hash = calculate_entity_content_hash(dxf_properties, entity_type)
            log_debug(f"  📄 DXF hash: {current_dxf_hash}")
        else:
            log_debug(f"Entity manager {type(entity_manager)} missing _extract_dxf_entity_properties_for_hash method")

        # Determine what changed
    yaml_changed = current_yaml_hash != stored_hash if stored_hash else True

    # Handle DXF changes properly - if DXF entity is missing, it's not a "change"
    if current_dxf_hash is None:
        dxf_changed = False  # Missing entity is not a change, it's an absence
    else:
        dxf_changed = current_dxf_hash != stored_hash if stored_hash else False

    # IMPORTANT: If we have both current hashes and they match each other,
    # but differ from stored hash, this is NOT a conflict - both sides are in sync
    # This happens when baseline hash is outdated/inconsistent
    if stored_hash and current_yaml_hash and current_dxf_hash:
        if current_yaml_hash == current_dxf_hash and (yaml_changed or dxf_changed):
            # Both sides have same content but differ from stored baseline
            # This is a baseline update scenario, not a conflict
            yaml_changed = False
            dxf_changed = False
            log_debug(f"  🔄 Baseline hash outdated - YAML and DXF are in sync, updating baseline")
        elif yaml_changed and dxf_changed and dxf_entity:
            # Check if DXF entity is managed by our app (has our XDATA)
            is_managed_entity = False
            try:
                from src.dxf_utils import XDATA_APP_ID
                xdata = dxf_entity.get_xdata(XDATA_APP_ID)
                is_managed_entity = bool(xdata)
            except:
                is_managed_entity = False

            if is_managed_entity:
                # For managed entities, prefer DXF changes (user likely moved it in AutoCAD)
                # This avoids false conflicts when user moves managed blocks
                yaml_changed = False  # Treat as DXF-only change
                log_debug(f"  🎯 Managed entity detected - treating as DXF change (likely moved in AutoCAD)")

    log_debug(f"  ✅ YAML changed: {yaml_changed} (current != stored: {current_yaml_hash != stored_hash if stored_hash else 'no stored hash'})")
    log_debug(f"  ✅ DXF changed: {dxf_changed} (current != stored: {current_dxf_hash != stored_hash if stored_hash and current_dxf_hash else 'no DXF hash'})")

    # Handle case where no stored hash exists (first time sync)
    if not stored_hash:
        if current_dxf_hash:
            # Check if DXF entity is managed by our app (has our XDATA)
            is_managed_entity = False
            if dxf_entity:
                try:
                    from src.dxf_utils import XDATA_APP_ID
                    xdata = dxf_entity.get_xdata(XDATA_APP_ID)
                    is_managed_entity = bool(xdata)
                except:
                    is_managed_entity = False

            if is_managed_entity:
                # Entity is managed by our app - compare hashes for sync
                yaml_changed = current_yaml_hash != current_dxf_hash
                dxf_changed = False  # Assume YAML is the source if no stored hash
                log_debug(f"  🆕 No stored hash (managed entity) - comparing YAML vs DXF: {yaml_changed}")
            else:
                # Entity exists but not managed by our app - treat as push scenario
                yaml_changed = True
                dxf_changed = False
                log_debug(f"  🆕 DXF entity exists but unmanaged (no XDATA) - YAML should be pushed")
        else:
            # No DXF entity, YAML should be pushed
            yaml_changed = True
            dxf_changed = False
            log_debug(f"  🆕 No stored hash, no DXF entity - YAML should be pushed")

    return {
        'yaml_changed': yaml_changed,
        'dxf_changed': dxf_changed,
        'has_conflict': yaml_changed and dxf_changed,
        'current_yaml_hash': current_yaml_hash,
        'current_dxf_hash': current_dxf_hash,
        'stored_hash': stored_hash,
        'sync_meta': sync_meta
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
    if dxf_entity:
        # Try to extract DXF properties for display
        try:
            # This is a simplified extraction for display purposes
            dxf_props = {}
            if hasattr(dxf_entity.dxf, 'center'):
                center = dxf_entity.dxf.center
                dxf_props['center'] = {'x': float(center[0]), 'y': float(center[1])}
            if hasattr(dxf_entity.dxf, 'width'):
                dxf_props['width'] = float(dxf_entity.dxf.width)
            if hasattr(dxf_entity.dxf, 'height'):
                dxf_props['height'] = float(dxf_entity.dxf.height)
            if hasattr(dxf_entity.dxf, 'insert'):
                insert = dxf_entity.dxf.insert
                dxf_props['position'] = {'x': float(insert[0]), 'y': float(insert[1]), 'type': 'absolute'}
            if hasattr(dxf_entity.dxf, 'layer'):
                dxf_props['layer'] = dxf_entity.dxf.layer
            if dxf_entity.dxftype() == 'MTEXT':
                dxf_props['text'] = dxf_entity.plain_text().replace('\n', '\\n')
            elif hasattr(dxf_entity.dxf, 'text'):
                dxf_props['text'] = dxf_entity.dxf.text

            for key, value in dxf_props.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"    {sub_key}: {sub_value}")
                else:
                    print(f"  {key}: {value}")
        except Exception as e:
            print(f"  (Error extracting DXF properties: {str(e)})")
    else:
        print("  (No DXF entity found)")

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
        if 'content_hash' in sync_meta and sync_meta['content_hash'] is not None:
            sync_meta['content_hash'] = str(sync_meta['content_hash'])

        # Only include sync metadata if it has meaningful content
        if sync_meta:
            clean_config['_sync'] = sync_meta
        else:
            # Remove empty sync metadata
            del clean_config['_sync']

    return clean_config


def validate_sync_property_consistency(yaml_data: Dict[str, Any], dxf_data: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
    """
    Validate that YAML and DXF data will produce consistent hashes.

    Args:
        yaml_data: YAML entity configuration
        dxf_data: DXF extracted properties
        entity_type: Type of entity

    Returns:
        dict: Validation results with any inconsistencies found
    """
    yaml_canonical = extract_canonical_sync_properties(yaml_data, entity_type)
    dxf_canonical = extract_canonical_sync_properties(dxf_data, entity_type)

    result = {
        'consistent': True,
        'differences': [],
        'yaml_canonical': yaml_canonical,
        'dxf_canonical': dxf_canonical,
        'yaml_hash': calculate_entity_content_hash(yaml_data, entity_type),
        'dxf_hash': calculate_entity_content_hash(dxf_data, entity_type)
    }

    # Compare canonical properties
    all_keys = set(yaml_canonical.keys()) | set(dxf_canonical.keys())

    for key in all_keys:
        yaml_val = yaml_canonical.get(key)
        dxf_val = dxf_canonical.get(key)

        if yaml_val != dxf_val:
            result['consistent'] = False
            result['differences'].append({
                'property': key,
                'yaml_value': yaml_val,
                'dxf_value': dxf_val
            })

    return result


def debug_hash_calculation(entity_config, dxf_entity, entity_type, entity_manager=None):
    """
    Debug helper for sync hash calculation issues.

    Args:
        entity_config: YAML entity configuration
        dxf_entity: DXF entity object
        entity_type: Type of entity
        entity_manager: Entity manager instance

    Returns:
        dict: Detailed debug information
    """
    entity_name = entity_config.get('name', 'unnamed')
    log_debug(f"🔍 Debug hash calculation for {entity_type} '{entity_name}'")

    # Calculate YAML hash
    yaml_hash = calculate_entity_content_hash(entity_config, entity_type)
    yaml_canonical = extract_canonical_sync_properties(entity_config, entity_type)

    debug_info = {
        'entity_name': entity_name,
        'entity_type': entity_type,
        'yaml_hash': yaml_hash,
        'yaml_canonical_properties': yaml_canonical,
        'dxf_available': dxf_entity is not None,
    }

    # Calculate DXF hash if entity exists
    if dxf_entity and entity_manager and hasattr(entity_manager, '_extract_dxf_entity_properties_for_hash'):
        dxf_properties = entity_manager._extract_dxf_entity_properties_for_hash(dxf_entity)
        dxf_hash = calculate_entity_content_hash(dxf_properties, entity_type)
        dxf_canonical = extract_canonical_sync_properties(dxf_properties, entity_type)

        debug_info.update({
            'dxf_hash': dxf_hash,
            'dxf_raw_properties': dxf_properties,
            'dxf_canonical_properties': dxf_canonical,
            'hashes_match': yaml_hash == dxf_hash,
        })

        # Detailed property comparison
        validation = validate_sync_property_consistency(entity_config, dxf_properties, entity_type)
        debug_info['property_validation'] = validation

        # Log summary
        if validation['consistent']:
            log_info(f"✅ Properties consistent for '{entity_name}' (hashes: {'match' if yaml_hash == dxf_hash else 'DIFFER'})")
        else:
            log_warning(f"❌ Property inconsistencies found for '{entity_name}':")
            for diff in validation['differences']:
                log_warning(f"  - {diff['property']}: YAML={diff['yaml_value']} vs DXF={diff['dxf_value']}")
    else:
        debug_info['dxf_hash'] = None
        debug_info['dxf_properties'] = None
        debug_info['hashes_match'] = None
        log_info(f"ℹ️  No DXF entity found for comparison")

    return debug_info
