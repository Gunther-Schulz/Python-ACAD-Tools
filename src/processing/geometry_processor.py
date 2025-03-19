"""
Geometry processing functionality for OLADPP.
"""
from typing import Dict, Any, Optional, List, Union
from ..core.exceptions import ProcessingError
import ezdxf
from ezdxf.entities import DXFEntity, DXFGraphic
from ezdxf.lldxf.const import DXFValueError
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, mapping, shape


class GeometryProcessor:
    """Handles geometry operations and transformations."""

    def __init__(self):
        """Initialize the geometry processor."""
        self._geometries: Dict[str, Dict[str, Any]] = {}

    def get_geometry(self, layer_name: str) -> Optional[object]:
        """
        Get geometry for a specific layer.

        Args:
            layer_name: Name of the layer

        Returns:
            Layer geometry or None if not found
        """
        if layer_name in self._geometries:
            return self._geometries[layer_name].get('geometry')
        return None

    def set_geometry(self, layer_name: str, geometry: object) -> None:
        """
        Set geometry for a specific layer.

        Args:
            layer_name: Name of the layer
            geometry: Geometry to set
        """
        if layer_name in self._geometries:
            self._geometries[layer_name]['geometry'] = geometry
        else:
            self._geometries[layer_name] = {'geometry': geometry}

    def create_buffer(
        self,
        geometry: object,
        distance: float = 0.0,
        mode: str = 'round',
        join_style: str = 'round'
    ) -> object:
        """
        Create a buffer around a geometry.

        Args:
            geometry: Input geometry
            distance: Buffer distance
            mode: Buffer mode ('round', 'flat', 'square')
            join_style: Join style ('round', 'mitre', 'bevel')

        Returns:
            Buffered geometry
        """
        try:
            # Convert to Shapely geometry if needed
            if not isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry = shape(geometry)

            # Create buffer
            buffered = geometry.buffer(
                distance,
                join_style=getattr(join_style, 'upper', 'ROUND'),
                cap_style=getattr(mode, 'upper', 'ROUND')
            )

            # Convert back to GeoJSON if needed
            if not isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                return mapping(buffered)

            return buffered

        except Exception as e:
            raise ProcessingError(f"Error creating buffer: {str(e)}")

    def create_difference(self, geometry1: object, geometry2: object) -> object:
        """
        Create the difference between two geometries.

        Args:
            geometry1: First geometry
            geometry2: Second geometry

        Returns:
            Difference geometry
        """
        try:
            # Convert to Shapely geometries if needed
            if not isinstance(geometry1, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry1 = shape(geometry1)
            if not isinstance(geometry2, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry2 = shape(geometry2)

            # Create difference
            difference = geometry1.difference(geometry2)

            # Convert back to GeoJSON if needed
            if not isinstance(geometry1, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                return mapping(difference)

            return difference

        except Exception as e:
            raise ProcessingError(f"Error creating difference: {str(e)}")

    def create_intersection(self, geometry1: object, geometry2: object) -> object:
        """
        Create the intersection of two geometries.

        Args:
            geometry1: First geometry
            geometry2: Second geometry

        Returns:
            Intersection geometry
        """
        try:
            # Convert to Shapely geometries if needed
            if not isinstance(geometry1, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry1 = shape(geometry1)
            if not isinstance(geometry2, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry2 = shape(geometry2)

            # Create intersection
            intersection = geometry1.intersection(geometry2)

            # Convert back to GeoJSON if needed
            if not isinstance(geometry1, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                return mapping(intersection)

            return intersection

        except Exception as e:
            raise ProcessingError(f"Error creating intersection: {str(e)}")

    def create_union(self, geometry1: object, geometry2: object) -> object:
        """
        Create the union of two geometries.

        Args:
            geometry1: First geometry
            geometry2: Second geometry

        Returns:
            Union geometry
        """
        try:
            # Convert to Shapely geometries if needed
            if not isinstance(geometry1, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry1 = shape(geometry1)
            if not isinstance(geometry2, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry2 = shape(geometry2)

            # Create union
            union = geometry1.union(geometry2)

            # Convert back to GeoJSON if needed
            if not isinstance(geometry1, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                return mapping(union)

            return union

        except Exception as e:
            raise ProcessingError(f"Error creating union: {str(e)}")

    def create_smooth(self, geometry: object, tolerance: float = 0.1) -> object:
        """
        Smooth a geometry.

        Args:
            geometry: Input geometry
            tolerance: Smoothing tolerance

        Returns:
            Smoothed geometry
        """
        try:
            # Convert to Shapely geometry if needed
            if not isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                geometry = shape(geometry)

            # Smooth geometry
            smoothed = geometry.simplify(tolerance, preserve_topology=True)

            # Convert back to GeoJSON if needed
            if not isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
                return mapping(smoothed)

            return smoothed

        except Exception as e:
            raise ProcessingError(f"Error smoothing geometry: {str(e)}")

    def merge_geometries(
        self,
        geometries: List[List[DXFEntity]]
    ) -> List[DXFEntity]:
        """
        Merge multiple geometries into one.

        Args:
            geometries: List of geometry lists to merge

        Returns:
            List of merged DXF entities
        """
        result = []
        for geometry in geometries:
            result.extend(geometry)
        return result

    def filter_geometry(
        self,
        geometry: List[DXFEntity],
        criteria: Dict[str, Any]
    ) -> List[DXFEntity]:
        """
        Filter geometry based on criteria.

        Args:
            geometry: List of DXF entities to filter
            criteria: Filter criteria

        Returns:
            List of filtered DXF entities
        """
        # Implementation will be added when we implement filtering
        return geometry

    def convert_to_dxf_entities(
        self,
        geometry: Any
    ) -> List[DXFEntity]:
        """
        Convert geometry to DXF entities.

        Args:
            geometry: Geometry to convert

        Returns:
            List of DXF entities
        """
        # Implementation will be added when we implement conversion
        return []

    def convert_from_dxf_entities(
        self,
        entities: List[DXFEntity]
    ) -> Any:
        """
        Convert DXF entities to geometry.

        Args:
            entities: List of DXF entities to convert

        Returns:
            Converted geometry
        """
        # Implementation will be added when we implement conversion
        return None
