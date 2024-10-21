import geopandas as gpd
from matplotlib import pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
import os
from src.wmts_downloader import download_wmts_tiles, download_wms_tiles, process_and_stitch_tiles
from shapely.ops import unary_union, linemerge
from shapely.validation import make_valid, explain_validity
from shapely.geometry import LinearRing
import shutil
from src.contour_processor import process_contour
from owslib.wmts import WebMapTileService
import ezdxf
import pandas as pd
import math
from geopandas import GeoSeries
import re
from src.project_loader import project_loader

def _clean_geometry(all_layers, project_settings, crs, geometry):
        if isinstance(geometry, (gpd.GeoSeries, pd.Series)):
            return geometry.apply(_clean_single_geometry)
        else:
            return _clean_single_geometry(geometry)


def _clean_single_geometry(all_layers, project_settings, crs, geometry):
        # Ensure the geometry is valid
        geometry = make_valid(geometry)
        
        # Simplify the geometry
        simplify_tolerance = 0.01
        geometry = geometry.simplify(simplify_tolerance, preserve_topology=True)
        
        # Remove thin growths
        thin_growth_threshold = 0.0001  # Adjust this value as needed
        geometry = _remove_thin_growths(geometry, thin_growth_threshold)
        
        # Remove small polygons and attempt to remove slivers
        min_area = 1
        sliver_removal_distance = 0.05

        if isinstance(geometry, Polygon):
            return _clean_polygon(geometry, sliver_removal_distance, min_area)
        elif isinstance(geometry, MultiPolygon):
            cleaned_polygons = [_clean_polygon(poly, sliver_removal_distance, min_area) 
                                for poly in geometry.geoms]
            cleaned_polygons = [poly for poly in cleaned_polygons if poly is not None]
            if not cleaned_polygons:
                return None
            return MultiPolygon(cleaned_polygons)
        elif isinstance(geometry, GeometryCollection):
            cleaned_geoms = [_clean_single_geometry(geom) for geom in geometry.geoms]
            cleaned_geoms = [geom for geom in cleaned_geoms if geom is not None]
            if not cleaned_geoms:
                return None
            return GeometryCollection(cleaned_geoms)
        else:
            # For non-polygon geometries, just return the simplified version
            return geometry


def _remove_thin_growths(all_layers, project_settings, crs, geometry, threshold):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            # Apply a negative buffer followed by a positive buffer
            cleaned = geometry.buffer(-threshold).buffer(threshold)
            
            # Ensure the result is valid and of the same type as the input
            cleaned = make_valid(cleaned)
            if isinstance(geometry, Polygon) and isinstance(cleaned, MultiPolygon):
                # If a Polygon became a MultiPolygon, take the largest part
                largest = max(cleaned.geoms, key=lambda g: g.area)
                return largest
            return cleaned
        elif isinstance(geometry, GeometryCollection):
            cleaned_geoms = [_remove_thin_growths(geom, threshold) for geom in geometry.geoms]
            return GeometryCollection([g for g in cleaned_geoms if g is not None])
        else:
            # For non-polygon geometries, return as is
            return geometry


def _clean_polygon(all_layers, project_settings, crs, polygon, sliver_removal_distance, min_area):
        if polygon.is_empty:
            log_warning("Encountered an empty polygon during cleaning. Skipping.")
            return polygon

        cleaned_exterior = _clean_linear_ring(polygon.exterior, sliver_removal_distance)
        cleaned_interiors = [_clean_linear_ring(interior, sliver_removal_distance) for interior in polygon.interiors]

        # Filter out any empty interiors
        cleaned_interiors = [interior for interior in cleaned_interiors if not interior.is_empty]

        try:
            cleaned_polygon = Polygon(cleaned_exterior, cleaned_interiors)
        except Exception as e:
            log_warning(f"Error creating cleaned polygon: {str(e)}. Returning original polygon.")
            return polygon

        if cleaned_polygon.area < min_area:
            log_info(f"Polygon area ({cleaned_polygon.area}) is below minimum ({min_area}). Removing.")
            return None

        return cleaned_polygon


def _clean_linear_ring(all_layers, project_settings, crs, ring, sliver_removal_distance):
        if ring.is_empty:
            log_warning("Encountered an empty ring during cleaning. Skipping.")
            return ring

        coords = list(ring.coords)
        if len(coords) < 3:
            log_warning(f"Ring has fewer than 3 coordinates. Skipping cleaning. Coords: {coords}")
            return ring

        line = LineString(coords)
        try:
            merged = linemerge([line])
        except Exception as e:
            log_warning(f"Error during linemerge: {str(e)}. Returning original ring.")
            return ring

        if merged.geom_type == 'LineString':
            cleaned = merged.simplify(sliver_removal_distance)
        else:
            log_warning(f"Unexpected geometry type after merge: {merged.geom_type}. Returning original ring.")
            return ring

        if not cleaned.is_ring:
            log_warning("Cleaned geometry is not a ring. Attempting to close it.")
            cleaned = LineString(list(cleaned.coords) + [cleaned.coords[0]])

        return LinearRing(cleaned)


def _remove_small_polygons(all_layers, project_settings, crs, geometry, min_area):
        if isinstance(geometry, Polygon):
            if geometry.area >= min_area:
                return geometry
            else:
                return Polygon()
        elif isinstance(geometry, MultiPolygon):
            return MultiPolygon([poly for poly in geometry.geoms if poly.area >= min_area])
        else:
            return geometry
            

def _merge_close_vertices(all_layers, project_settings, crs, geometry, tolerance=0.1):
        def merge_points(geom):
            if isinstance(geom, LineString):
                coords = list(geom.coords)
                merged_coords = [coords[0]]
                for coord in coords[1:]:
                    if Point(coord).distance(Point(merged_coords[-1])) > tolerance:
                        merged_coords.append(coord)
                return LineString(merged_coords)
            elif isinstance(geom, Polygon):
                exterior_coords = merge_points(LineString(geom.exterior.coords)).coords
                interiors = [merge_points(LineString(interior.coords)).coords for interior in geom.interiors]
                return Polygon(exterior_coords, interiors)
            elif isinstance(geom, MultiPolygon):
                return MultiPolygon([merge_points(part) for part in geom.geoms])
            elif isinstance(geom, MultiLineString):
                return MultiLineString([merge_points(part) for part in geom.geoms])
            else:
                return geom

        if isinstance(geometry, GeometryCollection):
            return GeometryCollection([merge_points(geom) for geom in geometry.geoms])
        else:
            return merge_points(geometry)
        

def blunt_sharp_angles(all_layers, project_settings, crs, geometry, angle_threshold, blunt_distance):
        if isinstance(geometry, GeoSeries):
            return geometry.apply(lambda geom: blunt_sharp_angles(geom, angle_threshold, blunt_distance))
        
        log_info(f"Blunting angles for geometry: {geometry.wkt[:100]}...")
        if isinstance(geometry, Polygon):
            return _blunt_polygon_angles(geometry, angle_threshold, blunt_distance)
        elif isinstance(geometry, MultiPolygon):
            return MultiPolygon([_blunt_polygon_angles(poly, angle_threshold, blunt_distance) for poly in geometry.geoms])
        elif isinstance(geometry, (LineString, MultiLineString)):
            return _blunt_linestring_angles(geometry, angle_threshold, blunt_distance)
        elif isinstance(geometry, GeometryCollection):
            new_geoms = [blunt_sharp_angles(geom, angle_threshold, blunt_distance) for geom in geometry.geoms]
            return GeometryCollection(new_geoms)
        else:
            log_warning(f"Unsupported geometry type for blunting: {type(geometry)}")
            return geometry


def _blunt_polygon_angles(all_layers, project_settings, crs, polygon, angle_threshold, blunt_distance):
        log_info(f"Blunting polygon angles: {polygon.wkt[:100]}...")
        
        exterior_blunted = _blunt_ring(LinearRing(polygon.exterior.coords), angle_threshold, blunt_distance)
        interiors_blunted = [_blunt_ring(LinearRing(interior.coords), angle_threshold, blunt_distance) for interior in polygon.interiors]
        
        return Polygon(exterior_blunted, interiors_blunted)


def _blunt_ring(all_layers, project_settings, crs, ring, angle_threshold, blunt_distance):
        coords = list(ring.coords)
        new_coords = []
        
        for i in range(len(coords) - 1):  # -1 because the last point is the same as the first for rings
            prev_point = Point(coords[i-1])
            current_point = Point(coords[i])
            next_point = Point(coords[(i+1) % (len(coords)-1)])  # Wrap around for the last point
            
            # Skip processing if current point is identical to previous or next point
            if current_point.equals(prev_point) or current_point.equals(next_point):
                new_coords.append(coords[i])
                continue
            
            angle = _calculate_angle(prev_point, current_point, next_point)
            
            if angle is not None and angle < angle_threshold:
                log_info(f"Blunting angle at point {i}")
                blunted_points = _create_radical_blunt_segment(prev_point, current_point, next_point, blunt_distance)
                new_coords.extend(blunted_points)
            else:
                new_coords.append(coords[i])
        
        new_coords.append(new_coords[0])  # Close the ring
        return LinearRing(new_coords)


def _blunt_linestring_angles(all_layers, project_settings, crs, linestring, angle_threshold, blunt_distance):
        log_info(f"Blunting linestring angles: {linestring.wkt[:100]}...")
        if isinstance(linestring, MultiLineString):
            new_linestrings = [_blunt_linestring_angles(ls, angle_threshold, blunt_distance) for ls in linestring.geoms]
            return MultiLineString(new_linestrings)
        
        coords = list(linestring.coords)
        new_coords = [coords[0]]
        
        for i in range(1, len(coords) - 1):
            prev_point = Point(coords[i-1])
            current_point = Point(coords[i])
            next_point = Point(coords[i+1])
            
            angle = _calculate_angle(prev_point, current_point, next_point)
            
            if angle is not None and angle < angle_threshold:
                log_info(f"Blunting angle at point {i}")
                blunted_points = _create_radical_blunt_segment(prev_point, current_point, next_point, blunt_distance)
                new_coords.extend(blunted_points)
            else:
                new_coords.append(coords[i])
        
        new_coords.append(coords[-1])
        return LineString(new_coords)


def _calculate_angle(all_layers, project_settings, crs, p1, p2, p3):
        v1 = [p1.x - p2.x, p1.y - p2.y]
        v2 = [p3.x - p2.x, p3.y - p2.y]
        
        v1_mag = math.sqrt(v1[0]**2 + v1[1]**2)
        v2_mag = math.sqrt(v2[0]**2 + v2[1]**2)
        
        # Check if either vector has zero magnitude
        if v1_mag == 0 or v2_mag == 0:
            log_warning(f"Zero magnitude vector encountered: v1_mag={v1_mag}, v2_mag={v2_mag}")
            return None
        
        dot_product = v1[0] * v2[0] + v1[1] * v2[1]
        
        cos_angle = dot_product / (v1_mag * v2_mag)
        cos_angle = max(-1, min(1, cos_angle))  # Ensure the value is between -1 and 1
        angle_rad = math.acos(cos_angle)
        return math.degrees(angle_rad)


def _create_radical_blunt_segment(all_layers, project_settings, crs, p1, p2, p3, blunt_distance):
        log_info(f"Creating radical blunt segment for points: {p1}, {p2}, {p3}")
        v1 = [(p1.x - p2.x), (p1.y - p2.y)]
        v2 = [(p3.x - p2.x), (p3.y - p2.y)]
        
        # Normalize vectors
        v1_mag = math.sqrt(v1[0]**2 + v1[1]**2)
        v2_mag = math.sqrt(v2[0]**2 + v2[1]**2)
        
        # Check if either vector has zero magnitude
        if v1_mag == 0 or v2_mag == 0:
            log_warning(f"Zero magnitude vector encountered in blunt segment: v1_mag={v1_mag}, v2_mag={v2_mag}")
            return [p2.coords[0]]  # Return the original point if we can't create a blunt segment
        
        v1_norm = [v1[0] / v1_mag, v1[1] / v1_mag]
        v2_norm = [v2[0] / v2_mag, v2[1] / v2_mag]
        
        # Calculate points for the new segment
        point1 = (p2.x + v1_norm[0] * blunt_distance, p2.y + v1_norm[1] * blunt_distance)
        point2 = (p2.x + v2_norm[0] * blunt_distance, p2.y + v2_norm[1] * blunt_distance)
        
        log_info(f"Radical blunt segment created: {point1}, {point2}")
        return [point1, point2]
    

def _remove_empty_geometries(all_layers, project_settings, crs, geometry):
        if isinstance(geometry, gpd.GeoDataFrame):
            return geometry[~geometry.geometry.is_empty & geometry.geometry.notna()]
        elif isinstance(geometry, (MultiPolygon, MultiLineString)):
            return type(geometry)([geom for geom in geometry.geoms if not geom.is_empty])
        elif isinstance(geometry, (Polygon, LineString)):
            return None if geometry.is_empty else geometry
        else:
            return geometry

