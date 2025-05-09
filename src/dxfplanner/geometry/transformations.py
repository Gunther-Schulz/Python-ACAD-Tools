"""
Implementation of the GeometryTransformer interface.
"""
from typing import AsyncIterator, Optional, Any, Dict

from ..domain.models.geo_models import (
    GeoFeature, AnyGeoGeometry,
    PointGeo, PolylineGeo, PolygonGeo,
    MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo
)
from ..domain.models.dxf_models import (
    DxfEntity, DxfText, DxfLWPolyline, DxfHatch, DxfHatchPath, Coordinate as DxfCoordinate # Renamed to avoid clash
)
from ..domain.models.common import Coordinate as CommonCoordinate # Original Coordinate
from ..domain.interfaces import IGeometryTransformer, IAttributeMapper
from ..core.exceptions import GeometryTransformError
from ..core.logging_config import get_logger

logger = get_logger(__name__)

# Helper to convert common Coordinate to DXF Coordinate model if needed by DxfHatchPath etc.
# Though DxfHatchPath might directly accept tuples or CommonCoordinate if its pydantic model is flexible.
# For now, assume DxfHatchPath.vertices expects List[DxfCoordinate] or List[CommonCoordinate].
# DxfLWPolyline.points expects List[CommonCoordinate]
# DxfText.insertion_point expects CommonCoordinate

class GeometryTransformerImpl(IGeometryTransformer):
    """
    Transforms GeoFeatures into DXF entities.
    Relies on attribute mapper for styling and assumes CRS transformation is handled upstream.
    """

    def __init__(
        self,
        attribute_mapper: IAttributeMapper,
    ):
        self.attribute_mapper = attribute_mapper
        logger.info("GeometryTransformerImpl initialized.")

    async def _transform_single_geometry_to_dxf(
        self,
        geometry: AnyGeoGeometry,
        dxf_layer: str,
        dxf_properties: Dict[str, Any],
        feature_id: Optional[str] = "N/A"
    ) -> AsyncIterator[DxfEntity]:
        """Helper to transform a single (non-collection) geometry part."""
        # Default values if not found in dxf_properties
        default_text_content = str(feature_id if feature_id != "N/A" else ".")
        default_text_height = 1.0

        base_attribs = {
            "layer": dxf_layer,
            "color": dxf_properties.get('color') # Will be None if not mapped, DxfEntity handles default
        }

        if isinstance(geometry, PointGeo):
            text_content = dxf_properties.get('text_content', default_text_content)
            text_height = dxf_properties.get('height', default_text_height)

            # Ensure coordinates are in the expected format (CommonCoordinate)
            insertion_coord = geometry.coordinates
            if not isinstance(insertion_coord, CommonCoordinate):
                 logger.warning(f"PointGeo.coordinates is not CommonCoordinate type: {type(insertion_coord)}. Skipping feature part.")
                 return

            yield DxfText(
                insertion_point=insertion_coord,
                text_content=text_content,
                height=text_height,
                **base_attribs
            )

        elif isinstance(geometry, PolylineGeo):
            # Ensure coordinates list is not empty and elements are CommonCoordinate
            if not geometry.coordinates or not all(isinstance(c, CommonCoordinate) for c in geometry.coordinates):
                logger.warning(f"PolylineGeo.coordinates invalid. Skipping feature part. Coords: {geometry.coordinates[:5]}...")
                return

            yield DxfLWPolyline(
                points=geometry.coordinates,
                is_closed=False,
                **base_attribs
            )

        elif isinstance(geometry, PolygonGeo):
            if not geometry.coordinates or not geometry.coordinates[0]: # Must have at least an exterior ring
                logger.warning(f"PolygonGeo.coordinates invalid (no exterior ring). Skipping feature part.")
                return

            exterior_ring = geometry.coordinates[0]
            if not all(isinstance(c, CommonCoordinate) for c in exterior_ring):
                logger.warning(f"PolygonGeo exterior ring has invalid coordinates. Skipping feature part.")
                return

            # Create DxfHatch
            hatch_paths = [DxfHatchPath(vertices=exterior_ring, is_closed=True)] # is_closed for polyline path
            for interior_ring_coords in geometry.coordinates[1:]:
                if interior_ring_coords and all(isinstance(c, CommonCoordinate) for c in interior_ring_coords):
                    hatch_paths.append(DxfHatchPath(vertices=interior_ring_coords, is_closed=True))
                else:
                    logger.warning("PolygonGeo interior ring invalid. Skipping this interior path.")

            # Hatch specific properties from dxf_properties (if any mapped by AttributeMapper)
            # Current AttributeMapper simple config does not map these. Use DxfHatch defaults.
            hatch_pattern_name = dxf_properties.get("hatch_pattern_name", "SOLID")
            hatch_scale = dxf_properties.get("hatch_scale", 1.0)
            hatch_angle = dxf_properties.get("hatch_angle", 0.0)

            yield DxfHatch(
                paths=hatch_paths,
                pattern_name=hatch_pattern_name,
                scale=hatch_scale,
                angle=hatch_angle,
                # hatch_style_enum: HatchStyle = HatchStyle.NORMAL, # DxfHatch uses default
                **base_attribs
            )
            # As an alternative or fallback, could draw polylines for boundaries:
            # yield DxfLWPolyline(points=exterior_ring, is_closed=True, **base_attribs)
            # for interior_ring_coords in geometry.coordinates[1:]:
            #     if interior_ring_coords: # and valid
            #        yield DxfLWPolyline(points=interior_ring_coords, is_closed=True, **base_attribs)

        elif isinstance(geometry, (MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo)):
            # These are lists of coordinates or lists of lists of coordinates, not lists of Geo-objects
            # The structure of these GeoJSON-like models needs careful handling.
            # MultiPointGeo.coordinates: List[Coordinate]
            # MultiPolylineGeo.coordinates: List[List[Coordinate]]
            # MultiPolygonGeo.coordinates: List[List[List[Coordinate]]]

            if isinstance(geometry, MultiPointGeo):
                for coord_item in geometry.coordinates:
                    if isinstance(coord_item, CommonCoordinate):
                        async for entity in self._transform_single_geometry_to_dxf(PointGeo(coordinates=coord_item), dxf_layer, dxf_properties, feature_id):
                            yield entity
                    else:
                        logger.warning(f"MultiPointGeo item is not CommonCoordinate: {type(coord_item)}. Skipping.")
            elif isinstance(geometry, MultiPolylineGeo):
                for line_coords in geometry.coordinates:
                    if line_coords and all(isinstance(c, CommonCoordinate) for c in line_coords):
                        async for entity in self._transform_single_geometry_to_dxf(PolylineGeo(coordinates=line_coords), dxf_layer, dxf_properties, feature_id):
                            yield entity
                    else:
                         logger.warning(f"MultiPolylineGeo item has invalid coordinates. Skipping this line part.")
            elif isinstance(geometry, MultiPolygonGeo):
                for poly_coords_list in geometry.coordinates: # Each item is a list of rings for one polygon
                    if poly_coords_list and poly_coords_list[0] and all(isinstance(c, CommonCoordinate) for c in poly_coords_list[0]):
                        async for entity in self._transform_single_geometry_to_dxf(PolygonGeo(coordinates=poly_coords_list), dxf_layer, dxf_properties, feature_id):
                            yield entity
                    else:
                        logger.warning(f"MultiPolygonGeo item has invalid coordinates. Skipping this polygon part.")
        else:
            logger.warning(f"Unsupported geometry type for DXF transformation: {type(geometry)}. Feature ID: {feature_id}")

    async def transform_feature_to_dxf_entities(
        self,
        feature: GeoFeature,
        **kwargs: Any
    ) -> AsyncIterator[DxfEntity]:
        """
        Transforms a single GeoFeature into one or more DxfEntity objects.
        """
        if feature.geometry is None:
            logger.debug(f"Feature has no geometry. Skipping. Feature ID: {feature.id}")
            return

        dxf_layer = self.attribute_mapper.get_dxf_layer_for_feature(feature)
        # Use feature.properties for attribute mapping, not feature.attributes (Pydantic model field name)
        dxf_properties = self.attribute_mapper.get_dxf_properties_for_feature(feature)
        feature_id_str = str(feature.id) if feature.id is not None else "N/A"

        current_geometry = feature.geometry

        if isinstance(current_geometry, GeometryCollectionGeo):
            logger.debug(f"Transforming GeometryCollection with {len(current_geometry.geometries)} parts. Feature ID: {feature_id_str}")
            for geom_part in current_geometry.geometries:
                if geom_part:
                    async for entity in self._transform_single_geometry_to_dxf(geom_part, dxf_layer, dxf_properties, feature_id_str):
                        yield entity
        else:
            # Handles PointGeo, PolylineGeo, PolygonGeo, and their Multi* versions via _transform_single_geometry_to_dxf
            async for entity in self._transform_single_geometry_to_dxf(current_geometry, dxf_layer, dxf_properties, feature_id_str):
                yield entity

        # No explicit yield here as the helper does the yielding.
        # Ensure the method is recognized as an async generator:
        if False: # pragma: no cover
            if True: # Defeating linter for this specific case
                 yield DxfEntity() # Should not be reached
