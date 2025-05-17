"""
Conversion utilities between DXFPlanner GeoModels and Shapely geometry objects.
"""
from typing import Optional
from dxfplanner.core.logging_config import get_logger
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon, GeometryCollection

from dxfplanner.domain.models import geo_models as dxf_geo_models
from dxfplanner.domain.models.common import Coordinate

logger = get_logger(__name__)

def convert_dxfplanner_geometry_to_shapely(
    dxfplanner_geom: dxf_geo_models.AnyGeoGeometry
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
            all_rings = [exterior_coords] + interior_coord_lists
            return dxf_geo_models.PolygonGeo(coordinates=all_rings)
        elif isinstance(shapely_geom, MultiPoint):
            points = [Coordinate(x=p.x, y=p.y) for p in shapely_geom.geoms if isinstance(p, Point)]
            if not points and shapely_geom.geoms:
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
            polygons_coords_list = []
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
