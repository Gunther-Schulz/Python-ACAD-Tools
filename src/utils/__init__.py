"""Utility modules for the application."""

from .file_utils import ensure_parent_dir_exists
from .string_utils import sanitize_dxf_layer_name
from .dxf_entity_utils import attach_xdata, get_xdata, has_xdata_value, remove_entities_by_layer, attach_script_identifier
from .dxf_maintenance_utils import cleanup_dxf_document
from .plotting_utils import plot_gdf, plot_shapely_geometry
from .dxf_geometry_utils import (
    convert_dxf_circle_to_polygon,
    extract_dxf_entity_basepoint,
    DXFGeometryConversionError
)
from .geodataframe_utils import (
    get_validated_source_gdf,
    reproject_gdf,
    get_common_crs,
    ensure_multi_geometry,
    make_valid_geometries,
    filter_gdf_by_attribute_values,
    filter_gdf_by_intersection,
    GdfValidationError,
    GEOMETRY_COLUMN
)
from .advanced_geometry_utils import create_envelope_for_geometry

__all__ = [
    "ensure_parent_dir_exists",
    "sanitize_dxf_layer_name",
    "attach_xdata",
    "get_xdata",
    "has_xdata_value",
    "cleanup_dxf_document",
    "plot_gdf",
    "plot_shapely_geometry",
    "convert_dxf_circle_to_polygon",
    "extract_dxf_entity_basepoint",
    "DXFGeometryConversionError",
    # New geodataframe_utils exports
    "get_validated_source_gdf",
    "reproject_gdf",
    "get_common_crs",
    "ensure_multi_geometry",
    "make_valid_geometries",
    "GdfValidationError",
    "GEOMETRY_COLUMN",
    "filter_gdf_by_attribute_values",
    "filter_gdf_by_intersection",
    "create_envelope_for_geometry",
    "remove_entities_by_layer",
    "attach_script_identifier"
]
