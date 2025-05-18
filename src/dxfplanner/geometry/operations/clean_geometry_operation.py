from typing import AsyncIterator, List, Optional
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import CleanGeometryOperationConfig
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.shapely_utils import make_valid_geometry
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry,
)
from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon, GeometryCollection

logger = get_logger(__name__)

class CleanGeometryOperation(IOperation[CleanGeometryOperationConfig]):
    """Cleans geometries (e.g., fix invalid, remove small parts)."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: CleanGeometryOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        logger.info(
            f"Executing CleanGeometryOperation for source_layer: '{config.source_layer}', output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"CleanGeometry: Skipping feature with no geometry. Properties: {feature.properties}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                logger.warning(f"CleanGeometry: Could not convert or got empty Shapely geometry. Properties: {feature.properties}")
                continue

            try:
                # Pass buffer_amount from config to make_valid_geometry
                cleaned_s_geom = make_valid_geometry(shapely_geom, buffer_amount=config.buffer_amount)
            except Exception as e_clean:
                logger.error(
                    f"CleanGeometry: Error during make_valid_geometry: {e_clean}. Properties: {feature.properties}",
                    exc_info=True
                )
                continue

            if cleaned_s_geom is None or cleaned_s_geom.is_empty:
                logger.warning(f"CleanGeometry: Geometry became None or empty after cleaning (make_valid). Original type: {shapely_geom.geom_type if shapely_geom else 'N/A'}. Properties: {feature.properties}")
                continue

            geoms_to_yield = []
            converted_geometries = convert_shapely_to_anygeogeometry(cleaned_s_geom)
            if isinstance(converted_geometries, list):
                for part_geom in converted_geometries:
                    if part_geom:
                         geoms_to_yield.append(part_geom)
            elif converted_geometries:
                geoms_to_yield.append(converted_geometries)

            if not geoms_to_yield:
                logger.debug(f"CleanGeometry: No valid DXFPlanner geometries from cleaned result. Properties: {feature.properties}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_attributes = feature.properties.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_attributes, crs=feature.crs)

        logger.info(f"CleanGeometryOperation completed for source_layer: '{config.source_layer}'")
