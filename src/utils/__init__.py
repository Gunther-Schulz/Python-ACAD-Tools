"""Utility modules for stateless, pure functions.

This module contains only truly generic utility functions that are stateless and don't
contain business logic. Domain-specific functionality has been moved to appropriate
services and adapters:

- DXF-related utilities -> src/adapters/dxf/
- Complex geometry operations -> src/services/geometry/
- Exceptions -> src/domain/exceptions.py
"""

# Import only truly generic utilities
from .filesystem import ensure_parent_dir_exists
from .text_processing import sanitize_dxf_layer_name
from .visualization import plot_gdf, plot_shapely_geometry

__all__ = [
    # True utilities (stateless, generic)
    "ensure_parent_dir_exists",
    "sanitize_dxf_layer_name",
    "plot_gdf",
    "plot_shapely_geometry",
]
