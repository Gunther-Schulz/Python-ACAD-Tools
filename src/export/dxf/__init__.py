"""
DXF export module for OLADPP.
Handles exporting geometries to DXF format.
"""
from .exporter import DXFExporter
from .utils import (
    get_color_code, attach_custom_data, is_created_by_script,
    add_text, remove_entities_by_layer, ensure_layer_exists,
    update_layer_properties, set_drawing_properties, verify_dxf_settings,
    sanitize_layer_name, add_mtext
)

__all__ = [
    'DXFExporter',
    'get_color_code',
    'attach_custom_data',
    'is_created_by_script',
    'add_text',
    'remove_entities_by_layer',
    'ensure_layer_exists',
    'update_layer_properties',
    'set_drawing_properties',
    'verify_dxf_settings',
    'sanitize_layer_name',
    'add_mtext'
]
