from typing import AsyncIterator, List, Dict, Any, Optional
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import SimplifyOperationConfig
from dxfplanner.core.logging_config import get_logger
from shapely.geometry import (
    MultiPoint, # Keep if convert_shapely_to_anygeogeometry can produce these from simplified output
    MultiLineString,
    MultiPolygon,
    GeometryCollection
)
from dxfplanner.geometry.shapely_utils import make_valid_geometry
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry
)

logger = get_logger(__name__)

class SimplifyOperation(IOperation[SimplifyOperationConfig]):
    """Performs a simplify (e.g., Douglas-Peucker) operation on geographic features."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: SimplifyOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the simplify operation.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: The configuration for the simplify operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting simplified GeoFeature objects.
        """
        logger.info(
            f"Executing SimplifyOperation for source_layer: '{config.source_layer}' " # Assuming source_layer is on BaseOperationConfig
            f"with tolerance: {config.tolerance}, output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Simplify: Skipping feature with no geometry. Properties: {feature.properties}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                logger.warning(f"Simplify: Could not convert or got empty Shapely geometry. Properties: {feature.properties}")
                continue

            try:
                simplified_s_geom = shapely_geom.simplify(config.tolerance, preserve_topology=config.preserve_topology)
            except Exception as e_simplify:
                logger.error(
                    f"Simplify: Error during Shapely simplify operation: {e_simplify}. Properties: {feature.properties}",
                    exc_info=True
                )
                continue

            if simplified_s_geom is None or simplified_s_geom.is_empty:
                logger.debug(f"Simplify: Result is None or empty. Properties: {feature.properties}")
                continue

            # make_valid_post_simplify was removed from SimplifyOperationConfig, so logic is removed here.
            # if config.make_valid_post_simplify:
            #     simplified_s_geom = make_valid_geometry(simplified_s_geom)
            #     if simplified_s_geom is None or simplified_s_geom.is_empty:
            #         logger.warning(f"Simplify: Geometry became None/empty after post-simplify validation. Properties: {feature.properties}")
            #         continue # Corrected from 'return' to 'continue'

            geoms_to_yield = []
            converted_geometries = convert_shapely_to_anygeogeometry(simplified_s_geom)
            if isinstance(converted_geometries, list):
                for part_geom in converted_geometries:
                    if part_geom: # Ensure the part itself is not None
                        geoms_to_yield.append(part_geom)
            elif converted_geometries: # Single geometry was returned
                geoms_to_yield.append(converted_geometries)


            if not geoms_to_yield:
                logger.debug(f"Simplify: No valid DXFPlanner geometries from simplification. Properties: {feature.properties}")
                continue

            for new_dxf_geom in geoms_to_yield:
                # Ensure 'attributes' is correctly named if GeoFeature expects that
                new_feature_properties = feature.properties.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_feature_properties, crs=feature.crs) # Changed attributes= to properties= if needed

        logger.info(f"SimplifyOperation completed for source_layer: '{config.source_layer}'") # Assuming source_layer is on BaseOperationConfig
