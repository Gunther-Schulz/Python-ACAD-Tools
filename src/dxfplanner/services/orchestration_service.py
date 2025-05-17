import re # For parsing EPSG code
from typing import Optional, Any, Dict, List, Tuple, AsyncIterator
from pathlib import Path

from dxfplanner.config.schemas import ProjectConfig, LayerConfig, ShapefileSourceConfig, GeoJsonSourceConfig, DataSourceType # Changed AppConfig to ProjectConfig
from dxfplanner.domain.interfaces import (
    IDxfGenerationService,
    IGeoDataReader,
    IDxfWriter,
    IGeometryTransformer,
    IValidationService,
    IPipelineService,
    # ICoordinateService, # No longer directly used for default CRS in the same way
    # IAttributeMapper # Not directly used here
)
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.core.exceptions import DxfGenerationError, ConfigurationError, GeometryTransformError, DxfWriteError, OrchestrationError, PipelineError
from dxfplanner.domain.types import AnyStrPath
from dxfplanner.services.style_service import StyleService
from dxfplanner.services.operation_service import OperationService
from dxfplanner.core.logging_config import get_logger
from dxfplanner.services.pipeline_service import PipelineService

logger = get_logger(__name__)

class DxfGenerationService(IDxfGenerationService):
    """Main service orchestrating the DXF generation workflow using PipelineService."""

    def __init__(
        self,
        project_config: ProjectConfig, # Changed from app_config: AppConfig
        pipeline_service: IPipelineService,
        logger_param: Optional[Any] = None,
        validation_service: Optional[IValidationService] = None,
    ):
        self._project_config = project_config # Changed from self._app_config
        self._pipeline_service = pipeline_service
        self._validation_service = validation_service
        self.logger = logger_param if logger_param else logger
        logger.info("DxfGenerationService initialized.")

    async def generate_dxf_from_source(
        self,
        output_dxf_path: AnyStrPath,
        **kwargs: Any
    ) -> None:
        """
        Orchestrates the full workflow: validate config, run pipeline.
        """
        logger.info(f"DxfGenerationService: Orchestrating DXF generation to '{output_dxf_path}'.")

        try:
            self.logger.info(f"Starting DXF generation for output path: {output_dxf_path}")

            # Validate configuration if a validation service is provided
            if self._validation_service:
                self.logger.debug("Validating application configuration...")
                await self._validation_service.validate_config(self._project_config) # Changed from self._app_config
                self.logger.debug("Configuration validated successfully.")

            # Run the main processing pipeline
            await self._pipeline_service.run_pipeline(
                output_dxf_path=str(output_dxf_path),
                **kwargs
            )
            self.logger.info(f"DXF generation completed successfully for: {output_dxf_path}")

        except PipelineError as e_pipe:
            logger.error(f"Pipeline reported PipelineError: {e_pipe}", exc_info=True)
            raise
        except Exception as e_pipeline_run:
            logger.error(f"Unexpected error during pipeline execution: {e_pipeline_run}", exc_info=True)
            raise DxfGenerationError(f"Pipeline execution failed unexpectedly: {e_pipeline_run}") from e_pipeline_run

        # Potential post-pipeline validation using self._validation_service on output_dxf_path
        if self._validation_service and hasattr(self._validation_service, 'validate_output_dxf'):
            try:
                await self._validation_service.validate_output_dxf(str(output_dxf_path))
                logger.info("Output DXF post-validation passed.")
            except Exception as e_val_dxf: # Should be a specific validation error type
                logger.warning(f"Output DXF validation failed: {e_val_dxf}")
                # Decide if this should be a DxfGenerationError or just a warning
