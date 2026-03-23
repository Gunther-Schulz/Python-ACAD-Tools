import math

import geopandas as gpd
from geopandas import GeoSeries
from shapely.geometry import (
    Polygon, MultiPolygon, LineString, MultiLineString,
    GeometryCollection, Point, LinearRing
)

from src.operations.registry import register_operation
from src.utils import log_debug, log_warning


@register_operation('bluntAngles', description='Blunt sharp angles on polygon/line vertices')
def create_blunt_angles_layer(all_layers, project_settings, crs, layer_name, operation):
    """Blunt sharp angles below a threshold by inserting chamfer segments."""
    angle_threshold = operation.get('angleThreshold', 45)
    blunt_distance = operation.get('distance', 0.5)

    if layer_name not in all_layers or all_layers[layer_name] is None:
        log_warning(f"Layer '{layer_name}' not found for blunting angles")
        return None

    gdf = all_layers[layer_name]
    log_debug(f"Applying blunt angles to layer '{layer_name}' with threshold {angle_threshold} and distance {blunt_distance}")

    blunted = gdf.geometry.apply(lambda geom: _blunt_sharp_angles(geom, angle_threshold, blunt_distance))
    result = gdf.copy()
    result.geometry = blunted
    return result


def _blunt_sharp_angles(geometry, angle_threshold, blunt_distance):
    if isinstance(geometry, GeoSeries):
        return geometry.apply(lambda geom: _blunt_sharp_angles(geom, angle_threshold, blunt_distance))
    if isinstance(geometry, Polygon):
        return _blunt_polygon(geometry, angle_threshold, blunt_distance)
    elif isinstance(geometry, MultiPolygon):
        return MultiPolygon([_blunt_polygon(p, angle_threshold, blunt_distance) for p in geometry.geoms])
    elif isinstance(geometry, (LineString, MultiLineString)):
        return _blunt_linestring(geometry, angle_threshold, blunt_distance)
    elif isinstance(geometry, GeometryCollection):
        return GeometryCollection([_blunt_sharp_angles(g, angle_threshold, blunt_distance) for g in geometry.geoms])
    else:
        return geometry


def _blunt_polygon(polygon, angle_threshold, blunt_distance):
    exterior = _blunt_ring(LinearRing(polygon.exterior.coords), angle_threshold, blunt_distance)
    interiors = [_blunt_ring(LinearRing(i.coords), angle_threshold, blunt_distance) for i in polygon.interiors]
    return Polygon(exterior, interiors)


def _blunt_ring(ring, angle_threshold, blunt_distance):
    coords = list(ring.coords)
    new_coords = []
    for i in range(len(coords) - 1):
        prev = Point(coords[i - 1])
        curr = Point(coords[i])
        nxt = Point(coords[(i + 1) % (len(coords) - 1)])
        if curr.equals(prev) or curr.equals(nxt):
            new_coords.append(coords[i])
            continue
        angle = _calculate_angle(prev, curr, nxt)
        if angle is not None and angle < angle_threshold:
            new_coords.extend(_create_blunt_segment(prev, curr, nxt, blunt_distance))
        else:
            new_coords.append(coords[i])
    new_coords.append(new_coords[0])
    return LinearRing(new_coords)


def _blunt_linestring(linestring, angle_threshold, blunt_distance):
    if isinstance(linestring, MultiLineString):
        return MultiLineString([_blunt_linestring(ls, angle_threshold, blunt_distance) for ls in linestring.geoms])
    coords = list(linestring.coords)
    new_coords = [coords[0]]
    for i in range(1, len(coords) - 1):
        prev = Point(coords[i - 1])
        curr = Point(coords[i])
        nxt = Point(coords[i + 1])
        angle = _calculate_angle(prev, curr, nxt)
        if angle is not None and angle < angle_threshold:
            new_coords.extend(_create_blunt_segment(prev, curr, nxt, blunt_distance))
        else:
            new_coords.append(coords[i])
    new_coords.append(coords[-1])
    return LineString(new_coords)


def _calculate_angle(p1, p2, p3):
    v1 = [p1.x - p2.x, p1.y - p2.y]
    v2 = [p3.x - p2.x, p3.y - p2.y]
    v1_mag = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    v2_mag = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if v1_mag == 0 or v2_mag == 0:
        return None
    cos_angle = max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (v1_mag * v2_mag)))
    return math.degrees(math.acos(cos_angle))


def _create_blunt_segment(p1, p2, p3, blunt_distance):
    v1 = [p1.x - p2.x, p1.y - p2.y]
    v2 = [p3.x - p2.x, p3.y - p2.y]
    v1_mag = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    v2_mag = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if v1_mag == 0 or v2_mag == 0:
        return [p2.coords[0]]
    v1_n = [v1[0] / v1_mag, v1[1] / v1_mag]
    v2_n = [v2[0] / v2_mag, v2[1] / v2_mag]
    return [
        (p2.x + v1_n[0] * blunt_distance, p2.y + v1_n[1] * blunt_distance),
        (p2.x + v2_n[0] * blunt_distance, p2.y + v2_n[1] * blunt_distance),
    ]
