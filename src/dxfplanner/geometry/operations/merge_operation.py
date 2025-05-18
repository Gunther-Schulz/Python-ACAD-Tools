from typing import AsyncIterator, List, Dict, Any, Optional
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import MergeOperationConfig
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry,
)
from dxfplanner.geometry.shapely_utils import make_valid_geometry

from shapely.ops import unary_union
from shapely.errors import GEOSException

logger = get_logger(__name__)

class MergeOperation(IOperation[MergeOperationConfig]):
    """
    Merges features from a single input stream into one or fewer features
    by performing a unary union of their geometries.
    """

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: MergeOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        log_prefix = f"MergeOperation (output: '{config.output_layer_name}')" # source_layer not on MergeOpConfig
        logger.info(f"{log_prefix}: Executing...")

        shapely_geoms_to_merge: List[Any] = []
        first_feature_properties: Optional[Dict[str, Any]] = None
        first_feature_crs: Optional[str] = None
        input_feature_count = 0

        async for feature in features:
            input_feature_count += 1
            if input_feature_count == 1:
                first_feature_properties = feature.properties.copy() if feature.properties else {}
                first_feature_crs = feature.crs

            if feature.geometry:
                s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
                if s_geom and not s_geom.is_empty:
                    valid_s_geom = make_valid_geometry(s_geom)
                    if valid_s_geom and not valid_s_geom.is_empty:
                        shapely_geoms_to_merge.append(valid_s_geom)
                    else:
                        logger.debug(f"{log_prefix}: Input geometry invalid/empty post-validation. Properties: {feature.properties}")
                else:
                    logger.debug(f"{log_prefix}: Input geometry None/empty post-conversion. Properties: {feature.properties}")

        if not shapely_geoms_to_merge:
            logger.info(f"{log_prefix}: No valid geometries from {input_feature_count} inputs. Yielding nothing.")
            return
        logger.info(f"{log_prefix}: Collected {len(shapely_geoms_to_merge)} geoms from {input_feature_count} inputs.")

        merged_s_geom = None
        try:
            merged_s_geom = unary_union(shapely_geoms_to_merge)
            if not merged_s_geom or merged_s_geom.is_empty: logger.warning(f"{log_prefix}: Unary union empty/invalid."); return
            merged_s_geom = make_valid_geometry(merged_s_geom)
            if not merged_s_geom or merged_s_geom.is_empty: logger.warning(f"{log_prefix}: Merged geom empty/invalid post-validation."); return
        except Exception as e: logger.error(f"{log_prefix}: Union/validation error: {e}", exc_info=True); return

        result_properties = first_feature_properties if first_feature_properties is not None else {}
        geoms_to_yield = []
        converted_geoms = convert_shapely_to_anygeogeometry(merged_s_geom)
        if isinstance(converted_geoms, list): geoms_to_yield.extend(g for g in converted_geoms if g)
        elif converted_geoms: geoms_to_yield.append(converted_geoms)

        if not geoms_to_yield: logger.warning(f"{log_prefix}: No valid DXFPlanner geoms from merged result."); return

        for new_dxf_geom in geoms_to_yield:
            yield GeoFeature(geometry=new_dxf_geom, attributes=result_properties, crs=first_feature_crs)
        logger.info(f"{log_prefix}: Completed. Yielded {len(geoms_to_yield)} feature(s).")
