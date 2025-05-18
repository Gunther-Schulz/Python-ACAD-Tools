from typing import AsyncIterator, Any, Optional, List, Tuple
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import FilterByExtentOperationConfig, ExtentFilterMode
from dxfplanner.core.logging_config import get_logger # Main logger
from logging import Logger # For type hint
from dxfplanner.geometry.model_conversion import convert_dxfplanner_geometry_to_shapely
from shapely.geometry import box, Polygon, LineString, Point
from shapely.errors import GEOSException

logger = get_logger(__name__)

class FilterByExtentOperation(IOperation[FilterByExtentOperationConfig]):
    """Filters features based on their spatial relationship to a defined extent."""

    def __init__(self, logger_param: Optional[Logger] = None):
        self.logger = logger_param if logger_param else logger

    async def execute(self, features: AsyncIterator[GeoFeature], config: FilterByExtentOperationConfig) -> AsyncIterator[GeoFeature]:
        log_prefix = f"FilterByExtent (mode: {config.mode}, output: '{config.output_layer_name}')"
        self.logger.info(f"{log_prefix}: Extent ({config.min_x}, {config.min_y}) to ({config.max_x}, {config.max_y}).")

        try:
            filter_box = box(config.min_x, config.min_y, config.max_x, config.max_y)
            if not filter_box.is_valid:
                self.logger.error(f"{log_prefix}: Invalid filter box from extent. Cannot filter.")
                async for feature_error_case in features: yield feature_error_case # Yield all if filter invalid
                return
        except Exception as e_box:
            self.logger.error(f"{log_prefix}: Error creating filter box: {e_box}. Yielding all.", exc_info=True)
            async for feature_error_case in features: yield feature_error_case
            return

        async for feature in features:
            if not feature.geometry:
                if config.mode == ExtentFilterMode.DISJOINT: yield feature # Disjoint from nothing is true
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if not shapely_geom or shapely_geom.is_empty:
                if config.mode == ExtentFilterMode.DISJOINT: yield feature
                continue

            match = False
            try:
                if config.mode == ExtentFilterMode.INTERSECTS:
                    match = filter_box.intersects(shapely_geom)
                elif config.mode == ExtentFilterMode.CONTAINS:
                    match = filter_box.contains(shapely_geom)
                elif config.mode == ExtentFilterMode.WITHIN:
                    match = filter_box.within(shapely_geom) # This means filter_box is within shapely_geom
                    # To check if shapely_geom is within filter_box:
                    # match = shapely_geom.within(filter_box)
                elif config.mode == ExtentFilterMode.DISJOINT:
                    match = filter_box.disjoint(shapely_geom)
                elif config.mode == ExtentFilterMode.TOUCHES:
                    match = filter_box.touches(shapely_geom)
                elif config.mode == ExtentFilterMode.CROSSES:
                    match = filter_box.crosses(shapely_geom)
                elif config.mode == ExtentFilterMode.OVERLAPS:
                    match = filter_box.overlaps(shapely_geom)
            except GEOSException as e_pred:
                self.logger.warning(f"{log_prefix}: GEOS error for pred '{config.mode}': {e_pred}. Skipping feature.")
                continue # Skip feature on predicate error
            except Exception as e_gen_pred:
                self.logger.error(f"{log_prefix}: Unexpected pred error '{config.mode}': {e_gen_pred}. Skipping.", exc_info=True)
                continue

            if match:
                yield feature
        self.logger.info(f"{log_prefix}: Completed.")
