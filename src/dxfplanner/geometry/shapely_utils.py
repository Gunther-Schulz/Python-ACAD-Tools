"""
Shapely geometry processing utility functions.
"""
from typing import Optional, Iterator
from dxfplanner.core.logging_config import get_logger
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint, GeometryCollection
from shapely.validation import make_valid as shapely_make_valid
from shapely.ops import unary_union

logger = get_logger(__name__)

def make_valid_geometry(geometry: BaseGeometry) -> Optional[BaseGeometry]:
    """
    Attempts to make a Shapely geometry valid.
    If the input geometry is already valid, it's returned as is.
    If validation results in a GeometryCollection, it attempts to extract and union
    compatible geometries (Polygons, LineStrings, Points).

    Args:
        geometry: The input Shapely geometry.

    Returns:
        A valid Shapely geometry, or None if the geometry is None, empty,
        or cannot be made valid into a supported type.
    """
    if geometry is None or geometry.is_empty:
        logger.debug("Input geometry is None or empty, returning as is.")
        return geometry
    if geometry.is_valid:
        return geometry

    logger.debug(f"Attempting to make invalid geometry valid: {geometry.geom_type}")
    try:
        valid_geom = shapely_make_valid(geometry)

        if valid_geom.is_empty:
            logger.warning(f"Geometry became empty after make_valid: {geometry.wkt[:100]}...")
            return None
        if not valid_geom.is_valid: # Should not happen if make_valid works
             logger.warning(f"Geometry still invalid after make_valid: {valid_geom.wkt[:100]}...")
             return None

        if isinstance(valid_geom, GeometryCollection):
            logger.debug(f"make_valid resulted in a GeometryCollection with {len(valid_geom.geoms)} parts.")
            parts = [
                part for part in valid_geom.geoms
                if isinstance(part, (Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint)) and not part.is_empty
            ]
            if not parts:
                logger.warning(f"GeometryCollection from make_valid for {geometry.wkt[:100]}... contained no usable parts.")
                return None
            if len(parts) == 1:
                logger.debug("Extracted single usable part from GeometryCollection.")
                return parts[0]
            try:
                logger.debug(f"Attempting unary_union on {len(parts)} extracted parts from GeometryCollection.")
                unioned_parts = unary_union(parts)
                if unioned_parts.is_empty:
                    logger.warning("Unary union of GeometryCollection parts resulted in empty geometry.")
                    return None
                return unioned_parts
            except Exception as e_union:
                logger.warning(f"Failed to unary_union parts of GeometryCollection from make_valid: {e_union}. Returning None.")
                return None

        return valid_geom
    except Exception as e:
        logger.error(f"Error during make_valid_geometry for {geometry.wkt[:100]}...: {e}", exc_info=True)
        return None

def remove_islands_from_geometry(geometry: BaseGeometry, preserve_islands: bool = False) -> Optional[BaseGeometry]:
    """
    Removes or preserves islands (holes) from Polygon or MultiPolygon geometries.
    If preserve_islands is True, it attempts to keep the original geometry if it has holes.
    If preserve_islands is False (default), it reconstructs polygons using only their exteriors.

    Args:
        geometry: The input Shapely Polygon or MultiPolygon.
        preserve_islands: If True, keeps islands; if False, removes them.

    Returns:
        The processed geometry, or the original geometry if not a Polygon/MultiPolygon,
        or None if processing results in an empty geometry.
    """
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry

    if geometry.is_empty:
        return None

    def process_polygon(poly: Polygon) -> Optional[Polygon]:
        if poly.is_empty:
            return None
        if preserve_islands:
            return poly
        else:
            if poly.exterior is None or len(poly.exterior.coords) < 3:
                logger.warning("Polygon has no valid exterior to reconstruct without islands.")
                return None
            return Polygon(poly.exterior)

    processed_polygons = []
    if isinstance(geometry, Polygon):
        processed = process_polygon(geometry)
        if processed:
            processed_polygons.append(processed)
    elif isinstance(geometry, MultiPolygon):
        for p in geometry.geoms:
            if p.is_empty: continue
            processed = process_polygon(p)
            if processed:
                processed_polygons.append(processed)

    if not processed_polygons:
        logger.debug(f"No polygons remained after island processing for input: {geometry.wkt[:100]}...")
        return None

    if len(processed_polygons) == 1:
        return processed_polygons[0]

    try:
        final_geometry = unary_union(processed_polygons)
        if final_geometry.is_empty:
            return None
        return final_geometry
    except Exception as e:
        logger.error(f"Error during unary_union in remove_islands: {e}", exc_info=True)
        return None

def explode_multipart_geometry(shapely_geom: BaseGeometry) -> Iterator[BaseGeometry]:
    """
    Explodes a Shapely MultiGeometry (MultiPoint, MultiLineString, MultiPolygon)
    or GeometryCollection into an iterator of its single-part constituent geometries.
    Single-part geometries (Point, LineString, Polygon) are yielded as is.

    Args:
        shapely_geom: The input Shapely geometry.

    Yields:
        Iterator[BaseGeometry]: An iterator of single-part Shapely geometries.
    """
    if shapely_geom is None or shapely_geom.is_empty:
        return

    if isinstance(shapely_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
        if hasattr(shapely_geom, 'geoms'):
            for part in shapely_geom.geoms:
                if part is not None and not part.is_empty:
                    yield from explode_multipart_geometry(part)
        else:
            logger.warning(f"MultiGeometry/Collection {shapely_geom.geom_type} without .geoms attribute? Yielding as is if simple.")
            if isinstance(shapely_geom, (Point, LineString, Polygon)):
                 yield shapely_geom
    elif isinstance(shapely_geom, (Point, LineString, Polygon)):
        yield shapely_geom
    else:
        logger.warning(f"explode_multipart_geometry: Unsupported input geometry type: {type(shapely_geom)}. Skipping.")
        return
