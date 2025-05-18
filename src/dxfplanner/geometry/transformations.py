# src/dxfplanner/geometry/transformations.py
from typing import List, Optional, Union, Any, Dict, Tuple, AsyncIterator
import math
import asyncio

from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString, Polygon as ShapelyPolygon
from shapely.ops import transform as shapely_transform_op

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPolygonGeo, GeometryCollectionGeo, AnyGeoGeometry
from dxfplanner.domain.models.dxf_models import AnyDxfEntity, DxfLine, DxfLWPolyline, DxfHatch, DxfHatchPath, DxfMText, DxfText, DxfInsert, DxfArc, DxfCircle # Added DxfMText, DxfLine, DxfInsert etc.
from dxfplanner.domain.interfaces import IGeometryTransformer, ICoordinateService, IStyleService
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
from dxfplanner.geometry.model_conversion import convert_shapely_to_anygeogeometry
from dxfplanner.geometry.feature_converter import convert_geo_feature_to_dxf_entities

logger = get_logger(__name__)

class GeometryTransformerImpl(IGeometryTransformer):
    def __init__(self, style_service: IStyleService, default_text_height: float = 2.5):
        self.style_service = style_service
        self.default_text_height = default_text_height
        self.logger = get_logger(__name__)

    async def transform_feature_to_dxf_entities(
        self,
        feature: GeoFeature,
        layer_config: Optional[LayerConfig] = None,
        style_service: Optional[IStyleService] = None,
        output_target_layer_name: Optional[str] = None,
        default_xdata_app_id: Optional[str] = "DXFPLANNER",
        default_xdata_tags: Optional[List[Tuple[int, Any]]] = None
    ) -> AsyncIterator[AnyDxfEntity]:
        self.logger.debug(
            f"Transforming feature ID {feature.id or 'N/A'} for "
            f"input layer '{layer_config.name if layer_config else 'N/A'}' "
            f"with output target layer '{output_target_layer_name or 'None specified (will derive)'}'."
        )

        current_style_service = style_service or self.style_service
        if not current_style_service:
            self.logger.error("StyleService is not available for GeometryTransformerImpl. Cannot proceed.")
            raise ConfigurationError("StyleService is not available for GeometryTransformerImpl.")

        # Determine the key for style resolution context.
        # If an output target layer is specified, that's the primary context for styling.
        # Otherwise, use the input layer's name.
        effective_style_resolution_key = output_target_layer_name or (layer_config.name if layer_config else None)

        try:
            # Resolve the effective style for the feature
            resolved_style_object = current_style_service.get_resolved_feature_style(
                geo_feature=feature,
                layer_config=layer_config # Pass the original layer_config for context
            )
            effective_style_dict = resolved_style_object.model_dump(exclude_none=True)

            # Call the utility function
            async for dxf_entity in convert_geo_feature_to_dxf_entities(
                geo_feature=feature, # Corrected keyword
                effective_style=effective_style_dict, # Pass resolved style dictionary
                # Pass the explicit output target layer name
                output_target_layer_name=output_target_layer_name,
                # Provide input layer name for context if output_target_layer_name is not set
                input_layer_name_for_context=(layer_config.name if layer_config else None),
                default_xdata_app_id=default_xdata_app_id,
                default_xdata_tags=default_xdata_tags
            ):
                yield dxf_entity
                # await asyncio.sleep(0) # Removed, feature_converter should handle its own async iteration properly

        except Exception as e:
            self.logger.error(
                f"Error during transformation for feature ID {feature.id or 'N/A'} "
                f"(Input layer: {layer_config.name if layer_config else 'N/A'}, Output target: {output_target_layer_name or 'N/A'}): {e}",
                exc_info=True
            )
            # Optionally re-raise or handle if necessary, for now just logging
