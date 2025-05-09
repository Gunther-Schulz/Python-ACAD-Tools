from typing import AsyncIterator, Optional, Any, Dict

from dxfplanner.domain.models.geo_models import GeoFeature #, PointGeo, PolylineGeo, PolygonGeo
from dxfplanner.domain.models.dxf_models import DxfEntity #, DxfLine, DxfLWPolyline, DxfText
from dxfplanner.domain.models.common import Coordinate # For direct use if needed
from dxfplanner.domain.interfaces import (
    IGeometryTransformer,
    # ICoordinateService, # Removed as it's no longer used by this service
    IAttributeMapper
)
from dxfplanner.core.exceptions import GeometryTransformError
# from dxfplanner.config.schemas import GeometryTransformServiceConfig # For config injection
# from loguru import logger # Assuming logger is obtained via dxfplanner.core.logging_config.get_logger if needed elsewhere

class GeometryTransformService(IGeometryTransformer):
    """
    Service for transforming GeoFeatures into DXF entities.
    This service will orchestrate attribute mapping. CRS transformation is handled by readers.
    """

    def __init__(
        self,
        # coordinate_service: ICoordinateService, # REMOVED
        attribute_mapper: IAttributeMapper,
        # config: Optional[GeometryTransformServiceConfig] = None # Optional config for this service
    ):
        # self.coordinate_service = coordinate_service # REMOVED
        self.attribute_mapper = attribute_mapper
        # self.config = config or GeometryTransformServiceConfig()
        # logger.info("GeometryTransformService initialized.") # Assuming logger is used as per project standards if un-commented

    async def transform_feature_to_dxf_entities(
        self,
        feature: GeoFeature,
        # target_crs: Optional[str] = None, # REMOVED from interface and implementation
        **kwargs: Any
    ) -> AsyncIterator[DxfEntity]:
        """
        Transforms a single GeoFeature into one or more DxfEntity objects.
        Actual implementation will convert different geometry types (Point, LineString, Polygon)
        from GeoFeature.geometry into corresponding DxfEntity types (DxfText, DxfLWPolyline, etc.).
        It will use IAttributeMapper for DXF properties. CRS transformation is assumed to be done by readers.
        """

        # 1. Get DXF layer and base properties from attribute mapper
        # dxf_layer = self.attribute_mapper.get_dxf_layer_for_feature(feature)
        # dxf_base_props = self.attribute_mapper.get_dxf_properties_for_feature(feature)
        # dxf_base_props["layer"] = dxf_layer # Ensure layer is in the props for entities

        # 2. Handle geometry transformation based on GeoFeature.geometry.type
        #    Coordinates are assumed to be in the final target CRS already (transformed by readers).

        # Conceptual example for PointGeo to DxfText:
        # if isinstance(feature.geometry, PointGeo):
        #     point_coord = feature.geometry.coordinates # Assumed to be already in target CRS
        #
        #     # Example: if feature.geometry is Shapely Point
        #     # reprojected_coord_tuple = (point_coord.x, point_coord.y)
        #     # if point_coord.has_z:
        #     #    reprojected_coord_tuple = (point_coord.x, point_coord.y, point_coord.z)

        #     # Create DxfText entity
        #     # text_content = dxf_base_props.pop("text_content", feature.id or "Point")
        #     # text_height = dxf_base_props.pop("height", self.config.default_text_height_for_points if hasattr(self, 'config') else 1.0)
        #     #
        #     # if "height" not in dxf_base_props and not text_height:
        #     #      text_height = 1.0 # A sensible default if not from config or props

        #     # yield DxfText(
        #     #     insertion_point=reprojected_coord_tuple, # Use tuple (x,y) or (x,y,z)
        #     #     text_content=str(text_content),
        #     #     height=text_height,
        #     #     **dxf_base_props # Pass remaining mapped properties (layer, color, etc.)
        #     # )
        #     pass # Placeholder

        # elif isinstance(feature.geometry, PolylineGeo): # or appropriate shapely types
        #     # Similar logic: coordinates are already in target CRS.
        #     # Extract points from feature.geometry.coordinates
        #     # reprojected_points = [(coord.x, coord.y) for coord in feature.geometry.coordinates]
        #     # yield DxfLWPolyline(points=reprojected_points, **dxf_base_props)
        #     pass # Placeholder

        # elif isinstance(feature.geometry, PolygonGeo): # or appropriate shapely types
        #     # Similar logic for exterior and interior rings.
        #     # exterior_points = [(coord.x, coord.y) for coord in feature.geometry.exterior.coordinates]
        #     # yield DxfLWPolyline(points=exterior_points, is_closed=True, **dxf_base_props)
        #     # For interiors, create separate LWPolylines or handle as per DXF HATCH requirements if filling.
        #     pass # Placeholder

        # else:
        #     # Potentially use logger from dxfplanner.core.logging_config if needed here
        #     # logger.warning(f"Unsupported geometry type: {type(feature.geometry)} for feature {getattr(feature, 'id', 'unknown')}")
        #     pass

        if False: # pragma: no cover
            yield DxfEntity() # Dummy yield

        raise NotImplementedError(
            "GeometryTransformService.transform_feature_to_dxf_entities is not yet implemented."
        )
