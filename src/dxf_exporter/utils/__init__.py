"""DXF exporter utility functions."""

from .constants import SCRIPT_IDENTIFIER
from .document_utils import (
    set_drawing_properties,
    verify_dxf_settings,
    cleanup_document,
    initialize_document,
    load_standard_text_styles
)
from .entity_utils import (
    attach_custom_data,
    is_created_by_script,
    apply_style_to_entity
)
from .geometry_utils import (
    create_hatch,
    set_hatch_transparency,
    get_available_blocks,
    add_block_reference
)
from .layer_utils import (
    ensure_layer_exists,
    update_layer_properties,
    sanitize_layer_name
)
from .style_utils import (
    get_color_code,
    convert_transparency
)
from .text_utils import (
    add_mtext,
    add_text,
    _apply_text_style_properties
)

__all__ = [
    'SCRIPT_IDENTIFIER',
    # Document utils
    'set_drawing_properties',
    'verify_dxf_settings',
    'cleanup_document',
    'initialize_document',
    'load_standard_text_styles',
    # Entity utils
    'attach_custom_data',
    'is_created_by_script',
    'apply_style_to_entity',
    # Geometry utils
    'create_hatch',
    'set_hatch_transparency',
    'get_available_blocks',
    'add_block_reference',
    # Layer utils
    'ensure_layer_exists',
    'update_layer_properties',
    'sanitize_layer_name',
    # Style utils
    'get_color_code',
    'convert_transparency',
    # Text utils
    'add_mtext',
    'add_text',
    '_apply_text_style_properties'
] 