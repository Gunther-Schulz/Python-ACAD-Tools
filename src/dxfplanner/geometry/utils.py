"""
General geometric utilities.
"""
import re
from typing import Tuple, Union, Optional, Any, Iterator
from dxfplanner.core.logging_config import get_logger
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint, GeometryCollection
from shapely.validation import make_valid as shapely_make_valid
from shapely.ops import unary_union

logger = get_logger(__name__)

def get_color_code(color: Any, name_to_aci: dict) -> Union[int, Tuple[int, int, int]]:
    """Converts various color inputs to an ACI code or an RGB tuple."""
    if color is None:
        return 7  # Default to 7 (white/black) if no color is specified
    if isinstance(color, int):
        return color  # Return ACI code as-is
    elif isinstance(color, str):
        if ',' in color:
            # It's an RGB string "r,g,b"
            try:
                rgb = tuple(map(int, color.split(',')))
                if len(rgb) == 3 and all(0 <= val <= 255 for val in rgb):
                    return rgb
                else:
                    logger.warning(f"Invalid RGB color string values: {color}")
                    return 7
            except ValueError:
                logger.warning(f"Invalid RGB color string format: {color}")
                return 7
        else:
            # It's a color name
            aci_code = name_to_aci.get(color.lower())
            if aci_code is None:
                logger.warning(f"Color name '{color}' not found in ACI color mapping. Defaulting to white (7).")
                return 7
            return aci_code
    elif isinstance(color, (list, tuple)) and len(color) == 3 and all(isinstance(val, int) and 0 <= val <= 255 for val in color):
        # It's already an RGB tuple
        return tuple(color)
    else:
        logger.warning(f"Invalid color type or format: {color}. Defaulting to white (7).")
        return 7

def convert_transparency(transparency: Any) -> Optional[float]:
    """Converts a transparency value to a float between 0.0 (opaque) and 1.0 (fully transparent)."""
    # ezdxf typically uses integer transparency 0x020000TT where TT is 00 (opaque) to FF (255, fully transparent)
    # This function aims for a 0.0 to 1.0 scale.
    val_to_convert = None
    if isinstance(transparency, (int, float)):
        val_to_convert = float(transparency)
    elif isinstance(transparency, str):
        try:
            val_to_convert = float(transparency)
        except ValueError:
            logger.warning(f"Invalid transparency value string: {transparency}")
            return None

    if val_to_convert is not None:
        # Clamp to 0.0 - 1.0 range, assuming direct input or already scaled.
        # More complex heuristics for 0-100 or 0-255 scales were removed for clarity;
        # this should be handled by the input provider or a more specific config.
        if 0.0 <= val_to_convert <= 1.0:
            return val_to_convert
        elif val_to_convert > 1.0: # If input is like 50 (for 50%), it will become 1.0
            logger.debug(f"Transparency {transparency} is > 1.0. Clamping to 1.0 (fully transparent). Input should ideally be 0.0-1.0.")
            return 1.0
        else: # val_to_convert < 0.0
            logger.debug(f"Transparency {transparency} is < 0.0. Clamping to 0.0 (opaque).")
            return 0.0
    return None

def sanitize_layer_name(name: str) -> str:
    """Sanitizes a layer name to be compliant with DXF/AutoCAD standards."""
    if not isinstance(name, str):
        logger.warning(f"Layer name input is not a string: {name}. Returning default name.")
        return "Default_Layer_Name"

    # Replace characters forbidden by AutoCAD in layer names
    # Forbidden characters: < > / \ " : ; ? * | = `
    forbidden_chars = r'[<>/\\":;?*|=`]' # Corrected regex
    sanitized = re.sub(forbidden_chars, '_', name)

    # DXF layer names also cannot have leading/trailing spaces (strictly).
    sanitized = sanitized.strip()

    if not sanitized: # If stripping makes the name empty, or it was empty to begin with.
        sanitized = "Empty_Layer_Name"

    # Truncate to 255 characters (common DXF limit for names)
    return sanitized[:255]

# --- Geometric Processing Utilities ---

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
            # Filter for supported geometry types that can be part of a simple feature
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

            # Attempt to union if multiple parts remain. This might be problematic if types are mixed
            # e.g. a Point and a Polygon. unary_union might handle some cases.
            try:
                logger.debug(f"Attempting unary_union on {len(parts)} extracted parts from GeometryCollection.")
                unioned_parts = unary_union(parts)
                if unioned_parts.is_empty:
                    logger.warning("Unary union of GeometryCollection parts resulted in empty geometry.")
                    return None
                return unioned_parts
            except Exception as e_union:
                logger.warning(f"Failed to unary_union parts of GeometryCollection from make_valid: {e_union}. Returning the collection itself if not empty.")
                # Fallback: if unary_union fails but collection has parts, maybe return the collection.
                # However, for feature processing, a GeometryCollection is often not desired.
                # Returning None might be safer if a single, simple geometry is expected.
                return None # Or valid_geom if GeometryCollection is an acceptable output in some contexts

        return valid_geom
    except Exception as e:
        logger.error(f"Error during make_valid_geometry for {geometry.wkt[:100]}...: {e}", exc_info=True)
        return None # Return None on failure

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
        return geometry # Operation only applies to polygons

    if geometry.is_empty:
        return None

    def process_polygon(poly: Polygon) -> Optional[Polygon]:
        if poly.is_empty:
            return None
        if preserve_islands:
            # If preserving islands, and the polygon has them, return it as is.
            # If it has no islands, it's already "preserved".
            return poly
        else:
            # Remove islands: reconstruct from exterior shell only
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
        # Union potentially multiple polygons resulting from processing a MultiPolygon
        final_geometry = unary_union(processed_polygons)
        if final_geometry.is_empty:
            return None
        return final_geometry
    except Exception as e:
        logger.error(f"Error during unary_union in remove_islands: {e}", exc_info=True)
        return None

# Ensure to add shapely to requirements.txt if not already there.
# Example usage (conceptual, actual use will be in operations):
# if config.make_valid_pre_buffer:
#     shapely_geom = make_valid_geometry(shapely_geom)
# if shapely_geom and (config.skip_islands or config.preserve_islands): # skip_islands implies !preserve_islands
#     shapely_geom = remove_islands_from_geometry(shapely_geom, preserve_islands=config.preserve_islands)

# --- DXFPlanner Geometry Models to/from Shapely Conversion Utilities ---
from dxfplanner.domain.models import geo_models as dxf_geo_models
from dxfplanner.domain.models.common import Coordinate

def convert_dxfplanner_geometry_to_shapely(
    dxfplanner_geom: Union[dxf_geo_models.Point, dxf_geo_models.Polyline, dxf_geo_models.Polygon]
) -> Optional[BaseGeometry]:
    """
    Converts a DXFPlanner geometry model (Point, Polyline, Polygon) to its Shapely equivalent.

    Args:
        dxfplanner_geom: An instance of DXFPlanner's Point, Polyline, or Polygon.

    Returns:
        The corresponding Shapely geometry object, or None if conversion fails.
    """
    try:
        if isinstance(dxfplanner_geom, dxf_geo_models.Point):
            return Point(dxfplanner_geom.coords.x, dxfplanner_geom.coords.y)
        elif isinstance(dxfplanner_geom, dxf_geo_models.Polyline):
            if not dxfplanner_geom.points or len(dxfplanner_geom.points) < 2:
                logger.warning("DXFPlanner Polyline has insufficient points for LineString. Min 2 required.")
                return None
            return LineString([(c.x, c.y) for c in dxfplanner_geom.points])
        elif isinstance(dxfplanner_geom, dxf_geo_models.Polygon):
            if not dxfplanner_geom.exterior or len(dxfplanner_geom.exterior) < 3:
                logger.warning("DXFPlanner Polygon has insufficient exterior points. Min 3 required.")
                return None

            shell = [(c.x, c.y) for c in dxfplanner_geom.exterior]
            holes = None
            if dxfplanner_geom.interiors:
                holes = []
                for interior_ring in dxfplanner_geom.interiors:
                    if interior_ring and len(interior_ring) >= 3:
                        holes.append([(c.x, c.y) for c in interior_ring])
                    else:
                        logger.warning("DXFPlanner Polygon interior ring has insufficient points. Min 3 required. Skipping interior.")
            return Polygon(shell, holes=holes)
        else:
            logger.warning(f"Unsupported DXFPlanner geometry type for Shapely conversion: {type(dxfplanner_geom)}")
            return None
    except Exception as e:
        logger.error(f"Error converting DXFPlanner geometry to Shapely: {e}", exc_info=True)
        return None

def convert_shapely_to_dxfplanner_geometry(
    shapely_geom: BaseGeometry
) -> Optional[Union[dxf_geo_models.Point, dxf_geo_models.Polyline, dxf_geo_models.Polygon]]:
    """
    Converts a simple Shapely geometry (Point, LineString, Polygon) to its DXFPlanner model equivalent.
    Multi-geometries (MultiPoint, MultiLineString, MultiPolygon) and GeometryCollections are NOT directly handled
    by this function and will return None; they should be iterated and converted individually if needed.

    Args:
        shapely_geom: A Shapely geometry object (Point, LineString, Polygon expected).

    Returns:
        An instance of DXFPlanner's Point, Polyline, or Polygon, or None if conversion fails
        or the input type is a multi-geometry or collection.
    """
    if shapely_geom is None or shapely_geom.is_empty:
        return None

    try:
        if isinstance(shapely_geom, Point):
            return dxf_geo_models.Point(coords=Coordinate(x=shapely_geom.x, y=shapely_geom.y))
        elif isinstance(shapely_geom, LineString):
            if len(shapely_geom.coords) < 2:
                 logger.warning("Shapely LineString has insufficient coordinates for DXFPlanner Polyline.")
                 return None
            return dxf_geo_models.Polyline(points=[Coordinate(x=x, y=y) for x, y in shapely_geom.coords])
        elif isinstance(shapely_geom, Polygon):
            if len(shapely_geom.exterior.coords) < 3:
                logger.warning("Shapely Polygon exterior has insufficient coordinates for DXFPlanner Polygon.")
                return None
            exterior_coords = [Coordinate(x=x, y=y) for x, y in shapely_geom.exterior.coords]
            interior_coord_lists = []
            if shapely_geom.interiors:
                for interior_ring in shapely_geom.interiors:
                    if len(interior_ring.coords) >= 3:
                        interior_coord_lists.append([Coordinate(x=x, y=y) for x, y in interior_ring.coords])
                    else:
                        logger.warning("Shapely Polygon interior ring has insufficient coordinates. Skipping interior.")
            return dxf_geo_models.Polygon(exterior=exterior_coords, interiors=interior_coord_lists if interior_coord_lists else None)
        elif isinstance(shapely_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
            logger.debug(f"Shapely MultiGeometry/Collection ({shapely_geom.geom_type}) received. Caller should iterate and convert parts.")
            return None # Or could raise an error, or attempt to convert first part?
        else:
            logger.warning(f"Unsupported Shapely geometry type for DXFPlanner conversion: {type(shapely_geom)}")
            return None
    except Exception as e:
        logger.error(f"Error converting Shapely geometry to DXFPlanner: {e}", exc_info=True)
        return None

# --- CRS Transformation Utility ---
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.ops import transform as shapely_transform_op

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

        # always_xy=True ensures (longitude, latitude) or (x, y) order
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

        # Apply the transformation to the geometry
        # The transform function from shapely.ops applies a function to all coordinates
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

# --- Explode Multipart Geometry Utility ---

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
        return # Yield nothing

    if isinstance(shapely_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
        if hasattr(shapely_geom, 'geoms'): # Standard for Multi* and GeometryCollection
            for part in shapely_geom.geoms:
                if part is not None and not part.is_empty:
                    # Recursively call for parts that might themselves be multi-part (e.g., nested GeometryCollection)
                    # or to handle the case where a part is a simple geometry.
                    yield from explode_multipart_geometry(part)
        else:
            # Should not happen for these types if they are valid
            logger.warning(f"MultiGeometry/Collection {shapely_geom.geom_type} without .geoms attribute? Yielding as is if simple.")
            if isinstance(shapely_geom, (Point, LineString, Polygon)):
                 yield shapely_geom
    elif isinstance(shapely_geom, (Point, LineString, Polygon)):
        yield shapely_geom # Already single part
    else:
        logger.warning(f"explode_multipart_geometry: Unsupported input geometry type: {type(shapely_geom)}. Skipping.")
        return # Yield nothing

# --- Shapely to DXFPlanner GeoModels Conversion Utility ---
from dxfplanner.domain.models import geo_models as dxf_geo_models # Already imported earlier for other converters

def convert_shapely_to_anygeogeometry(
    shapely_geom: BaseGeometry
) -> Optional[dxf_geo_models.AnyGeoGeometry]:
    """
    Converts a Shapely geometry to its DXFPlanner AnyGeoGeometry model equivalent.
    Handles Point, LineString, Polygon, and their Multi* versions, and GeometryCollection.

    Args:
        shapely_geom: A Shapely geometry object.

    Returns:
        An instance of a DXFPlanner geo_model (e.g., PointGeo, MultiPolygonGeo),
        or None if conversion fails or the input is None/empty.
    """
    if shapely_geom is None or shapely_geom.is_empty:
        return None

    try:
        if isinstance(shapely_geom, Point):
            return dxf_geo_models.PointGeo(coordinates=Coordinate(x=shapely_geom.x, y=shapely_geom.y))

        elif isinstance(shapely_geom, LineString):
            if len(shapely_geom.coords) < 2:
                logger.warning("Shapely LineString has insufficient coordinates for PolylineGeo.")
                return None
            return dxf_geo_models.PolylineGeo(coordinates=[Coordinate(x=x, y=y) for x, y in shapely_geom.coords])

        elif isinstance(shapely_geom, Polygon):
            if len(shapely_geom.exterior.coords) < 3:
                logger.warning("Shapely Polygon exterior has insufficient coordinates for PolygonGeo.")
                return None
            exterior_coords = [Coordinate(x=x, y=y) for x, y in shapely_geom.exterior.coords]
            interior_coord_lists = []
            if shapely_geom.interiors:
                for interior_ring in shapely_geom.interiors:
                    if len(interior_ring.coords) >= 3:
                        interior_coord_lists.append([Coordinate(x=x, y=y) for x, y in interior_ring.coords])
                    else:
                        logger.warning("Shapely Polygon interior ring has insufficient coordinates. Skipping interior.")
            # PolygonGeo.coordinates expects List[List[Coordinate]] (exterior, then interiors)
            all_rings = [exterior_coords] + interior_coord_lists
            return dxf_geo_models.PolygonGeo(coordinates=all_rings)

        elif isinstance(shapely_geom, MultiPoint):
            points = [Coordinate(x=p.x, y=p.y) for p in shapely_geom.geoms if isinstance(p, Point)]
            if not points and shapely_geom.geoms: # Had geoms but none were valid points
                 logger.warning("MultiPoint contains no valid Points after filtering.")
                 return None
            return dxf_geo_models.MultiPointGeo(coordinates=points)

        elif isinstance(shapely_geom, MultiLineString):
            lines_coords = []
            for line in shapely_geom.geoms:
                if isinstance(line, LineString) and len(line.coords) >= 2:
                    lines_coords.append([Coordinate(x=x, y=y) for x, y in line.coords])
            if not lines_coords and shapely_geom.geoms:
                 logger.warning("MultiLineString contains no valid LineStrings after filtering.")
                 return None
            return dxf_geo_models.MultiPolylineGeo(coordinates=lines_coords)

        elif isinstance(shapely_geom, MultiPolygon):
            polygons_coords_list = [] # List of List[List[Coordinate]]
            for poly in shapely_geom.geoms:
                if isinstance(poly, Polygon) and len(poly.exterior.coords) >=3:
                    exterior = [Coordinate(x=x, y=y) for x, y in poly.exterior.coords]
                    interiors = []
                    for int_ring in poly.interiors:
                        if len(int_ring.coords) >=3:
                            interiors.append([Coordinate(x=x, y=y) for x, y in int_ring.coords])
                    polygons_coords_list.append([exterior] + interiors)
            if not polygons_coords_list and shapely_geom.geoms:
                logger.warning("MultiPolygon contains no valid Polygons after filtering.")
                return None
            return dxf_geo_models.MultiPolygonGeo(coordinates=polygons_coords_list)

        elif isinstance(shapely_geom, GeometryCollection):
            converted_geoms = []
            for part_geom in shapely_geom.geoms:
                converted_part = convert_shapely_to_anygeogeometry(part_geom) # Recursive call
                if converted_part:
                    converted_geoms.append(converted_part)
            if not converted_geoms and shapely_geom.geoms:
                logger.warning("GeometryCollection contains no convertible geometries after filtering.")
                return None
            return dxf_geo_models.GeometryCollectionGeo(geometries=converted_geoms)

        else:
            logger.warning(f"Unsupported Shapely geometry type for AnyGeoGeometry conversion: {type(shapely_geom)}")
            return None
    except Exception as e:
        logger.error(f"Error converting Shapely geometry to AnyGeoGeometry model: {e}", exc_info=True)
        return None
