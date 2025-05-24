"""DXF-related adapter utilities for external ezdxf library integration."""

from .entity_operations import (
    attach_xdata,
    get_xdata,
    has_xdata_value,
    attach_script_identifier,
    remove_entities_by_layer,
    is_created_by_script,
    APP_ID_PREFIX
)
from .document_maintenance import cleanup_dxf_document
from .geometry_conversions import (
    convert_dxf_circle_to_polygon,
    extract_dxf_entity_basepoint,
)

__all__ = [
    "attach_xdata",
    "get_xdata",
    "has_xdata_value",
    "attach_script_identifier",
    "remove_entities_by_layer",
    "is_created_by_script",
    "APP_ID_PREFIX",
    "cleanup_dxf_document",
    "convert_dxf_circle_to_polygon",
    "extract_dxf_entity_basepoint",
]
