# src/dxfplanner/geometry/transformations.py
from typing import List, Optional, Union, Any, Dict, Tuple, AsyncIterator
import math
import asyncio

from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString, Polygon as ShapelyPolygon
from shapely.ops import transform as shapely_transform_op

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPolygonGeo, GeometryCollectionGeo, AnyGeoGeometry
from dxfplanner.domain.models.dxf_models import AnyDxfEntity, DxfLine, DxfLWPolyline, DxfHatch, DxfHatchPath, DxfMText, DxfText, DxfInsert, DxfArc, DxfCircle # Added DxfMText, DxfLine, DxfInsert etc.
from dxfplanner.domain.interfaces import IGeometryTransformer, ICoordinateService
from dxfplanner.services.style_service import StyleService, StyleObjectConfig
from dxfplanner.config.schemas import (
    LayerConfig,
    LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig,
    HatchPropertiesConfig,
    TextParagraphPropertiesConfig,
    ColorModel
)
from dxfplanner.core.exceptions import GeometryTransformError, ConfigurationError
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.utils import (
    convert_shapely_to_anygeogeometry,
    convert_geo_feature_to_dxf_entities
)

logger = get_logger(__name__)

class GeometryTransformerImpl(IGeometryTransformer):
    def __init__(self, style_service: StyleService, default_text_height: float = 2.5):
        self.style_service = style_service
        self.default_text_height = default_text_height
        self.logger = get_logger(__name__)

    async def transform_feature_to_dxf_entities(
        self, feature: GeoFeature, layer_config: LayerConfig
    ) -> AsyncIterator[AnyDxfEntity]:
        self.logger.debug(f"Transforming feature ID {feature.id or 'N/A'} for layer '{layer_config.name}' using utility function.")

        style_config: StyleObjectConfig = self.style_service.get_resolved_style_for_feature(
            layer_config=layer_config,
            feature_attributes=feature.properties
        )

        effective_style_dict = style_config.model_dump(exclude_none=True) # Convert StyleObjectConfig to dict

        try:
            # Call the utility function
            dxf_entities: List[AnyDxfEntity] = convert_geo_feature_to_dxf_entities(
                geo_feature=feature,
                effective_style=effective_style_dict,
                layer_name=layer_config.name
            )

            if not dxf_entities:
                self.logger.debug(f"Utility function returned no DXF entities for feature ID {feature.id or 'N/A'} on layer {layer_config.name}.")

            for dxf_entity in dxf_entities:
                yield dxf_entity
                await asyncio.sleep(0) # Ensure cooperative multitasking

        except Exception as e:
            self.logger.error(
                f"Error during transformation using utility for feature ID {feature.id or 'N/A'} "
                f"on layer {layer_config.name}: {e}",
                exc_info=True
            )
