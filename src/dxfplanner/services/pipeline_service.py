"""
Service responsible for orchestrating the processing of all layers in a project configuration.
"""
from typing import AsyncIterator, Dict, Tuple

from dxfplanner.config import AppConfig, LayerConfig
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IDxfWriter
from dxfplanner.services.layer_processor_service import LayerProcessorService
from dxfplanner.core.exceptions import PipelineError
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class PipelineService:
    """Orchestrates the processing of all layers and writing the final DXF."""

    def __init__(
        self,
        app_config: AppConfig,
        layer_processor: LayerProcessorService,
        dxf_writer: IDxfWriter
    ):
        self.app_config = app_config
        self.layer_processor = layer_processor
        self.dxf_writer = dxf_writer
        logger.info("PipelineService initialized.")

    async def run_pipeline(self, output_dxf_path: str) -> None:
        """
        Runs the full data processing and DXF generation pipeline.

        Args:
            output_dxf_path: The path where the final DXF file will be saved.
        """
        logger.info(f"Starting DXF generation pipeline. Output to: {output_dxf_path}")

        if not self.app_config.layers:
            logger.warning("No layers defined in the application configuration. Output DXF will be empty or minimal.")
            # Still call writer to produce an empty valid DXF with headers/styles if that's desired
            # For now, let DxfWriter handle an empty entities_by_layer_config dictionary.

        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]] = {}
        total_layers_processed = 0
        total_layers_enabled = sum(1 for lc in self.app_config.layers if lc.enabled)

        logger.info(f"Found {len(self.app_config.layers)} configured layers, {total_layers_enabled} enabled.")

        for layer_conf in self.app_config.layers:
            if not layer_conf.enabled:
                logger.info(f"Skipping disabled layer: {layer_conf.name}")
                continue

            logger.info(f"Initiating processing for layer: {layer_conf.name}")
            try:
                # The process_layer method itself is an async generator.
                # We store this generator directly.
                # DxfWriter will iterate over it when it's ready.
                dxf_entity_stream = self.layer_processor.process_layer(layer_conf)
                entities_by_layer_config[layer_conf.name] = (layer_conf, dxf_entity_stream)
                total_layers_processed += 1
            except Exception as e_layer_proc:
                logger.error(f"Failed to initiate processing for layer '{layer_conf.name}': {e_layer_proc}", exc_info=True)
                # Optionally, continue with other layers or halt pipeline
                # For now, continue to allow other layers to process

        if not entities_by_layer_config and total_layers_enabled > 0:
            logger.warning("No DXF entity streams were successfully prepared, though enabled layers were present. Output DXF may be empty.")
        elif not entities_by_layer_config:
            logger.info("No enabled layers with data sources found or processed. Proceeding to write (potentially empty) DXF.")

        try:
            logger.info(f"All layer processing initiated ({total_layers_processed}/{total_layers_enabled} enabled layers). Passing to DXF writer.")
            await self.dxf_writer.write_drawing(
                file_path=output_dxf_path,
                entities_by_layer_config=entities_by_layer_config
            )
            logger.info(f"DXF generation pipeline completed successfully. Output file: {output_dxf_path}")
        except Exception as e_write:
            logger.error(f"Error during DXF writing stage: {e_write}", exc_info=True)
            raise PipelineError(f"DXF writing failed: {e_write}") from e_write
