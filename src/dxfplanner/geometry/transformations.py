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
    DxfEntity, DxfText, DxfLWPolyline, DxfHatch, DxfHatchPath, Coordinate as DxfCoordinate,
    AnyDxfEntity # Added AnyDxfEntity
)
from ..domain.models.common import Coordinate as CommonCoordinate, PlacedLabel # Added PlacedLabel
from ..domain.interfaces import IGeometryTransformer, IAttributeMapper
from ..config.schemas import TextStylePropertiesConfig # Added TextStylePropertiesConfig
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

        # Prepare base DXF attributes from resolved properties, including layer
        base_attribs = {
            "layer": dxf_layer,
        }
        # Add common attributes if they exist in dxf_properties (from AttributeMapper)
        if 'color' in dxf_properties: # color should be ACI index or None
            base_attribs['color'] = dxf_properties['color']
        if 'linetype' in dxf_properties:
            base_attribs['linetype'] = dxf_properties['linetype']
        if 'lineweight' in dxf_properties: # e.g., 25 for 0.25mm
            base_attribs['lineweight'] = dxf_properties['lineweight']
        if 'transparency' in dxf_properties: # e.g., 0.5 for 50% transparent
             # ezdxf uses True Color alpha byte for transparency (0=opaque, 255=fully transparent)
             # Or specific Transparency object? Check ezdxf docs.
             # For simplicity, let's assume ezdxf handles a 'transparency' key if available.
             # If not, this might need adjustment based on ezdxf version/API.
             # base_attribs['transparency'] = dxf_properties['transparency'] # Placeholder
             pass # Deferring transparency implementation until ezdxf API is confirmed

        # Ensure base_attribs only contains non-None values if ezdxf prefers that
        # base_attribs = {k: v for k, v in base_attribs.items() if v is not None} # Optional cleanup

        if isinstance(geometry, PointGeo):
            text_content = dxf_properties.get('text_content', default_text_content)
            text_height = dxf_properties.get('height', default_text_height)

            # Ensure coordinates are in the expected format (CommonCoordinate)
            insertion_coord = geometry.coordinates
            if not isinstance(insertion_coord, CommonCoordinate):
                 logger.warning(f"PointGeo.coordinates is not CommonCoordinate type: {type(insertion_coord)}. Skipping feature part.")
                 return

            point_text_attribs = base_attribs.copy()
            point_text_attribs['height'] = text_height

            yield DxfText(
                insertion_point=insertion_coord,
                text_content=text_content,
                **point_text_attribs
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

            # Hatch specific properties from dxf_properties
            hatch_pattern_name = dxf_properties.get("hatch_pattern_name", "SOLID")
            hatch_scale = dxf_properties.get("hatch_scale", 1.0)
            hatch_angle = dxf_properties.get("hatch_angle", 0.0)
            hatch_style_enum = dxf_properties.get("hatch_style_enum", 'NORMAL') # Get specific hatch style if mapped
            # associative = dxf_properties.get("associative", False) # Get associativity if mapped

            # Combine base attributes and hatch-specific attributes
            hatch_attribs = base_attribs.copy()
            hatch_attribs['pattern_name'] = hatch_pattern_name
            hatch_attribs['scale'] = hatch_scale
            hatch_attribs['angle'] = hatch_angle
            hatch_attribs['hatch_style_enum'] = hatch_style_enum
            # hatch_attribs['associative'] = associative # Add if needed

            # Pass ONLY the combined dictionary to the DxfHatch model
            yield DxfHatch(
                paths=hatch_paths,
                # REMOVE individual keywords below, they are now in hatch_attribs
                # pattern_name=hatch_pattern_name,
                # scale=hatch_scale,
                # angle=hatch_angle,
                # hatch_style_enum=hatch_style_enum,
                **hatch_attribs # Pass combined dict including base layer, color etc. AND hatch specifics
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

    async def transform_placed_label_to_dxf_entity(
        self,
        label: PlacedLabel,
        style_config: Optional[TextStylePropertiesConfig] = None
    ) -> Optional[AnyDxfEntity]:
        """
        Transforms a PlacedLabel object into a DXF text entity (e.g., MTEXT or TEXT).
        """
        if not isinstance(label.position, CommonCoordinate):
            logger.error(f"PlacedLabel has invalid position type: {type(label.position)}. Cannot create DxfText.")
            return None

        # Default DXF properties for text, can be overridden by style_config
        dxf_text_props = {
            "text_content": label.text,
            "insertion_point": label.position,
            "height": 2.5, # Default height
            "rotation": label.rotation,
            "layer": "0", # Default layer, should ideally come from style or context
            "color": None # Default color (BYLAYER/BYBLOCK determined by DxfText model)
        }

        if style_config:
            dxf_text_props["height"] = style_config.height
            if style_config.color: # color can be "BYLAYER", ACI, or tuple
                dxf_text_props["color"] = style_config.color
            # layer should be part of a broader styling context, not directly in TextStylePropertiesConfig
            # For now, we'll assume the layer is set by the DxfWriter or a default.
            # MTEXT specific properties from style_config could be added here if creating DxfMText
            # e.g., dxf_text_props["attachment_point"] = style_config.attachment_point if style_config.attachment_point else None
            # dxf_text_props["mtext_width"] = style_config.mtext_width if style_config.mtext_width else None
            # etc.

        try:
            # For simplicity, creating DxfText. Could be DxfMText if more advanced formatting is needed.
            # Ensure DxfText model can handle 'rotation' and other fields as passed.
            # The DxfText model needs layer and color. Layer might come from LayerConfig.labeling style.
            # If TextStylePropertiesConfig doesn't include layer, a default or context layer is needed.

            # Let's assume layer comes from the DxfText model's default or is handled by DxfWriter
            # based on general layer context, if not in style_config (which it isn't typically).
            # If a label_layer is defined in LabelingConfig, that should be used.
            # For now, using a placeholder for layer. This needs refinement in LayerProcessorService.

            # Removing layer from here, should be provided by caller or handled by DxfText default
            # dxf_text_props.pop("layer", None) # Or set from a context if available

            created_entity = DxfText(**dxf_text_props)
            logger.debug(f"Created DxfText for label: '{label.text}' at {label.position.x},{label.position.y}")
            return created_entity
        except Exception as e:
            logger.error(f"Failed to create DxfText for label '{label.text}': {e}", exc_info=True)
            return None
