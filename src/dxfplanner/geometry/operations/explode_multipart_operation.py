from typing import AsyncIterator, List, Optional
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import ExplodeMultipartOperationConfig
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.shapely_utils import explode_multipart_geometry
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry,
)
# No direct Shapely geometry types needed here as explode_multipart_geometry returns them

logger = get_logger(__name__)

class ExplodeMultipartOperation(IOperation[ExplodeMultipartOperationConfig]):
    """Explodes multipart geometries into single part geometries."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: ExplodeMultipartOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        logger.info(
            f"Executing ExplodeMultipartOperation for source_layer: '{config.source_layer}', output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Explode: Skipping feature with no geometry. Properties: {feature.properties}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                logger.warning(f"Explode: Could not convert or got empty Shapely geometry. Properties: {feature.properties}")
                continue

            part_count = 0
            try:
                for single_part_s_geom in explode_multipart_geometry(shapely_geom):
                    if single_part_s_geom is None or single_part_s_geom.is_empty:
                        continue

                    new_dxf_geom_part = convert_shapely_to_anygeogeometry(single_part_s_geom)

                    if new_dxf_geom_part:
                        # If convert_shapely_to_anygeogeometry itself returns a list (e.g. for GeometryCollection parts),
                        # ensure we iterate through that too.
                        if isinstance(new_dxf_geom_part, list):
                            for sub_part_geom in new_dxf_geom_part:
                                if sub_part_geom:
                                    part_count += 1
                                    new_attributes = feature.properties.copy()
                                    yield GeoFeature(geometry=sub_part_geom, attributes=new_attributes, crs=feature.crs)
                        else: # Single geometry part
                            part_count += 1
                            new_attributes = feature.properties.copy()
                            yield GeoFeature(geometry=new_dxf_geom_part, attributes=new_attributes, crs=feature.crs)
                    else:
                        logger.warning(f"Explode: Could not convert exploded Shapely part back to DXFPlanner geometry. Part type: {single_part_s_geom.geom_type if single_part_s_geom else 'N/A'}")
            except Exception as e_explode:
                logger.error(
                    f"Explode: Error during explode_multipart_geometry or processing parts: {e_explode}. Properties: {feature.properties}",
                    exc_info=True
                )
                continue

            if part_count == 0 and shapely_geom and not shapely_geom.is_empty : # Log only if original had geometry
                logger.debug(f"Explode: No parts yielded for feature. Original type: {shapely_geom.geom_type if shapely_geom else 'N/A'}. Properties: {feature.properties}")

        logger.info(f"ExplodeMultipartOperation completed for source_layer: '{config.source_layer}'")
