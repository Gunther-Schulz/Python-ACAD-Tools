"""Legacy module for backward compatibility. All functionality has been moved to dxf_exporter.utils."""

from src.dxf_exporter.utils import (
    SCRIPT_IDENTIFIER,
    # Document utils
    set_drawing_properties,
    verify_dxf_settings,
    cleanup_document,
    initialize_document,
    load_standard_text_styles,
    # Entity utils
    attach_custom_data,
    remove_entities_by_layer,
    is_created_by_script,
    apply_style_to_entity,
    # Geometry utils
    create_hatch,
    set_hatch_transparency,
    get_available_blocks,
    add_block_reference,
    # Layer utils
    ensure_layer_exists,
    update_layer_properties,
    sanitize_layer_name,
    # Style utils
    get_color_code,
    convert_transparency,
    get_style,
    # Text utils
    add_mtext,
    add_text
)

__all__ = [
    'SCRIPT_IDENTIFIER',
    'set_drawing_properties',
    'verify_dxf_settings',
    'cleanup_document',
    'initialize_document',
    'load_standard_text_styles',
    'attach_custom_data',
    'remove_entities_by_layer',
    'is_created_by_script',
    'apply_style_to_entity',
    'create_hatch',
    'set_hatch_transparency',
    'get_available_blocks',
    'add_block_reference',
    'ensure_layer_exists',
    'update_layer_properties',
    'sanitize_layer_name',
    'get_color_code',
    'convert_transparency',
    'get_style',
    'add_mtext',
    'add_text'
]























































































