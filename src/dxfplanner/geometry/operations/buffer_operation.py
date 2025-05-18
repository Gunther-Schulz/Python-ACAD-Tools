from typing import AsyncIterator, Optional, List, Dict, Any, Tuple
import types # For MappingProxyType

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import BufferOperationConfig
from dxfplanner.core.logging_config import get_logger
from shapely.geometry import (
    MultiPoint,
    MultiLineString,
    MultiPolygon,
    GeometryCollection
)
from dxfplanner.geometry.shapely_utils import (
    make_valid_geometry,
    remove_islands_from_geometry
)
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry
)

logger = get_logger(__name__)

SHAPELY_JOIN_STYLE = types.MappingProxyType({
    'ROUND': 1,
    'MITRE': 2,
    'BEVEL': 3
})
SHAPELY_CAP_STYLE = types.MappingProxyType({
    'ROUND': 1,
    'FLAT': 2,
    'SQUARE': 3
})

class BufferOperation(IOperation[BufferOperationConfig]):
    """Performs a buffer operation on geographic features."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: BufferOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the buffer operation.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: The configuration for the buffer operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting buffered GeoFeature objects.
        """
        logger.info(
            f"Executing BufferOperation with distance: {config.distance}, "
            f"output configured as: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(
                    f"Skipping feature with no geometry. Properties: {feature.properties}"
                )
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(
                    f"Could not convert DXFPlanner geometry to Shapely for feature. "
                    f"Properties: {feature.properties}"
                )
                continue

            if config.make_valid_pre_buffer:
                shapely_geom = make_valid_geometry(shapely_geom)
                if shapely_geom is None or shapely_geom.is_empty:
                    logger.warning(
                        f"Geometry became None/empty after pre-buffer validation. "
                        f"Properties: {feature.properties}"
                    )
                    continue

            current_buffer_distance = config.distance
            if config.distance_field and config.distance_field in feature.properties:
                try:
                    current_buffer_distance = float(feature.properties[config.distance_field])
                    logger.debug(
                        f"Using distance_field '{config.distance_field}' with value: {current_buffer_distance}"
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Could not parse distance_field '{config.distance_field}' value "
                        f"'{feature.properties[config.distance_field]}' as float: {e}. "
                        f"Using default: {config.distance}"
                    )
                    current_buffer_distance = config.distance

            s_join_style = SHAPELY_JOIN_STYLE.get(
                config.join_style.upper(), SHAPELY_JOIN_STYLE['ROUND'] # Ensure upper for key
            )
            s_cap_style = SHAPELY_CAP_STYLE.get(
                config.cap_style.upper(), SHAPELY_CAP_STYLE['ROUND'] # Ensure upper for key
            )

            try:
                buffered_s_geom = shapely_geom.buffer(
                    current_buffer_distance,
                    resolution=config.resolution,
                    join_style=s_join_style,
                    cap_style=s_cap_style,
                    mitre_limit=config.mitre_limit
                )
            except Exception as e_buffer:
                logger.error(
                    f"Error during Shapely buffer operation for feature: {e_buffer}. "
                    f"Properties: {feature.properties}",
                    exc_info=True
                )
                continue

            if buffered_s_geom is None or buffered_s_geom.is_empty:
                logger.debug(f"Buffer result is None or empty for feature. Properties: {feature.properties}")
                continue

            if config.skip_islands or config.preserve_islands:
                should_preserve_for_func = config.preserve_islands and not config.skip_islands
                buffered_s_geom = remove_islands_from_geometry(buffered_s_geom, preserve_islands=should_preserve_for_func)
                if buffered_s_geom is None or buffered_s_geom.is_empty:
                    logger.debug(f"Geometry became None/empty after island processing. Properties: {feature.properties}")
                    continue

            if config.make_valid_post_buffer:
                buffered_s_geom = make_valid_geometry(buffered_s_geom)
                if buffered_s_geom is None or buffered_s_geom.is_empty:
                    logger.warning(f"Geometry became None/empty after post-buffer validation. Properties: {feature.properties}")
                    continue

            geoms_to_yield = []
            # Convert potentially multipart geometry
            converted_geometries = convert_shapely_to_anygeogeometry(buffered_s_geom)
            if isinstance(converted_geometries, list):
                for part_geom in converted_geometries:
                    if part_geom: # Ensure the part itself is not None
                        geoms_to_yield.append(part_geom)
            elif converted_geometries: # Single geometry was returned
                geoms_to_yield.append(converted_geometries)


            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from buffer result. Properties: {feature.properties}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_feature_attributes = feature.properties.copy() # Use .properties
                yield GeoFeature(geometry=new_dxf_geom, properties=new_feature_attributes) # Ensure attributes is the correct name

        logger.info(f"BufferOperation completed. Output configured as: '{config.output_layer_name}'")
