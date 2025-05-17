"""
Coordinate Reference System (CRS) reprojection utilities for Shapely geometries.
"""
from typing import Optional
from dxfplanner.core.logging_config import get_logger
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform_op
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError

logger = get_logger(__name__)

def reproject_geometry(
    shapely_geom: BaseGeometry,
    source_crs_str: str,
    target_crs_str: str
) -> Optional[BaseGeometry]:
    """
    Reprojects a Shapely geometry from a source CRS to a target CRS.

    Args:
        shapely_geom: The input Shapely geometry.
        source_crs_str: The source Coordinate Reference System string (e.g., "EPSG:4326").
        target_crs_str: The target Coordinate Reference System string (e.g., "EPSG:3857").

    Returns:
        The reprojected Shapely geometry, or None if reprojection fails.
    """
    if shapely_geom is None or shapely_geom.is_empty:
        return None
    if not source_crs_str or not target_crs_str:
        logger.error("Source or target CRS is not provided for reprojection.")
        return None
    if source_crs_str.lower() == target_crs_str.lower():
        logger.debug(f"Source and target CRS are the same ('{source_crs_str}'). No reprojection needed.")
        return shapely_geom

    try:
        source_crs = CRS.from_user_input(source_crs_str)
        target_crs = CRS.from_user_input(target_crs_str)

        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        reprojected_geom = shapely_transform_op(transformer.transform, shapely_geom)

        if reprojected_geom is None or reprojected_geom.is_empty:
            logger.warning(f"Geometry became None or empty after reprojection from {source_crs_str} to {target_crs_str}.")
            return None
        return reprojected_geom
    except CRSError as e_crs:
        logger.error(f"CRS Error during reprojection from '{source_crs_str}' to '{target_crs_str}': {e_crs}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during geometry reprojection: {e}", exc_info=True)
        return None
