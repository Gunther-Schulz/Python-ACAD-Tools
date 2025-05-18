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
        op_name_for_log = f"BufferOp ('{config.output_layer_name or 'UnnamedBuffer'}' from source distance {config.distance})" # Helper for logs, handle no output_name
        logger.info(
            f"{op_name_for_log}: Executing."
        )

        processed_feature_count = 0
        yielded_feature_count = 0

        async for feature in features:
            processed_feature_count += 1
            logger.debug(f"{op_name_for_log}: Processing input feature #{processed_feature_count}. Props: {feature.properties}")
            if feature.geometry is None:
                logger.debug(
                    f"{op_name_for_log}: Skipping feature #{processed_feature_count} with no geometry. Properties: {feature.properties}"
                )
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(
                    f"{op_name_for_log}: Could not convert DXFPlanner geometry to Shapely for feature #{processed_feature_count}. "
                    f"Properties: {feature.properties}"
                )
                continue

            if config.make_valid_pre_buffer:
                shapely_geom = make_valid_geometry(shapely_geom)
                if shapely_geom is None or shapely_geom.is_empty:
                    logger.warning(
                        f"{op_name_for_log}: Geometry for feature #{processed_feature_count} became None/empty after pre-buffer validation. "
                        f"Properties: {feature.properties}"
                    )
                    continue

            current_buffer_distance = config.distance
            if config.distance_field and config.distance_field in feature.properties:
                try:
                    current_buffer_distance = float(feature.properties[config.distance_field])
                    logger.debug(
                        f"{op_name_for_log}: Feature #{processed_feature_count} using distance_field '{config.distance_field}' with value: {current_buffer_distance}"
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"{op_name_for_log}: Could not parse distance_field '{config.distance_field}' value for feature #{processed_feature_count} "
                        f"'{feature.properties[config.distance_field]}' as float: {e}. "
                        f"Using default: {config.distance}"
                    )
                    current_buffer_distance = config.distance

            s_join_style = SHAPELY_JOIN_STYLE.get(
                config.join_style.upper(), SHAPELY_JOIN_STYLE['ROUND']
            )
            s_cap_style = SHAPELY_CAP_STYLE.get(
                config.cap_style.upper(), SHAPELY_CAP_STYLE['ROUND']
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
                    f"{op_name_for_log}: Error during Shapely buffer operation for feature #{processed_feature_count}: {e_buffer}. "
                    f"Properties: {feature.properties}",
                    exc_info=True
                )
                continue

            if buffered_s_geom is None or buffered_s_geom.is_empty:
                logger.debug(f"{op_name_for_log}: Buffer result for feature #{processed_feature_count} is None or empty. Properties: {feature.properties}")
                continue

            if config.skip_islands or config.preserve_islands:
                should_preserve_for_func = config.preserve_islands and not config.skip_islands
                buffered_s_geom = remove_islands_from_geometry(buffered_s_geom, preserve_islands=should_preserve_for_func)
                if buffered_s_geom is None or buffered_s_geom.is_empty:
                    logger.debug(f"{op_name_for_log}: Geometry for feature #{processed_feature_count} became None/empty after island processing. Properties: {feature.properties}")
                    continue

            if config.make_valid_post_buffer:
                buffered_s_geom = make_valid_geometry(buffered_s_geom)
                if buffered_s_geom is None or buffered_s_geom.is_empty:
                    logger.warning(f"{op_name_for_log}: Geometry for feature #{processed_feature_count} became None/empty after post-buffer validation. Properties: {feature.properties}")
                    continue

            geoms_to_yield = []
            converted_geometries = convert_shapely_to_anygeogeometry(buffered_s_geom)
            if isinstance(converted_geometries, list):
                for part_geom in converted_geometries:
                    if part_geom:
                        geoms_to_yield.append(part_geom)
            elif converted_geometries:
                geoms_to_yield.append(converted_geometries)


            if not geoms_to_yield:
                logger.debug(f"{op_name_for_log}: No valid DXFPlanner geometries could be converted from buffer result for feature #{processed_feature_count}. Properties: {feature.properties}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_feature_attributes = feature.properties.copy()
                logger.debug(f"{op_name_for_log}: Yielding output feature #{yielded_feature_count + 1} (from input #{processed_feature_count}). Original props: {feature.properties}")
                yielded_feature_count += 1
                yield GeoFeature(geometry=new_dxf_geom, properties=new_feature_attributes)

        if processed_feature_count == 0:
            logger.warning(f"{op_name_for_log}: Received 0 input features.")

        logger.info(f"{op_name_for_log}: Completed. Processed: {processed_feature_count} input features, Yielded: {yielded_feature_count} output features.")
