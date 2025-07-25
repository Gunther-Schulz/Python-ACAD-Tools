"""
Canonical property schemas for entity sync operations.

This module defines which properties should be included in hash calculations
for each entity type, ensuring consistency between YAML and DXF property extraction.
"""

import math
from typing import Dict, Any, List, Optional
from src.utils import log_debug


class SyncPropertySchema:
    """Base class for entity property schemas."""

    @classmethod
    def get_canonical_properties(cls) -> List[str]:
        """Return the list of properties that should be included in hash calculation."""
        raise NotImplementedError

    @classmethod
    def normalize_property_value(cls, key: str, value: Any) -> Any:
        """Normalize a property value for consistent comparison."""
        if value is None:
            return None

        # Handle common normalizations
        if isinstance(value, float):
            # Round to 6 decimal places to avoid floating point precision issues
            return round(value, 6)
        elif isinstance(value, bool):
            return bool(value)
        elif isinstance(value, list):
            # Sort lists for consistent ordering (except for specific cases)
            if key in cls.get_ordered_list_properties():
                return list(value)  # Keep original order
            else:
                return sorted(list(value))  # Sort for consistency
        elif isinstance(value, dict):
            # Recursively normalize dict values
            return {k: cls.normalize_property_value(k, v) for k, v in sorted(value.items())}
        elif isinstance(value, str):
            return value.strip()
        else:
            return value

    @classmethod
    def get_ordered_list_properties(cls) -> List[str]:
        """Return list of properties where list order should be preserved."""
        return []

    @classmethod
    def extract_canonical_properties(cls, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and normalize only the canonical properties from entity data.

        Args:
            entity_data: Raw entity data (from YAML or DXF extraction)

        Returns:
            dict: Cleaned and normalized properties for hash calculation
        """
        canonical_props = {}

        for prop_name in cls.get_canonical_properties():
            if prop_name in entity_data:
                raw_value = entity_data[prop_name]
                normalized_value = cls.normalize_property_value(prop_name, raw_value)
                canonical_props[prop_name] = normalized_value

        log_debug(f"Extracted canonical properties for {cls.__name__}: {list(canonical_props.keys())}")
        return canonical_props


class ViewportSyncSchema(SyncPropertySchema):
    """Property schema for viewport entities."""

    @classmethod
    def get_canonical_properties(cls) -> List[str]:
        return [
            'name',
            'center',      # {x: float, y: float}
            'width',       # float
            'height',      # float
            'viewCenter',  # {x: float, y: float}
            'scale',       # float
            'frozenLayers',   # list of strings (sorted)
            'visibleLayers',  # list of strings (sorted) - alternative to frozenLayers
            'lockZoom',    # boolean
            # Note: Intentionally excluding color, layer
            # These are formatting/display details, not core content properties
            # Hash should only care about viewport geometry, scale, and layer visibility
        ]

    @classmethod
    def get_ordered_list_properties(cls) -> List[str]:
        # For viewports, layer lists can be sorted for consistency
        return []


class TextSyncSchema(SyncPropertySchema):
    """Property schema for text insert entities."""

    @classmethod
    def get_canonical_properties(cls) -> List[str]:
        return [
            'name',
            'text',        # string content
            'position',    # {type: 'absolute', x: float, y: float}
            'layer',       # string (layer name)
            'paperspace',  # boolean
            # Note: Intentionally excluding style, justification, height, color, rotation
            # These are formatting/display details, not core content properties
            # Hash should only care about WHAT text says and WHERE it is, not HOW it looks
        ]

    @classmethod
    def normalize_property_value(cls, key: str, value: Any) -> Any:
        """Text-specific normalization."""
        if key == 'text' and isinstance(value, str):
            # Normalize newlines for consistent comparison
            return value.replace('\r\n', '\n').replace('\r', '\n')
        elif key == 'paperspace':
            # Ensure boolean type
            return bool(value) if value is not None else False
        else:
            return super().normalize_property_value(key, value)


class BlockSyncSchema(SyncPropertySchema):
    @classmethod
    def get_canonical_properties(cls) -> List[str]:
        return [
            'name',         # string (identifier for the block insert)
            'blockName',    # string (which block definition to use)
            'scale',        # float (scaling factor, defaults to 1.0)
            'rotation',     # float (rotation angle in degrees, defaults to 0.0)
            'position',     # dict (placement information - absolute or geometry-based)
            'paperspace',   # boolean (model space vs paper space placement)
            # Note: Intentionally excluding 'sync' - this is a processing mode flag, not content
            # Hash should only care about WHAT block is placed, WHERE, and HOW (scale/rotation)
        ]

    @classmethod
    def normalize_property_value(cls, key: str, value: Any) -> Any:
        if key == 'scale':
            # Ensure scale is a float, default to 1.0 if None
            return float(value) if value is not None else 1.0
        elif key == 'rotation':
            # Ensure rotation is a float, default to 0.0 if None
            return float(value) if value is not None else 0.0
        elif key == 'paperspace':
            # Ensure boolean consistency
            return bool(value) if value is not None else False
        return super().normalize_property_value(key, value)


# Schema registry for entity types
SYNC_SCHEMAS = {
    'viewport': ViewportSyncSchema,
    'text': TextSyncSchema,
    'block': BlockSyncSchema,
}


def get_sync_schema(entity_type: str) -> Optional[SyncPropertySchema]:
    """Get the sync schema for an entity type."""
    return SYNC_SCHEMAS.get(entity_type)


def extract_canonical_sync_properties(entity_data: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
    """
    Extract canonical sync properties for any entity type.

    Args:
        entity_data: Raw entity data
        entity_type: Type of entity ('viewport', 'text', etc.)

    Returns:
        dict: Canonical properties for hash calculation
    """
    schema = get_sync_schema(entity_type)
    if schema:
        return schema.extract_canonical_properties(entity_data)
    else:
        # Fallback for unknown entity types - exclude sync metadata
        log_debug(f"No sync schema found for entity type '{entity_type}', using fallback")
        return {k: v for k, v in entity_data.items() if not k.startswith('_sync')}


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
        'dxf_canonical': dxf_canonical
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
