"""
General geometric utilities.
"""
import re
from typing import Tuple, Union, Optional, Any, Iterator, List, Dict
from dxfplanner.core.logging_config import get_logger
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint, GeometryCollection
from shapely.validation import make_valid as shapely_make_valid
from shapely.ops import unary_union
from dxfplanner.domain.models import geo_models as dxf_geo_models
from dxfplanner.domain.models.geo_models import AnyGeoGeometry, GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo
from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfPoint, DxfLWPolyline, DxfHatch, DxfMText, DxfText, DxfInsert,
    HatchBoundaryPath, HatchEdgeType
)

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
    dxfplanner_geom: AnyGeoGeometry
) -> Optional[BaseGeometry]:
    """
    Converts a DXFPlanner geometry model (AnyGeoGeometry) to its Shapely equivalent.
    Handles Point, Polyline, Polygon, MultiPoint, MultiLineString, MultiPolygon,
    and GeometryCollection.

    Args:
        dxfplanner_geom: An instance of DXFPlanner's AnyGeoGeometry.

    Returns:
        The corresponding Shapely geometry object, or None if conversion fails.
    """
    if dxfplanner_geom is None:
        return None

    try:
        # Assuming Point, LineString, Polygon etc. are imported from shapely.geometry at the top
        if isinstance(dxfplanner_geom, dxf_geo_models.PointGeo):
            return Point(dxfplanner_geom.coordinates.x, dxfplanner_geom.coordinates.y)
        elif isinstance(dxfplanner_geom, dxf_geo_models.PolylineGeo):
            coords = [(c.x, c.y) for c in dxfplanner_geom.coordinates]
            if len(coords) < 2:
                logger.warning("DXFPlanner PolylineGeo has insufficient coordinates for Shapely LineString.")
                return None
            return LineString(coords)
        elif isinstance(dxfplanner_geom, dxf_geo_models.PolygonGeo):
            if not dxfplanner_geom.coordinates:
                logger.warning("DXFPlanner PolygonGeo has no coordinate rings.")
                return None
            exterior_coords = [(c.x, c.y) for c in dxfplanner_geom.coordinates[0]]
            if len(exterior_coords) < 3:
                logger.warning(f"DXFPlanner PolygonGeo exterior ring has insufficient ({len(exterior_coords)}) coordinates for Shapely Polygon. Need at least 3.")
                return None

            interior_coords_list = []
            if len(dxfplanner_geom.coordinates) > 1:
                for interior_ring_coords in dxfplanner_geom.coordinates[1:]:
                    coords = [(c.x, c.y) for c in interior_ring_coords]
                    if len(coords) >= 3:
                        interior_coords_list.append(coords)
                    else:
                        logger.warning(f"DXFPlanner PolygonGeo interior ring has insufficient ({len(coords)}) coordinates. Skipping interior.")
            return Polygon(exterior_coords, holes=interior_coords_list if interior_coords_list else None)

        elif isinstance(dxfplanner_geom, dxf_geo_models.MultiPointGeo):
            points = [(p.x, p.y) for p in dxfplanner_geom.coordinates]
            return MultiPoint(points)

        elif isinstance(dxfplanner_geom, dxf_geo_models.MultiPolylineGeo):
            lines_data = []
            for line_coord_list in dxfplanner_geom.coordinates:
                coords = [(c.x, c.y) for c in line_coord_list]
                if len(coords) >= 2:
                    lines_data.append(coords)
                else:
                    logger.warning("DXFPlanner MultiPolylineGeo part has insufficient coordinates. Skipping part.")
            return MultiLineString(lines_data)

        elif isinstance(dxfplanner_geom, dxf_geo_models.MultiPolygonGeo):
            polygons_data = []
            for poly_rings_coords_list in dxfplanner_geom.coordinates:
                if not poly_rings_coords_list:
                    logger.warning("DXFPlanner MultiPolygonGeo contains an empty polygon definition. Skipping part.")
                    continue

                shell_coords = [(c.x, c.y) for c in poly_rings_coords_list[0]]
                if len(shell_coords) < 3:
                    logger.warning(f"DXFPlanner MultiPolygonGeo part exterior has insufficient ({len(shell_coords)}) coordinates. Skipping part.")
                    continue

                holes_data = []
                if len(poly_rings_coords_list) > 1:
                    for interior_ring_coords in poly_rings_coords_list[1:]:
                        coords = [(c.x, c.y) for c in interior_ring_coords]
                        if len(coords) >= 3:
                            holes_data.append(coords)
                        else:
                            logger.warning(f"DXFPlanner MultiPolygonGeo part interior ring has insufficient ({len(coords)}) coordinates. Skipping interior.")
                polygons_data.append((shell_coords, holes_data if holes_data else []))
            return MultiPolygon(polygons_data)

        elif isinstance(dxfplanner_geom, dxf_geo_models.GeometryCollectionGeo):
            shapely_geoms = []
            for part_geom in dxfplanner_geom.geometries:
                converted_part = convert_dxfplanner_geometry_to_shapely(part_geom)
                if converted_part:
                    shapely_geoms.append(converted_part)
            return GeometryCollection(shapely_geoms)

        else:
            logger.warning(f"Unhandled DXFPlanner geometry type for Shapely conversion: {type(dxfplanner_geom).__name__} ({dxfplanner_geom})")
            return None
    except Exception as e:
        logger.error(f"Error converting DXFPlanner geometry ({type(dxfplanner_geom).__name__}) to Shapely: {e}", exc_info=True)
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

# --- NEW FUNCTION START ---
def convert_geo_feature_to_dxf_entities(
    geo_feature: GeoFeature,
    effective_style: Dict[str, Any]
) -> List[DxfEntity]:
    """
    Converts a GeoFeature (containing AnyGeoGeometry and properties) into a list
    of DxfEntity domain models based on the feature's geometry, properties, and
    the effective style.

    Args:
        geo_feature: The input GeoFeature.
        effective_style: A dictionary of resolved style attributes.

    Returns:
        A list of DxfEntity instances.
    """
    dxf_entities: List[DxfEntity] = []
    feature_geometry = geo_feature.geometry
    feature_properties = geo_feature.properties if geo_feature.properties else {}

    if feature_geometry is None:
        logger.warning(f"GeoFeature ID '{geo_feature.id}' has no geometry. Skipping DxfEntity conversion.")
        return dxf_entities

    # Common style attributes from effective_style
    layer_name = effective_style.get("layer_name", "0")
    aci_color = effective_style.get("color", 256) # 256 = ByLayer
    rgb_color = effective_style.get("rgb_color") # Optional
    linetype = effective_style.get("linetype") # Optional
    lineweight = effective_style.get("lineweight", -1) # -1 = ByLayer default
    transparency_val = effective_style.get("transparency_value") # Resolved 0.0-1.0 float

    # 1. Special handling for features intended as block inserts or text labels (based on properties)
    block_name_from_style = effective_style.get("block_name")
    text_content_from_style = effective_style.get("text_content")

    if isinstance(feature_geometry, PointGeo):
        if block_name_from_style:
            block_scale_x = effective_style.get("block_scale_x", 1.0)
            block_scale_y = effective_style.get("block_scale_y", 1.0)
            block_scale_z = effective_style.get("block_scale_z", 1.0)
            block_rotation = effective_style.get("block_rotation", 0.0)
            dxf_insert = DxfInsert(
                block_name=block_name_from_style,
                insert_x=feature_geometry.coordinates.x,
                insert_y=feature_geometry.coordinates.y,
                insert_z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
                x_scale=block_scale_x,
                y_scale=block_scale_y,
                z_scale=block_scale_z,
                rotation=block_rotation,
                layer=layer_name,
                color=aci_color,
                rgb=rgb_color,
                linetype=linetype,
                lineweight=lineweight,
                transparency=transparency_val
            )
            dxf_entities.append(dxf_insert)
            return dxf_entities

        elif feature_properties.get("__geometry_type__") == "LABEL" or text_content_from_style:
            text_string = text_content_from_style or feature_properties.get("label_text", "Default Text")
            text_height = effective_style.get("text_height", 1.0)
            text_rotation = feature_properties.get("label_rotation", effective_style.get("text_rotation", 0.0))
            text_style_name = effective_style.get("text_style_name", "Standard")
            attachment_point = effective_style.get("mtext_attachment_point", 1)
            width = effective_style.get("mtext_width")

            dxf_text_entity: Union[DxfMText, DxfText]
            if "\\P" in text_string or "\n" in text_string or width is not None:
                dxf_text_entity = DxfMText(
                    text=text_string,
                    insert_x=feature_geometry.coordinates.x,
                    insert_y=feature_geometry.coordinates.y,
                    insert_z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
                    height=text_height,
                    rotation=text_rotation,
                    style=text_style_name,
                    attachment_point=attachment_point,
                    width=width,
                    layer=layer_name,
                    color=aci_color,
                    rgb=rgb_color,
                    transparency=transparency_val
                )
            else:
                dxf_text_entity = DxfText(
                    text=text_string,
                    insert_x=feature_geometry.coordinates.x,
                    insert_y=feature_geometry.coordinates.y,
                    insert_z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
                    height=text_height,
                    rotation=text_rotation,
                    style=text_style_name,
                    layer=layer_name,
                    color=aci_color,
                    rgb=rgb_color,
                    transparency=transparency_val
                )
            dxf_entities.append(dxf_text_entity)
            return dxf_entities

    # 2. Standard geometry conversion if not handled above
    if isinstance(feature_geometry, PointGeo): # This will only be reached if not a block/label
        dxf_point = DxfPoint(
            x=feature_geometry.coordinates.x,
            y=feature_geometry.coordinates.y,
            z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
            layer=layer_name,
            color=aci_color,
            rgb=rgb_color,
            linetype=linetype
        )
        dxf_entities.append(dxf_point)

    elif isinstance(feature_geometry, PolylineGeo):
        points = [(c.x, c.y, c.z if c.z is not None else 0.0) for c in feature_geometry.coordinates]
        if len(points) >= 2:
            is_closed = False
            if len(points) > 2 and points[0] == points[-1]:
                is_closed = True

            dxf_lwpolyline = DxfLWPolyline(
                points=points,
                closed=is_closed,
                layer=layer_name,
                color=aci_color,
                rgb=rgb_color,
                linetype=linetype,
                lineweight=lineweight,
                transparency=transparency_val
            )
            dxf_entities.append(dxf_lwpolyline)
        else:
            logger.warning(f"PolylineGeo for feature ID '{geo_feature.id}' has < 2 points. Cannot create DxfLWPolyline.")

    elif isinstance(feature_geometry, PolygonGeo):
        hatch_pattern_name = effective_style.get("hatch_pattern_name")
        hatch_scale = effective_style.get("hatch_scale", 1.0)
        hatch_angle = effective_style.get("hatch_angle", 0.0)
        draw_hatch_boundary = effective_style.get("draw_hatch_boundary", True)

        all_rings_coords = feature_geometry.coordinates

        if not all_rings_coords or not all_rings_coords[0]:
            logger.warning(f"PolygonGeo for feature ID '{geo_feature.id}' has no exterior ring. Cannot process.")
            return dxf_entities

        boundary_paths_data: List[HatchBoundaryPath] = []
        exterior_ring_coords = [(c.x, c.y) for c in all_rings_coords[0]]
        if len(exterior_ring_coords) >= 3:
            if exterior_ring_coords[0] != exterior_ring_coords[-1]:
                 exterior_ring_coords.append(exterior_ring_coords[0])
            boundary_paths_data.append(HatchBoundaryPath(vertices=exterior_ring_coords, type=HatchEdgeType.POLYLINE.value)) # Use .value for enum

            if len(all_rings_coords) > 1:
                for interior_ring_domain_coords in all_rings_coords[1:]:
                    interior_ring_shapely_coords = [(c.x, c.y) for c in interior_ring_domain_coords]
                    if len(interior_ring_shapely_coords) >= 3:
                        if interior_ring_shapely_coords[0] != interior_ring_shapely_coords[-1]:
                            interior_ring_shapely_coords.append(interior_ring_shapely_coords[0])
                        boundary_paths_data.append(HatchBoundaryPath(vertices=interior_ring_shapely_coords, type=HatchEdgeType.POLYLINE.value)) # Use .value
        else:
            logger.warning(f"PolygonGeo exterior for '{geo_feature.id}' has < 3 points. Cannot form hatch path.")

        if hatch_pattern_name and boundary_paths_data:
            dxf_hatch = DxfHatch(
                pattern_name=hatch_pattern_name,
                scale=hatch_scale,
                angle=hatch_angle,
                boundary_paths=boundary_paths_data,
                layer=layer_name,
                color=aci_color,
                rgb=rgb_color,
                transparency=transparency_val
            )
            dxf_entities.append(dxf_hatch)

        if draw_hatch_boundary and all_rings_coords and all_rings_coords[0] and len(all_rings_coords[0]) >=2 :
            exterior_points_for_lw = [(c.x, c.y, c.z if c.z is not None else 0.0) for c in all_rings_coords[0]]
            is_closed_lw = False
            if len(exterior_points_for_lw) > 2 and exterior_points_for_lw[0] == exterior_points_for_lw[-1]:
                is_closed_lw = True

            boundary_polyline = DxfLWPolyline(
                points=exterior_points_for_lw,
                closed=is_closed_lw,
                layer=layer_name,
                color=aci_color,
                rgb=rgb_color,
                linetype=linetype,
                lineweight=lineweight,
                transparency=transparency_val
            )
            dxf_entities.append(boundary_polyline)
            # Note: Does not draw boundaries for holes explicitly here, DxfWriter might.

    elif isinstance(feature_geometry, (MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo)):
        if isinstance(feature_geometry, MultiPointGeo):
            for coord in feature_geometry.coordinates:
                part_feature = GeoFeature(id=f"{geo_feature.id}_mpt_part", geometry=PointGeo(coordinates=coord), properties=feature_properties)
                dxf_entities.extend(convert_geo_feature_to_dxf_entities(part_feature, effective_style))
        elif isinstance(feature_geometry, MultiPolylineGeo):
            for coord_list in feature_geometry.coordinates:
                part_feature = GeoFeature(id=f"{geo_feature.id}_mpl_part", geometry=PolylineGeo(coordinates=coord_list), properties=feature_properties)
                dxf_entities.extend(convert_geo_feature_to_dxf_entities(part_feature, effective_style))
        elif isinstance(feature_geometry, MultiPolygonGeo):
             for poly_coord_rings in feature_geometry.coordinates:
                part_feature = GeoFeature(id=f"{geo_feature.id}_mpg_part", geometry=PolygonGeo(coordinates=poly_coord_rings), properties=feature_properties)
                dxf_entities.extend(convert_geo_feature_to_dxf_entities(part_feature, effective_style))
        elif isinstance(feature_geometry, GeometryCollectionGeo):
             for i, part_geom in enumerate(feature_geometry.geometries):
                 part_feature = GeoFeature(id=f"{geo_feature.id}_gc_part{i}", geometry=part_geom, properties=feature_properties)
                 dxf_entities.extend(convert_geo_feature_to_dxf_entities(part_feature, effective_style))
    else:
        logger.warning(f"Unsupported AnyGeoGeometry type for DxfEntity conversion: {type(feature_geometry).__name__} for feature ID '{geo_feature.id}'")

    return dxf_entities

# --- END NEW FUNCTION ---
