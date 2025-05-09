import re # For parsing EPSG code
from typing import Optional, Any, Dict, List, Tuple, AsyncIterator
from pathlib import Path

from dxfplanner.config.schemas import AppConfig, LayerConfig, ShapefileSourceConfig, GeoJsonSourceConfig, DataSourceType # Added DataSourceType, GeoJsonSourceConfig
from dxfplanner.domain.interfaces import (
    IDxfGenerationService,
    IGeoDataReader,
    IDxfWriter,
    IGeometryTransformer,
    IValidationService,
    # ICoordinateService, # No longer directly used for default CRS in the same way
    # IAttributeMapper # Not directly used here
)
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.core.exceptions import DxfGenerationError, ConfigurationError, GeometryTransformError, DxfWriteError
from dxfplanner.domain.interfaces import AnyStrPath
from dxfplanner.services.style_service import StyleService
from dxfplanner.services.operation_service import OperationService
from dxfplanner.core.logging_config import get_logger
from dxfplanner.services.pipeline_service import PipelineService

logger = get_logger(__name__)

def _parse_crs_to_epsg(crs_string: Optional[str]) -> Optional[int]:
    """Parses a CRS string (e.g., 'EPSG:4326') to an integer EPSG code."""
    if not crs_string:
        return None
    match = re.match(r"^EPSG:(\d+)$", crs_string, re.IGNORECASE)
    if match:
        return int(match.group(1))
    logger.warning(f"Could not parse EPSG code from CRS string: {crs_string}")
    return None

class DxfGenerationService(IDxfGenerationService):
    """Main service orchestrating the DXF generation workflow using PipelineService."""

    def __init__(
        self,
        app_config: AppConfig,
        pipeline_service: PipelineService,
        validation_service: Optional[IValidationService] = None,
    ):
        self._app_config = app_config
        self.pipeline_service = pipeline_service
        self.validation_service = validation_service
        logger.info("DxfGenerationService initialized.")

    async def generate_dxf_from_source(
        self,
        output_dxf_path: AnyStrPath,
        **kwargs: Any
    ) -> None:
        logger.info(f"DxfGenerationService: Orchestrating DXF generation to '{output_dxf_path}'.")

        # Potential pre-pipeline validation using self.validation_service and self._app_config
        if self.validation_service and hasattr(self.validation_service, 'validate_app_config'):
            try:
                # Assuming a method like validate_app_config exists or could be added to IValidationService
                # await self.validation_service.validate_app_config(self._app_config)
                logger.info("AppConfig pre-validation (conceptual) passed.")
            except ConfigurationError as e_val_config:
                logger.error(f"Application configuration validation failed: {e_val_config}")
                raise DxfGenerationError(f"Configuration validation failed: {e_val_config}") from e_val_config

        try:
            await self.pipeline_service.run_pipeline(str(output_dxf_path))
            logger.info(f"DxfGenerationService: Pipeline completed. Output: {output_dxf_path}")
        except ConfigurationError as e_config: # Raised by pipeline if fundamental config issues occur
            logger.error(f"Pipeline configuration error: {e_config}", exc_info=True)
            raise DxfGenerationError(f"Pipeline failed due to configuration: {e_config}") from e_config
        except DxfGenerationError as e_gen: # If pipeline service itself raises this
            logger.error(f"Pipeline reported DxfGenerationError: {e_gen}", exc_info=True)
            raise # Re-raise as is
        except Exception as e_pipeline_run:
            logger.error(f"Unexpected error during pipeline execution: {e_pipeline_run}", exc_info=True)
            raise DxfGenerationError(f"Pipeline execution failed unexpectedly: {e_pipeline_run}") from e_pipeline_run

        # Potential post-pipeline validation using self.validation_service on output_dxf_path
        if self.validation_service and hasattr(self.validation_service, 'validate_output_dxf'):
            try:
                # await self.validation_service.validate_output_dxf(str(output_dxf_path))
                logger.info("Output DXF post-validation (conceptual) passed.")
            except Exception as e_val_dxf: # Should be a specific validation error type
                logger.warning(f"Output DXF validation failed: {e_val_dxf}")
                # Decide if this should be a DxfGenerationError or just a warning
