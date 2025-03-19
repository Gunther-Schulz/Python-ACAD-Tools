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

    def _ensure_shapely_geometry(self, geometry: object) -> object:
        """
        Ensure geometry is a Shapely geometry type.

        Args:
            geometry: Input geometry

        Returns:
            Shapely geometry
        """
        if not isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
            return shape(geometry)
        return geometry

    def _convert_if_needed(self, geometry: object, original: object) -> object:
        """
        Convert geometry back to original type if needed.

        Args:
            geometry: Geometry to convert
            original: Original geometry type to match

        Returns:
            Converted geometry
        """
        if not isinstance(original, (Polygon, MultiPolygon, LineString, MultiLineString, Point)):
            return mapping(geometry)
        return geometry

    def _apply_geometry_operation(
        self,
        operation_name: str,
        operation_func: callable,
        geometry: object,
        *args,
        **kwargs
    ) -> object:
        """
        Apply a geometry operation with proper type handling.

        Args:
            operation_name: Name of the operation for error messages
            operation_func: Function to apply the operation
            geometry: Input geometry
            *args: Additional arguments for the operation
            **kwargs: Additional keyword arguments for the operation

        Returns:
            Result of the operation
        """
        try:
            # Convert to Shapely geometry if needed
            shapely_geom = self._ensure_shapely_geometry(geometry)

            # Apply operation
            result = operation_func(shapely_geom, *args, **kwargs)

            return self._convert_if_needed(result, geometry)

        except Exception as e:
            raise ProcessingError(f"Error in {operation_name}: {str(e)}")

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
        def buffer_op(geom, dist, m, js):
            return geom.buffer(
                dist,
                join_style=getattr(js, 'upper', 'ROUND'),
                cap_style=getattr(m, 'upper', 'ROUND')
            )

        return self._apply_geometry_operation(
            'buffer',
            buffer_op,
            geometry,
            distance,
            mode,
            join_style
        )

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
            shapely_geom1 = self._ensure_shapely_geometry(geometry1)
            shapely_geom2 = self._ensure_shapely_geometry(geometry2)

            # Create difference
            difference = shapely_geom1.difference(shapely_geom2)

            return self._convert_if_needed(difference, geometry1)

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
            shapely_geom1 = self._ensure_shapely_geometry(geometry1)
            shapely_geom2 = self._ensure_shapely_geometry(geometry2)

            # Create intersection
            intersection = shapely_geom1.intersection(shapely_geom2)

            return self._convert_if_needed(intersection, geometry1)

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
            shapely_geom1 = self._ensure_shapely_geometry(geometry1)
            shapely_geom2 = self._ensure_shapely_geometry(geometry2)

            # Create union
            union = shapely_geom1.union(shapely_geom2)

            return self._convert_if_needed(union, geometry1)

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
        def smooth_op(geom, tol):
            return geom.simplify(tol, preserve_topology=True)

        return self._apply_geometry_operation(
            'smooth',
            smooth_op,
            geometry,
            tolerance
        )

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
