import re # For parsing EPSG code
from typing import Optional, Any, Dict, List, Tuple, AsyncIterator
from pathlib import Path

from dxfplanner.config.schemas import ProjectConfig, LayerConfig, ShapefileSourceConfig, GeoJSONSourceConfig, DataSourceType # Corrected Casing
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
from dxfplanner.domain.interfaces import AnyStrPath
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
        output_dxf_path: AnyStrPath, # This path is used to update project_config for DxfWriter
        pipeline_name_override: Optional[str] = None, # Optional override for selecting the pipeline
        **kwargs: Any # kwargs is no longer passed to run_pipeline, kept for signature compatibility if CLI passes it
    ) -> None:
        """
        Orchestrates the full workflow: validate config, run pipeline.
        """
        # General log message, specific output path is handled by DxfWriter via project_config
        logger.info(f"DxfGenerationService: Orchestrating DXF generation.")

        # Update project_config with the explicit output path if provided. DxfWriter uses this.
        if output_dxf_path:
             self._project_config.dxf_writer.output_filepath = str(output_dxf_path)
             logger.info(f"DXF output path for DxfWriter set to: {str(output_dxf_path)}")
        else:
            # Ensure there's a default path if none is provided to this method
            if not self._project_config.dxf_writer.output_filepath:
                err_msg_path = "Output DXF path not provided to generate_dxf_from_source and no default in project_config.dxf_writer.output_filepath."
                self.logger.error(err_msg_path)
                raise ConfigurationError(err_msg_path)
            logger.info(f"Using DXF output path from project_config: {self._project_config.dxf_writer.output_filepath}")

        selected_pipeline_name: Optional[str] = None # For logging in except blocks
        try:
            # Validate configuration if a validation service is provided
            if self._validation_service:
                self.logger.debug("Validating application configuration...")
                await self._validation_service.validate_config(self._project_config)
                self.logger.debug("Configuration validated successfully.")

            # Determine the pipeline to run
            if pipeline_name_override:
                # Check if the overridden pipeline name exists
                if not self._project_config.pipelines or not any(p.name == pipeline_name_override for p in self._project_config.pipelines):
                    err_msg = f"Specified pipeline_name_override '{pipeline_name_override}' not found in project configuration pipelines."
                    self.logger.error(err_msg)
                    raise ConfigurationError(err_msg)
                selected_pipeline_name = pipeline_name_override
                self.logger.info(f"Using overridden pipeline: '{selected_pipeline_name}'")
            elif self._project_config.pipelines and len(self._project_config.pipelines) > 0:
                selected_pipeline_name = self._project_config.pipelines[0].name
                self.logger.info(f"Using the first defined pipeline by default: '{selected_pipeline_name}' (Total pipelines defined: {len(self._project_config.pipelines)}). Consider using pipeline_name_override for explicit selection.")
            else:
                err_msg = "No pipelines are defined in the project configuration, and no pipeline_name_override was provided."
                self.logger.error(err_msg)
                raise ConfigurationError(err_msg)

            # Run the main processing pipeline
            self.logger.info(f"Executing pipeline: '{selected_pipeline_name}'")
            await self._pipeline_service.run_pipeline(
                pipeline_name=selected_pipeline_name # MODIFIED: Pass pipeline_name
                # REMOVED: output_dxf_path argument
                # REMOVED: **kwargs argument
            )
            # DxfWriter uses project_config.dxf_writer.output_filepath, which was set/confirmed above.
            final_output_path = self._project_config.dxf_writer.output_filepath
            self.logger.info(f"DXF generation pipeline '{selected_pipeline_name}' completed successfully. Output should be at: {final_output_path}")

        except PipelineError as e_pipe:
            logger.error(f"Pipeline '{selected_pipeline_name if selected_pipeline_name else 'N/A'}' reported PipelineError: {e_pipe}", exc_info=True)
            raise
        except ConfigurationError as e_config:
            logger.error(f"Configuration error related to pipeline selection or paths: {e_config}", exc_info=True)
            raise
        except Exception as e_pipeline_run:
            logger.error(f"Unexpected error during pipeline ('{selected_pipeline_name if selected_pipeline_name else 'N/A'}') execution: {e_pipeline_run}", exc_info=True)
            raise DxfGenerationError(f"Pipeline ('{selected_pipeline_name if selected_pipeline_name else 'N/A'}') execution failed unexpectedly: {e_pipeline_run}") from e_pipeline_run

        # Potential post-pipeline validation using self._validation_service on output_dxf_path
        if self._validation_service and hasattr(self._validation_service, 'validate_output_dxf'):
            try:
                await self._validation_service.validate_output_dxf(str(output_dxf_path))
                logger.info("Output DXF post-validation passed.")
            except Exception as e_val_dxf: # Should be a specific validation error type
                logger.warning(f"Output DXF validation failed: {e_val_dxf}")
                # Decide if this should be a DxfGenerationError or just a warning
