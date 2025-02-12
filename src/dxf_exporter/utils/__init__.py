"""DXF exporter utility functions."""

from .constants import SCRIPT_IDENTIFIER
from .document_utils import (
    initialize_document,
    cleanup_document,
    set_drawing_properties,
    verify_dxf_settings,
    load_standard_text_styles
)
from .entity_utils import (
    attach_custom_data,
    remove_entities_by_layer,
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
    convert_transparency,
    get_style
)
from .text_utils import (
    add_mtext,
    add_text
)

__all__ = [
    'SCRIPT_IDENTIFIER',
    'initialize_document',
    'cleanup_document',
    'set_drawing_properties',
    'verify_dxf_settings',
    'load_standard_text_styles',
    'ensure_layer_exists',
    'attach_custom_data',
    'remove_entities_by_layer',
    'is_created_by_script',
    'apply_style_to_entity',
    'create_hatch',
    'set_hatch_transparency',
    'get_available_blocks',
    'add_block_reference',
    'update_layer_properties',
    'sanitize_layer_name',
    'get_color_code',
    'convert_transparency',
    'get_style',
    'add_mtext',
    'add_text'
] 