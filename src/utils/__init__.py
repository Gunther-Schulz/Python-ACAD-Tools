"""Utility modules for stateless, pure functions.

This module contains only truly generic utility functions that are stateless and don't
contain business logic. Domain-specific functionality has been moved to appropriate
services and adapters:

- DXF-related utilities -> src/adapters/dxf/
- Complex geometry operations -> src/services/geometry/
- Exceptions -> src/domain/exceptions.py
"""

# Import truly generic utilities
from .filesystem import ensure_parent_dir_exists
from .text_processing import sanitize_dxf_layer_name
from .visualization import plot_gdf, plot_shapely_geometry

# Import commonly used items from other modules for backward compatibility
# (These should eventually be imported directly from their new locations)
from ..adapters.dxf import (
    attach_xdata,
    get_xdata,
    has_xdata_value,
    remove_entities_by_layer,
    attach_script_identifier,
    cleanup_dxf_document,
    convert_dxf_circle_to_polygon,
    extract_dxf_entity_basepoint,
)
from ..services.geometry import GEOMETRY_COLUMN
from ..domain.exceptions import DXFGeometryConversionError, GdfValidationError

__all__ = [
    # True utilities (stateless, generic)
    "ensure_parent_dir_exists",
    "sanitize_dxf_layer_name",
    "plot_gdf",
    "plot_shapely_geometry",

    # Backward compatibility imports (consider removing in future versions)
    # DXF adapter functions
    "attach_xdata",
    "get_xdata",
    "has_xdata_value",
    "remove_entities_by_layer",
    "attach_script_identifier",
    "cleanup_dxf_document",
    "convert_dxf_circle_to_polygon",
    "extract_dxf_entity_basepoint",

    # Geometry service constants
    "GEOMETRY_COLUMN",

    # Domain exceptions
    "DXFGeometryConversionError",
    "GdfValidationError",
]
