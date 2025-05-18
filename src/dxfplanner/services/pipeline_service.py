"""
Service responsible for orchestrating the processing of all layers in a project configuration.
"""
from typing import AsyncIterator, Dict, Tuple
from logging import Logger

from dxfplanner.config import ProjectConfig, LayerConfig
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IDxfWriter, IPipelineService, ILayerProcessorService, IGeometryTransformer, IStyleService
from dxfplanner.core.exceptions import PipelineError
from dxfplanner.core.logging_config import get_logger
from dxfplanner.domain.models.geo_models import GeoFeature

logger = get_logger(__name__)

class PipelineService(IPipelineService):
    """Orchestrates the processing of all layers and writing the final DXF."""

    def __init__(
        self,
        project_config: ProjectConfig,
        layer_processor: ILayerProcessorService,
        dxf_writer: IDxfWriter,
        geometry_transformer: IGeometryTransformer,
        style_service: IStyleService,
        logger: Logger
    ):
        self.project_config = project_config
        self.layer_processor = layer_processor
        self.dxf_writer = dxf_writer
        self.geometry_transformer = geometry_transformer
        self.style_service = style_service
        self.logger = logger
        self.logger.info("PipelineService initialized.")

    async def run_pipeline(self, pipeline_name: str) -> None:
        active_pipeline_config = next((p for p in self.project_config.pipelines if p.name == pipeline_name), None)
        if not active_pipeline_config:
            self.logger.error(f"Pipeline '{pipeline_name}' not found in project configuration.")
            # Consider raising an error or specific handling
            return

        self.logger.info(f"Starting pipeline: {pipeline_name}")

        master_geo_feature_streams: Dict[str, Tuple[LayerConfig, AsyncIterator[GeoFeature]]] = {}

        for layer_name_to_process in active_pipeline_config.layers_to_process:
            layer_conf_to_process = next((lc for lc in self.project_config.layers if lc.name == layer_name_to_process), None)
            if not layer_conf_to_process:
                self.logger.warning(f"Layer '{layer_name_to_process}' specified in pipeline '{pipeline_name}' layers_to_process not found in global layer configurations. Skipping.")
                continue
            if not layer_conf_to_process.enabled:
                self.logger.info(f"Layer '{layer_name_to_process}' is configured as disabled. Skipping processing for this layer in pipeline '{pipeline_name}'.")
                continue

            self.logger.info(f"Pipeline '{pipeline_name}': Processing LayerConfig '{layer_conf_to_process.name}'...")
            processed_layer_geo_streams = await self.layer_processor.process_layer(layer_conf_to_process)

            for conceptual_layer_name, (original_lc, geo_stream) in processed_layer_geo_streams.items():
                if conceptual_layer_name in master_geo_feature_streams:
                    self.logger.warning(f"Conceptual layer '{conceptual_layer_name}' produced by LayerConfig '{layer_conf_to_process.name}' (key: {original_lc.name}) overwrites an existing stream. This may be due to multiple LayerConfigs producing outputs with the same name.")
                master_geo_feature_streams[conceptual_layer_name] = (original_lc, geo_stream)

        self.logger.info(f"Pipeline '{pipeline_name}': Collected {len(master_geo_feature_streams)} total conceptual GeoFeature streams: {list(master_geo_feature_streams.keys())}")

        dxf_entities_for_writer: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]] = {}

        if not active_pipeline_config.layers_to_write:
            self.logger.warning(f"Pipeline '{pipeline_name}' has an empty 'layers_to_write' list. No DXF entities will be explicitly selected for writing.")
        else:
            self.logger.info(f"Pipeline '{pipeline_name}': Preparing DXF entities for layers specified in layers_to_write: {active_pipeline_config.layers_to_write}")
            for layer_name_to_write in active_pipeline_config.layers_to_write:
                if layer_name_to_write not in master_geo_feature_streams:
                    self.logger.warning(f"Layer '{layer_name_to_write}' specified in pipeline '{pipeline_name}' layers_to_write was not found among the produced conceptual GeoFeature streams. Skipping '{layer_name_to_write}'.")
                    continue

                original_layer_conf_for_styling, geo_feature_stream = master_geo_feature_streams[layer_name_to_write]

                self.logger.info(f"Pipeline '{pipeline_name}': Transforming GeoFeatures for conceptual layer '{layer_name_to_write}' to DxfEntities. Styling context from LayerConfig: '{original_layer_conf_for_styling.name}'. Target DXF Layer: '{layer_name_to_write}'.")

                async def transform_stream_for_layer(
                    gfs: AsyncIterator[GeoFeature],
                    styling_lc: LayerConfig,
                    target_dxf_layer_name: str
                ) -> AsyncIterator[AnyDxfEntity]:
                    async for geo_feature in gfs:
                        if not geo_feature.geometry:
                            self.logger.debug(f"Skipping GeoFeature with no geometry for target layer '{target_dxf_layer_name}'. Attributes: {geo_feature.attributes}")
                            continue
                        # Ensure necessary services are available, e.g., self.style_service, self.geometry_transformer
                        async for dxf_entity in self.geometry_transformer.transform_feature_to_dxf_entities(
                            feature=geo_feature,
                            layer_config=styling_lc,
                            style_service=self.style_service,
                            output_target_layer_name=target_dxf_layer_name
                        ):
                            yield dxf_entity

                dxf_entity_stream_for_this_layer = transform_stream_for_layer(
                    geo_feature_stream, original_layer_conf_for_styling, layer_name_to_write
                )

                # Key is the target DXF layer name. LayerConfig is for styling context.
                dxf_entities_for_writer[layer_name_to_write] = (original_layer_conf_for_styling, dxf_entity_stream_for_this_layer)

        if dxf_entities_for_writer:
            self.logger.info(f"Pipeline '{pipeline_name}': Calling DxfWriter with {len(dxf_entities_for_writer)} streams for target DXF layers: {list(dxf_entities_for_writer.keys())}")
            output_path = self.project_config.dxf_writer.output_filepath
            if not output_path:
                self.logger.error(f"Pipeline '{pipeline_name}': Output DXF file path is not configured in project_config.dxf_writer.output_filepath. Cannot write DXF.")
                # Or raise an error, or decide on a default behavior if appropriate
                # For now, let's log and skip writing, DxfWriter might also raise an error if path is None/empty
                return # Or handle more gracefully
            await self.dxf_writer.write_drawing(
                file_path=output_path,
                entities_by_layer_config=dxf_entities_for_writer
            )
        else:
            self.logger.warning(f"Pipeline '{pipeline_name}': No DXF entity streams prepared for DxfWriter. DXF file may be empty or only contain default layer setup.")
            output_path = self.project_config.dxf_writer.output_filepath
            if not output_path:
                self.logger.error(f"Pipeline '{pipeline_name}': Output DXF file path is not configured in project_config.dxf_writer.output_filepath for empty write. Cannot write DXF.")
                return # Or handle
            await self.dxf_writer.write_drawing(
                file_path=output_path,
                entities_by_layer_config={}
            )

        self.logger.info(f"Pipeline '{pipeline_name}' finished.")
