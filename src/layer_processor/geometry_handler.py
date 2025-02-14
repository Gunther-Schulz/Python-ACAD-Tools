"""Module for handling geometry operations."""

import math
import numpy as np
from shapely.geometry import Point, LineString
from src.core.utils import log_debug, log_warning, log_error

class GeometryHandler:
    def __init__(self, layer_processor):
        try:
            self.layer_processor = layer_processor
            log_debug("Geometry handler initialized successfully")
        except Exception as e:
            log_error(f"Error initializing geometry handler: {str(e)}")
            raise

    def standardize_layer_crs(self, layer_name, geometry_or_gdf):
        """Standardize the CRS of a layer."""
        try:
            if hasattr(geometry_or_gdf, 'crs'):
                if geometry_or_gdf.crs != self.layer_processor.crs:
                    log_debug(f"Converting CRS for layer {layer_name} from {geometry_or_gdf.crs} to {self.layer_processor.crs}")
                    return geometry_or_gdf.to_crs(self.layer_processor.crs)
                log_debug(f"Layer {layer_name} already in correct CRS")
            return geometry_or_gdf
        except Exception as e:
            log_error(f"Error standardizing CRS for layer {layer_name}: {str(e)}")
            raise

    def blunt_sharp_angles(self, geometry, angle_threshold, blunt_distance):
        """Blunt sharp angles in a geometry."""
        try:
            log_debug(f"Blunting sharp angles with threshold {angle_threshold} and distance {blunt_distance}")
            
            if hasattr(geometry, 'geoms'):
                return type(geometry)([self.blunt_sharp_angles(g, angle_threshold, blunt_distance) for g in geometry.geoms])
            elif hasattr(geometry, 'exterior'):
                return self._blunt_polygon_angles(geometry, angle_threshold, blunt_distance)
            elif isinstance(geometry, LineString):
                return self._blunt_linestring_angles(geometry, angle_threshold, blunt_distance)
                
            log_debug("Geometry type does not require blunting")
            return geometry
            
        except Exception as e:
            log_error(f"Error blunting sharp angles: {str(e)}")
            return geometry

    def _blunt_polygon_angles(self, polygon, angle_threshold, blunt_distance):
        """Blunt sharp angles in a polygon."""
        try:
            log_debug("Processing polygon angles")
            exterior = self._blunt_ring(list(polygon.exterior.coords), angle_threshold, blunt_distance)
            interiors = [self._blunt_ring(list(interior.coords), angle_threshold, blunt_distance) 
                        for interior in polygon.interiors]
            return type(polygon)(shell=exterior, holes=interiors)
        except Exception as e:
            log_error(f"Error blunting polygon angles: {str(e)}")
            return polygon

    def _blunt_ring(self, coords, angle_threshold, blunt_distance):
        """Blunt sharp angles in a ring of coordinates."""
        try:
            if len(coords) < 4:  # Need at least 4 points for a closed ring
                log_debug("Ring has too few points for blunting")
                return coords

            result = []
            n = len(coords) - 1  # Last point is same as first for closed rings
            blunted_count = 0
            
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
                    blunted_count += 1
                else:
                    if i == 0:
                        result.append(p1)
                    result.append(p2)

            # Close the ring
            result.append(result[0])
            log_debug(f"Blunted {blunted_count} angles in ring")
            return result
            
        except Exception as e:
            log_error(f"Error blunting ring angles: {str(e)}")
            return coords

    def _blunt_linestring_angles(self, linestring, angle_threshold, blunt_distance):
        """Blunt sharp angles in a linestring."""
        try:
            coords = list(linestring.coords)
            if len(coords) < 3:
                log_debug("Linestring has too few points for blunting")
                return linestring

            result = [coords[0]]
            blunted_count = 0
            
            for i in range(1, len(coords) - 1):
                p1 = coords[i - 1]
                p2 = coords[i]
                p3 = coords[i + 1]
                
                angle = self._calculate_angle(p1, p2, p3)
                
                if angle < angle_threshold:
                    # Create blunted corner
                    start_point, end_point = self._create_radical_blunt_segment(p1, p2, p3, blunt_distance)
                    result.extend([start_point, end_point])
                    blunted_count += 1
                else:
                    result.append(p2)

            result.append(coords[-1])
            log_debug(f"Blunted {blunted_count} angles in linestring")
            return LineString(result)
            
        except Exception as e:
            log_error(f"Error blunting linestring angles: {str(e)}")
            return linestring

    def _calculate_angle(self, p1, p2, p3):
        """Calculate angle between three points in degrees."""
        try:
            v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
            v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
            
            v1_norm = np.linalg.norm(v1)
            v2_norm = np.linalg.norm(v2)
            
            if v1_norm == 0 or v2_norm == 0:
                log_debug("Zero-length vector detected, returning 180 degrees")
                return 180.0
            
            cos_angle = np.dot(v1, v2) / (v1_norm * v2_norm)
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            angle_rad = np.arccos(cos_angle)
            angle_deg = math.degrees(angle_rad)
            
            log_debug(f"Calculated angle: {angle_deg:.2f} degrees")
            return angle_deg
            
        except Exception as e:
            log_error(f"Error calculating angle: {str(e)}")
            return 180.0  # Return straight angle as fallback

    def _create_radical_blunt_segment(self, p1, p2, p3, blunt_distance):
        """Create a blunted segment between three points."""
        try:
            # Calculate vectors
            v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
            v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
            
            # Normalize vectors
            v1_norm = np.linalg.norm(v1)
            v2_norm = np.linalg.norm(v2)
            
            if v1_norm == 0 or v2_norm == 0:
                log_warning("Zero-length vector detected in blunt segment creation")
                return p2, p2
            
            v1_unit = v1 / v1_norm
            v2_unit = v2 / v2_norm
            
            # Calculate points at blunt_distance along each vector from p2
            start_point = (p2[0] + v1_unit[0] * blunt_distance, 
                         p2[1] + v1_unit[1] * blunt_distance)
            end_point = (p2[0] + v2_unit[0] * blunt_distance,
                        p2[1] + v2_unit[1] * blunt_distance)
            
            log_debug(f"Created blunt segment: {start_point} -> {end_point}")
            return start_point, end_point
            
        except Exception as e:
            log_error(f"Error creating blunt segment: {str(e)}")
            return p2, p2  # Return original point as fallback 