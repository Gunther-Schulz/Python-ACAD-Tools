from typing import AsyncIterator, List, Dict, Any, Optional
from collections import defaultdict
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import DissolveOperationConfig
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.model_conversion import (
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry,
)
from dxfplanner.geometry.shapely_utils import make_valid_geometry

from shapely.ops import unary_union
from shapely.errors import GEOSException

logger = get_logger(__name__)

class DissolveOperation(IOperation[DissolveOperationConfig]):
    """Dissolves features based on a specified attribute field."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: DissolveOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        # DissolveOperationConfig does not have source_layer. Use output_layer_name for log context.
        log_prefix = f"DissolveOperation (by: '{config.by_attribute}', output: '{config.output_layer_name}')"
        logger.info(f"{log_prefix}: Starting dissolve.")

        grouped_features_data: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {"geoms": [], "first_feature_properties": None, "first_feature_crs": None})
        default_group_key = "__all_dissolve_group__" # Used if by_attribute is None or field missing

        input_feature_count = 0
        async for feature in features:
            input_feature_count += 1
            current_properties = feature.properties if feature.properties else {}
            group_key_value: Any = default_group_key

            if config.by_attribute:
                if config.by_attribute in current_properties:
                    val = current_properties[config.by_attribute]
                    # Ensure hashable key, convert None to a specific marker if needed to distinguish from default_group_key
                    group_key_value = val if val is not None else f"__none_value_for_{config.by_attribute}__"
                # else: stays default_group_key if field is missing

            group_data = grouped_features_data[group_key_value]
            if group_data["first_feature_properties"] is None:
                group_data["first_feature_properties"] = current_properties.copy()
                group_data["first_feature_crs"] = feature.crs

            if feature.geometry:
                s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
                if s_geom and not s_geom.is_empty:
                    valid_s_geom = make_valid_geometry(s_geom)
                    if valid_s_geom and not valid_s_geom.is_empty:
                        group_data["geoms"].append(valid_s_geom)

        if input_feature_count == 0: logger.info(f"{log_prefix}: No features to dissolve."); return
        logger.debug(f"{log_prefix}: Grouped into {len(grouped_features_data)} groups by '{config.by_attribute or 'N/A'}'.")

        for group_key, data in grouped_features_data.items():
            if not data["geoms"]: logger.warning(f"{log_prefix}: No geoms for group '{group_key}'. Skipping."); continue
            try:
                dissolved_s_geom = unary_union(data["geoms"])
                if not dissolved_s_geom or dissolved_s_geom.is_empty: logger.warning(f"{log_prefix}: Union empty for group '{group_key}'."); continue
                dissolved_s_geom = make_valid_geometry(dissolved_s_geom)
                if not dissolved_s_geom or dissolved_s_geom.is_empty: logger.warning(f"{log_prefix}: Dissolved empty post-validation for group '{group_key}'."); continue

                new_properties = data["first_feature_properties"].copy() if data["first_feature_properties"] else {}
                if config.by_attribute:
                    actual_key_to_store = group_key if group_key not in [default_group_key, f"__none_value_for_{config.by_attribute}__"] else None
                    new_properties[config.by_attribute] = actual_key_to_store

                final_dxf_geoms = convert_shapely_to_anygeogeometry(dissolved_s_geom)
                geoms_to_yield = [g for g in final_dxf_geoms if g] if isinstance(final_dxf_geoms, list) else ([final_dxf_geoms] if final_dxf_geoms else [])

                if not geoms_to_yield: logger.warning(f"{log_prefix}: Failed to convert dissolved geom for group '{group_key}'."); continue
                for geom_part in geoms_to_yield:
                    yield GeoFeature(geometry=geom_part, attributes=new_properties, crs=data["first_feature_crs"])
            except Exception as e: logger.error(f"{log_prefix}: Error for group '{group_key}': {e}", exc_info=True)
        logger.info(f"{log_prefix}: Completed.")
