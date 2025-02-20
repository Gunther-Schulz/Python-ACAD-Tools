"""Module for handling geometry operations."""

import math
import numpy as np
from shapely.geometry import Point, LineString

class GeometryHandler:
    def __init__(self, layer_processor):
        self.layer_processor = layer_processor

    def standardize_layer_crs(self, layer_name, geometry_or_gdf):
        """Standardize the CRS of a layer."""
        if hasattr(geometry_or_gdf, 'crs'):
            if geometry_or_gdf.crs != self.layer_processor.crs:
                return geometry_or_gdf.to_crs(self.layer_processor.crs)
        return geometry_or_gdf

    def blunt_sharp_angles(self, geometry, angle_threshold, blunt_distance):
        """Blunt sharp angles in a geometry."""
        if hasattr(geometry, 'geoms'):
            return type(geometry)([self.blunt_sharp_angles(g, angle_threshold, blunt_distance) for g in geometry.geoms])
        elif hasattr(geometry, 'exterior'):
            return self._blunt_polygon_angles(geometry, angle_threshold, blunt_distance)
        elif isinstance(geometry, LineString):
            return self._blunt_linestring_angles(geometry, angle_threshold, blunt_distance)
        return geometry

    def _blunt_polygon_angles(self, polygon, angle_threshold, blunt_distance):
        """Blunt sharp angles in a polygon."""
        exterior = self._blunt_ring(list(polygon.exterior.coords), angle_threshold, blunt_distance)
        interiors = [self._blunt_ring(list(interior.coords), angle_threshold, blunt_distance) 
                    for interior in polygon.interiors]
        return type(polygon)(shell=exterior, holes=interiors)

    def _blunt_ring(self, coords, angle_threshold, blunt_distance):
        """Blunt sharp angles in a ring of coordinates."""
        if len(coords) < 4:  # Need at least 4 points for a closed ring
            return coords

        result = []
        n = len(coords) - 1  # Last point is same as first for closed rings
        
        for i in range(n):
            p1 = coords[i]
            p2 = coords[(i + 1) % n]
            p3 = coords[(i + 2) % n]
            
            angle = self._calculate_angle(p1, p2, p3)
            
            if angle < angle_threshold:
                # Create blunted corner
                start_point, end_point = self._create_radical_blunt_segment(p1, p2, p3, blunt_distance)
                if i == 0:
                    result.append(p1)
                result.extend([start_point, end_point])
            else:
                if i == 0:
                    result.append(p1)
                result.append(p2)

        # Close the ring
        result.append(result[0])
        return result

    def _blunt_linestring_angles(self, linestring, angle_threshold, blunt_distance):
        """Blunt sharp angles in a linestring."""
        coords = list(linestring.coords)
        if len(coords) < 3:
            return linestring

        result = [coords[0]]
        
        for i in range(1, len(coords) - 1):
            p1 = coords[i - 1]
            p2 = coords[i]
            p3 = coords[i + 1]
            
            angle = self._calculate_angle(p1, p2, p3)
            
            if angle < angle_threshold:
                # Create blunted corner
                start_point, end_point = self._create_radical_blunt_segment(p1, p2, p3, blunt_distance)
                result.extend([start_point, end_point])
            else:
                result.append(p2)

        result.append(coords[-1])
        return LineString(result)

    def _calculate_angle(self, p1, p2, p3):
        """Calculate angle between three points in degrees."""
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        
        v1_norm = np.linalg.norm(v1)
        v2_norm = np.linalg.norm(v2)
        
        if v1_norm == 0 or v2_norm == 0:
            return 180.0
        
        cos_angle = np.dot(v1, v2) / (v1_norm * v2_norm)
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        angle_rad = np.arccos(cos_angle)
        return math.degrees(angle_rad)

    def _create_radical_blunt_segment(self, p1, p2, p3, blunt_distance):
        """Create a blunted segment between three points."""
        # Calculate vectors
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        
        # Normalize vectors
        v1_norm = np.linalg.norm(v1)
        v2_norm = np.linalg.norm(v2)
        
        if v1_norm == 0 or v2_norm == 0:
            return p2, p2
        
        v1_unit = v1 / v1_norm
        v2_unit = v2 / v2_norm
        
        # Calculate points at blunt_distance along each vector from p2
        start_point = (p2[0] + v1_unit[0] * blunt_distance, 
                      p2[1] + v1_unit[1] * blunt_distance)
        end_point = (p2[0] + v2_unit[0] * blunt_distance,
                    p2[1] + v2_unit[1] * blunt_distance)
        
        return start_point, end_point 