from typing import AsyncIterator, List, Optional
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.schemas import ReprojectOperationConfig, CRSModel
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry,
)
from dxfplanner.geometry.projection import reproject_geometry
from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon, GeometryCollection

logger = get_logger(__name__)

class ReprojectOperation(IOperation[ReprojectOperationConfig]):
    """Reprojects geographic features to a new CRS."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: ReprojectOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        logger.info(
            f"Executing ReprojectOperation for source_layer: '{config.source_layer}' "
            f"to target_crs: {config.target_crs}, output: '{config.output_layer_name}'"
        )

        target_crs_str = config.target_crs
        if isinstance(config.target_crs, CRSModel): # Assuming CRSModel needs specific field
             target_crs_str = config.target_crs.name if hasattr(config.target_crs, 'name') else str(config.target_crs)
        elif not isinstance(config.target_crs, str):
             target_crs_str = str(config.target_crs)


        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Reproject: Skipping feature with no geometry. Properties: {feature.properties}")
                continue

            source_crs_str = feature.crs
            if not source_crs_str:
                logger.warning(f"Reproject: Feature has no source CRS defined. Cannot reproject. Properties: {feature.properties}")
                continue

            if source_crs_str.lower() == target_crs_str.lower():
                logger.debug(f"Reproject: Feature CRS '{source_crs_str}' matches target CRS '{target_crs_str}'. Yielding original feature.")
                yield feature
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                logger.warning(f"Reproject: Could not convert or got empty Shapely geometry. Properties: {feature.properties}")
                continue

            try:
                reprojected_s_geom = reproject_geometry(shapely_geom, source_crs_str, target_crs_str)
            except Exception as e_reproject:
                logger.error(
                    f"Reproject: Error during Shapely reproject_geometry: {e_reproject}. Properties: {feature.properties}",
                    exc_info=True
                )
                continue

            if reprojected_s_geom is None or reprojected_s_geom.is_empty:
                logger.warning(f"Reproject: Result is None or empty. Source CRS: {source_crs_str}, Target CRS: {target_crs_str}. Properties: {feature.properties}")
                continue

            geoms_to_yield = []
            converted_geometries = convert_shapely_to_anygeogeometry(reprojected_s_geom)
            if isinstance(converted_geometries, list):
                for part_geom in converted_geometries:
                    if part_geom:
                         geoms_to_yield.append(part_geom)
            elif converted_geometries:
                geoms_to_yield.append(converted_geometries)

            if not geoms_to_yield:
                logger.debug(f"Reproject: No valid DXFPlanner geometries from reprojected result. Properties: {feature.properties}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_attributes = feature.properties.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_attributes, crs=target_crs_str)

        logger.info(f"ReprojectOperation completed for source_layer: '{config.source_layer}'")
