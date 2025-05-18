from typing import AsyncIterator, Optional, List, Any, Dict, Tuple
from pathlib import Path
import asyncio
import math

import ezdxf
from ezdxf.enums import InsertUnits # For setting drawing units
from ezdxf import colors as ezdxf_colors # For ACI color handling
from ezdxf import const as ezdxf_const # For MTEXT constants

from dxfplanner.domain.models.dxf_models import (
    DxfEntity, # DxfLayer removed
    DxfLine, DxfLWPolyline, DxfText, DxfMText, # Added DxfMText
    DxfHatch, DxfHatchPath, # Added DxfHatch and DxfHatchPath
    AnyDxfEntity, Coordinate, DxfInsert, # Added DxfInsert
    DxfArc, DxfCircle, DxfPolyline
)
from dxfplanner.domain.interfaces import IDxfWriter, AnyStrPath, IStyleService, ILegendGenerator, IDxfResourceSetupService, IDxfEntityConverterService, IDxfViewportSetupService
from dxfplanner.core.exceptions import DxfWriteError
from dxfplanner.config.schemas import ProjectConfig, ColorModel, LayerDisplayPropertiesConfig, TextStylePropertiesConfig, HatchPropertiesConfig # Changed AppConfig to ProjectConfig
from dxfplanner.services.style_service import StyleService, StyleObjectConfig # For resolving layer styles
from dxfplanner.core.logging_config import get_logger
from dxfplanner.services.geoprocessing.attribute_mapping_service import AttributeMappingService
from dxfplanner.services.geoprocessing.coordinate_service import CoordinateTransformService
from dxfplanner.domain.models.geo_models import (\
    GeoFeature,\
    PointGeo,\
    PolylineGeo,\
    PolygonGeo,\
    MultiPointGeo,\
    MultiPolylineGeo,\
    MultiPolygonGeo,\
    GeometryCollectionGeo,\
    AnyGeoGeometry\
)
from dxfplanner.config.schemas import (\
    DxfWriterConfig,\
    LayerConfig,\
    AnyOperationConfig,\
    StyleObjectConfig, LayerDisplayPropertiesConfig, TextStylePropertiesConfig, HatchPropertiesConfig # ColorModel removed here
)

# Need BoundingBoxModel from domain models for return type
from dxfplanner.domain.models.common import BoundingBox as BoundingBoxModel
from dxfplanner.config.schemas import LayerStyleConfig, HatchPropertiesConfig, TextStyleConfig, BlockDefinitionConfig # Keep
from dxfplanner.geometry.color_utils import get_color_code, convert_transparency # ADDED
from dxfplanner.geometry.layer_utils import sanitize_layer_name # ADDED

logger = get_logger(__name__)

class DxfWriter(IDxfWriter):
    # --- START OF NEW __init__ METHOD ---
    def __init__(self,
                    project_config: ProjectConfig,
                    style_service: IStyleService,
                    resource_setup_service: IDxfResourceSetupService,
                    entity_converter_service: IDxfEntityConverterService,
                    viewport_setup_service: IDxfViewportSetupService,
                    legend_generator: Optional[ILegendGenerator] = None):
        self.project_config = project_config
        self.writer_config: DxfWriterConfig = project_config.dxf_writer
        self.style_service = style_service
        self.legend_generator = legend_generator
        self.logger = logger # Ensure module logger is used

        # Store injected services
        self.resource_setup_service = resource_setup_service
        self.entity_converter_service = entity_converter_service
        self.viewport_setup_service = viewport_setup_service

    async def _get_or_create_document(self) -> ezdxf.document.Drawing:
        """Gets the current DXF document or creates a new one if none exists or if forced by config."""
        template_path = self.writer_config.template_file
        doc: ezdxf.document.Drawing
        if template_path and Path(template_path).exists():
            try:
                self.logger.info(f"Loading DXF document from template: {template_path}")
                doc = ezdxf.readfile(template_path)
                if self.writer_config.template_clear_modelspace:
                    self.logger.info("Clearing modelspace from template.")
                    msp = doc.modelspace()
                    msp.delete_all_entities()
            except Exception as e:
                self.logger.error(f"Failed to load DXF template '{template_path}': {e}. Creating a new document.", exc_info=True)
                doc = ezdxf.new(dxfversion=self.writer_config.target_dxf_version or 'AC1032') # Consistent use of target_dxf_version
        else:
            if template_path:
                self.logger.warning(f"DXF template path '{template_path}' not found. Creating a new document.")
            else:
                self.logger.info("No DXF template specified. Creating a new document.")
            doc = ezdxf.new(dxfversion=self.writer_config.target_dxf_version or 'AC1032') # Consistent use of target_dxf_version

        # Ensure the configured XDATA application name is registered in the APPID table.
        if self.writer_config.xdata_application_name:
            try:
                doc.appids.add(self.writer_config.xdata_application_name)
                self.logger.debug(f"Ensured APPID '{self.writer_config.xdata_application_name}' is registered.")
            except Exception as e_appid_reg:
                # ezdxf might raise an error for invalid appid names, though unlikely for default.
                self.logger.warning(
                    f"Could not register APPID '{self.writer_config.xdata_application_name}': {e_appid_reg}",
                    exc_info=True
                )
        return doc

    async def write_drawing(
        self,
        file_path: AnyStrPath,
        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]],
    ) -> None:
        self.logger.info(f"Starting DXF drawing generation for: {file_path}")
        p_output_path = Path(file_path)
        if not p_output_path.suffix.lower() == ".dxf":
             raise DxfWriteError(f"Output file path must have a .dxf extension: {p_output_path}")

        doc = await self._get_or_create_document()
        msp = doc.modelspace()

        await self.resource_setup_service.setup_document_resources(doc, entities_by_layer_config)

        all_added_dxf_entities_domain_model: List[AnyDxfEntity] = []

        for layer_name_from_pipeline, (layer_cfg, dxf_entity_models_iter) in entities_by_layer_config.items():
            if not layer_cfg.enabled: # Check from original logic
                self.logger.debug(f"Skipping disabled layer: {layer_cfg.name}")
                continue
            self.logger.info(f"Processing entities for layer: '{layer_cfg.name}' (Source pipeline layer: '{layer_name_from_pipeline}')")

            layer_display_props = self.style_service.get_layer_display_properties(layer_cfg)
            hatch_props = self.style_service.get_hatch_properties(layer_config_fallback=layer_cfg)
            text_props = self.style_service.get_text_style_properties(layer_config_fallback=layer_cfg)

            current_layer_style_config = LayerStyleConfig(
                name=layer_cfg.name,
                color=layer_display_props.color,
                linetype=layer_display_props.linetype,
                lineweight=layer_display_props.lineweight,
                transparency=layer_display_props.transparency,
                plot=layer_display_props.plot,
                hatch_pattern=hatch_props,
                text_style=text_props,
            )

            async for dxf_entity_model in dxf_entity_models_iter:
                created_ezdxf_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                    msp, doc, dxf_entity_model, current_layer_style_config
                )
                if created_ezdxf_entity:
                    app_id = self.writer_config.xdata_application_name
                    if app_id:
                        try:
                            xdata_content = [(1000, f"Processed by {app_id}")]
                            created_ezdxf_entity.set_xdata(app_id, xdata_content)
                        except AttributeError:
                            self.logger.warning(f"Could not attach XDATA to entity {created_ezdxf_entity.dxf.handle}. It might not support XDATA.", exc_info=False)
                        except Exception as e_xdata:
                             self.logger.warning(f"Failed to attach XDATA to entity {created_ezdxf_entity.dxf.handle}: {e_xdata}", exc_info=True)
                    all_added_dxf_entities_domain_model.append(dxf_entity_model)

        # Unified legend generation: uses ProjectConfig.legends via LegendGenerationService.generate_legends
        if self.legend_generator and self.project_config.legends:
            self.logger.info(f"Generating {len(self.project_config.legends)} legend(s) from ProjectConfig.")
            try:
                # generate_legends iterates through self.project_config.legends and calls render_legend_definition for each
                await self.legend_generator.generate_legends(doc, msp)
            except Exception as e_legend:
                self.logger.error(f"Error during legend generation: {e_legend}", exc_info=True)
        elif self.legend_generator:
             self.logger.info("No legends defined in ProjectConfig.legends. Skipping legend generation.")

        await self.viewport_setup_service.setup_drawing_view(doc, msp, all_added_dxf_entities_domain_model)

        if self.writer_config.audit_on_save: # From original logic
            try:
                logger.debug("Performing DXF document audit before saving.")
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, doc.audit)
            except Exception as e_audit:
                logger.warning(f"Error during DXF document audit: {e_audit}", exc_info=True)

        await self._save_document(doc, p_output_path)
        self.logger.info(f"DXF drawing generation complete. File saved to: {p_output_path}")

    async def _save_document(self, doc: ezdxf.document.Drawing, file_path: AnyStrPath) -> None:
        """Saves the DXF document to the specified file path."""
        self.logger.info(f"Saving DXF document to: {file_path}")
        try:
            output_path = Path(file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            doc.saveas(output_path)
            self.logger.info(f"Successfully saved DXF document: {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save DXF document to '{file_path}': {e}", exc_info=True)
            raise

    # --- LEGEND GENERATION SUPPORT METHODS (MODIFIED) ---
    async def clear_legend_content(self, doc: ezdxf.document.Drawing, msp: ezdxf.layouts.Modelspace, legend_id: str) -> None:
        logger.debug(f"Attempting to clear legend content for legend_id: {legend_id}")
        if not self.writer_config.xdata_application_name:
            logger.warning("XDATA application name not configured. Cannot clear legend content by XDATA.")
            return

        entities_to_delete = []
        # Construct the expected prefix for XDATA legend item tags for this specific legend_id
        # This matches the prefixing strategy in LegendGenerationService
        expected_xdata_tag_prefix = f"legend_{legend_id}_"
        app_id = self.writer_config.xdata_application_name

        for entity in msp: # Iterate through all entities in modelspace
            try:
                if entity.has_xdata(app_id):
                    xdata = entity.get_xdata(app_id)
                    # XDATA for legend items is expected to be like:
                    # [(1000, "legend_item"), (1000, "legend_<legend_id>_actual_item_name")]
                    if len(xdata) >= 2 and xdata[0].code == 1000 and xdata[0].value == "legend_item":
                        if xdata[1].code == 1000 and isinstance(xdata[1].value, str) and xdata[1].value.startswith(expected_xdata_tag_prefix):
                            entities_to_delete.append(entity)
                            logger.debug(f"Marked entity {entity.dxf.handle} (type: {entity.dxftype()}) with XDATA value '{xdata[1].value}' for deletion.")
            except AttributeError: # Some entities might not have has_xdata (e.g., unsupported types)
                logger.debug(f"Entity {entity} does not support XDATA, skipping.")
                continue
            except Exception as e:
                logger.warning(f"Error processing entity {entity.dxf.handle if hasattr(entity, 'dxf') else entity} for XDATA: {e}")
                continue

        if entities_to_delete:
            logger.info(f"Found {len(entities_to_delete)} entities to delete for legend_id: {legend_id}")
            for entity in entities_to_delete:
                try:
                    msp.delete_entity(entity)
                    logger.debug(f"Successfully deleted entity {entity.dxf.handle}.")
                except Exception as e:
                    logger.warning(f"Failed to delete entity {entity.dxf.handle}: {e}")
        else:
            logger.info(f"No entities found with XDATA matching prefix '{expected_xdata_tag_prefix}' for legend_id: {legend_id}. No entities deleted.")

    async def get_entities_bbox(
        self,
        entities: List[Any]
    ) -> Optional[BoundingBoxModel]:
        logger.debug(f"Calculating bounding box for {len(entities)} entities.")
        if not entities:
            return None
        try:
            # Filter out None entities that might result from failed creations
            valid_entities = [e for e in entities if e is not None and hasattr(e, 'dxf')]
            if not valid_entities:
                logger.debug("No valid entities provided to calculate bounding box.")
                return None

            ez_bbox = ezdxf.bbox.extents(valid_entities, fast=True)
            if ez_bbox.has_data:
                return BoundingBoxModel(
                    min_x=ez_bbox.extmin.x, min_y=ez_bbox.extmin.y, min_z=ez_bbox.extmin.z,
                    max_x=ez_bbox.extmax.x, max_y=ez_bbox.extmax.y, max_z=ez_bbox.extmax.z
                )
            return None
        except Exception as e:
            logger.error(f"Error calculating bounding box: {e}", exc_info=True)
            return None

    async def translate_entities(
        self,
        entities: List[Any],
        dx: float, dy: float, dz: float
    ) -> None:
        logger.debug(f"Translating {len(entities)} entities by ({dx}, {dy}, {dz}).")
        if not entities:
            return
        try:
            for entity in entities:
                if entity and hasattr(entity, 'translate'):
                    entity.translate(dx, dy, dz)
        except Exception as e:
            logger.error(f"Error translating entities: {e}", exc_info=True)
            # Not raising DxfWriteError here as it might be part of a larger operation
