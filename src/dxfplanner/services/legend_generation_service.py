from typing import Any, Dict, List, Optional, Tuple
from logging import Logger
import re # Moved import re to top level
import math # Added for math.radians if not already present for MTEXT

import ezdxf # For ezdxf.bbox
from ezdxf import const as ezdxf_const # For MTEXT consts

from ..config.schemas import (
    ProjectConfig, LegendDefinitionConfig, LegendLayoutConfig, LegendGroupConfig, LegendItemConfig,
    LegendItemStyleConfig, TextStylePropertiesConfig, StyleObjectConfig,
    LayerDisplayPropertiesConfig, HatchPropertiesConfig, ColorModel, LayerConfig # Added more specific style configs, ColorModel, LayerConfig
)
from ..config.reader_schemas import GeoJSONSourceConfig, DataSourceType
from ..domain.interfaces import ILegendGenerator, IDxfWriter, IStyleService, IDxfEntityConverterService
from ..core.exceptions import ConfigurationError # For missing style presets
# Import DxfEntity models and LayerStyleConfig
from ..domain.models.dxf_models import DxfMText, AnyDxfEntity # Assuming DxfMText exists
from ..config.schemas import LayerStyleConfig # Corrected import path
# Import additional DxfEntity models for swatches
from ..domain.models.dxf_models import DxfLWPolyline, DxfHatch, DxfInsert, DxfHatchPath, DxfLine
from ..domain.models.common import Coordinate # ADDED IMPORT
from .helpers.legend_component_factory import LegendComponentFactory # Add this import

# It's better to get SCRIPT_IDENTIFIER from config if it's globally defined
# For now, assume dxf_writer will handle its own script identifier for custom data

class LegendGenerationService(ILegendGenerator):
    """
    Service responsible for generating legends based on configuration
    and adding them to a DXF document.
    """
    def __init__(
        self,
        config: ProjectConfig,
        logger: Logger,
        style_service: IStyleService,
        entity_converter_service: IDxfEntityConverterService
    ):
        self.config = config
        self.logger = logger
        self.style_service = style_service
        self.entity_converter_service = entity_converter_service
        self.component_factory = LegendComponentFactory(
            config=self.config,
            logger=self.logger,
            style_service=self.style_service,
            entity_converter_service=self.entity_converter_service
        )
        # Cache for sanitized layer names if needed, or dxf_writer handles it
        # self.layer_name_cache: Dict[str, str] = {}
        self.logger.info("LegendGenerationService initialized with LegendComponentFactory.")

    async def generate_legends(
        self,
        doc: Any,  # ezdxf.document.Drawing
        msp: Any,  # ezdxf.layouts.Modelspace
        **kwargs: Any
    ) -> None:
        self.logger.info(f"Starting legend generation for {len(self.config.legends)} legend definition(s).")
        if not self.config.legends:
            self.logger.info("No legends configured to generate.")
            return

        for legend_def_config in self.config.legends:
            self.logger.debug(f"Processing legend ID: {legend_def_config.id}")
            await self.render_legend_definition(doc, msp, legend_def_config, **kwargs)

        self.logger.info("Legend generation completed.")

    async def render_legend_definition(
        self,
        doc: Any,
        msp: Any,
        legend_config: LegendDefinitionConfig,
        **kwargs: Any
    ) -> None:
        self.logger.info(f"Generating legend: {legend_config.id} - Title: {legend_config.title or 'N/A'}")
        layout = legend_config.layout
        current_x = layout.position_x
        current_y = layout.position_y
        legend_tag_prefix = f"legend_{legend_config.id}" # Define prefix for this legend
        app_id = self.config.dxf_writer.xdata_application_name # Get app_id for XDATA

        # Clean existing legend entities - IDxfWriter needs a robust way to do this
        # e.g., by a unique legend_id tag in xdata or specific layer prefixing
        # For now, conceptual call:
        # await self.dxf_writer.clear_legend_content(doc, msp, legend_id=legend_config.id) # REMOVED - DxfWriter's responsibility now

        # Create Legend Title & Subtitle
        current_y = await self.component_factory._create_legend_main_titles( # Updated call
            msp, doc.blocks,
            legend_config=legend_config,
            current_x=current_x,
            current_y=current_y,
            legend_tag_prefix=legend_tag_prefix,
            app_id=app_id
        )

        current_y -= layout.group_spacing

        for group_conf in legend_config.groups:
            group_layer_name = self.component_factory._get_sanitized_layer_name(f"Legend_{legend_config.id}_{group_conf.name}")
            current_y = await self.component_factory._create_legend_group(
                msp, doc.blocks,
                group_config=group_conf,
                legend_definition=legend_config,
                group_layer_name=group_layer_name,
                current_x=current_x,
                current_y=current_y,
                legend_tag_prefix=legend_tag_prefix,
                app_id=app_id
            )
            current_y -= layout.group_spacing

        if legend_config.background_box_enabled:
            self.logger.info(f"Background box for legend '{legend_config.id}' requested but not yet implemented.")
