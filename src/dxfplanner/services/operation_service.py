"""
Service responsible for orchestrating and applying a sequence of data processing operations.
"""
from typing import AsyncIterator, List, Dict, Type
from dxfplanner.config.schemas import AppConfig, AnyOperationConfig, OperationType
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.core.exceptions import DXFPlannerBaseError, ConfigurationError
from dxfplanner.core.logging_config import get_logger

# Import concrete operation implementations
from dxfplanner.geometry.operations import BufferOperation, SimplifyOperation, FieldMappingOperation, ReprojectOperation, CleanGeometryOperation, ExplodeMultipartOperation

logger = get_logger(__name__)

class OperationServiceError(DXFPlannerBaseError):
    """Custom exception for OperationService errors."""
    pass

class OperationService:
    """
    Orchestrates a sequence of data processing operations on features.
    """
    def __init__(self, app_config: AppConfig):
        self._app_config = app_config
        self._operation_map: Dict[OperationType, Type[IOperation]] = {
            OperationType.BUFFER: BufferOperation,
            OperationType.SIMPLIFY: SimplifyOperation,
            OperationType.FIELD_MAPPER: FieldMappingOperation,
            OperationType.REPROJECT: ReprojectOperation,
            OperationType.CLEAN_GEOMETRY: CleanGeometryOperation,
            OperationType.EXPLODE_MULTIPART: ExplodeMultipartOperation,
            # Map other operation types to their classes
        }
        logger.info("OperationService initialized.")

    async def process_features(
        self,
        features: AsyncIterator[GeoFeature],
        operation_configs: List[AnyOperationConfig]
    ) -> AsyncIterator[GeoFeature]:
        """
        Applies a list of configured operations sequentially to a stream of features.

        Args:
            features: The input stream of GeoFeatures.
            operation_configs: A list of operation configurations to apply.

        Yields:
            GeoFeature: The processed GeoFeatures.
        """
        current_features_stream = features

        if not operation_configs:
            logger.debug("No operations to apply. Returning original feature stream.")
            async for feature in current_features_stream:
                yield feature
            return

        logger.info(f"Starting processing of {len(operation_configs)} operations.")

        for op_idx, op_config in enumerate(operation_configs):
            logger.debug(f"Applying operation {op_idx + 1}/{len(operation_configs)}: {op_config.type.value}")

            operation_class = self._operation_map.get(op_config.type)
            if not operation_class:
                msg = f"Unsupported operation type: {op_config.type.value}"
                logger.error(msg)
                raise ConfigurationError(msg)

            try:
                operation_instance: IOperation = operation_class()
            except Exception as e:
                msg = f"Failed to instantiate operation '{op_config.type.value}': {e}"
                logger.error(msg, exc_info=True)
                raise OperationServiceError(msg) from e

            logger.warning(f"Operation '{op_config.type.value}' is a placeholder and will not transform data.")

        if operation_configs:
             logger.warning("OperationService.process_features is currently a placeholder and returns the original feature stream due to unimplemented operations.")

        async for feature in current_features_stream:
             yield feature
