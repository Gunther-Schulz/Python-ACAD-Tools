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
        # Cache for sanitized layer names if needed, or dxf_writer handles it
        # self.layer_name_cache: Dict[str, str] = {}
        self.logger.info("LegendGenerationService initialized.")

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
        current_y = await self._create_legend_main_titles(
            doc, msp, legend_config, current_x, current_y, legend_tag_prefix, app_id
        )

        current_y -= layout.group_spacing

        for group_conf in legend_config.groups:
            group_layer_name = self._get_sanitized_layer_name(f"Legend_{legend_config.id}_{group_conf.name}")
            current_y = await self._create_legend_group(
                doc, msp, group_conf, legend_config, group_layer_name, current_x, current_y, legend_tag_prefix, app_id
            )
            current_y -= layout.group_spacing # Spacing after each group

        # Optionally draw a background box (after all content is placed to get extents)
        if legend_config.background_box_enabled:
            # This would require collecting all created entities for this legend,
            # calculating their total bounding box, and then drawing a rectangle.
            # This is a more advanced feature for self.dxf_writer or a utility.
            self.logger.info(f"Background box for legend '{legend_config.id}' requested but not yet implemented.")

    async def _create_legend_main_titles(
        self,
        doc: Any, msp: Any,
        legend_config: LegendDefinitionConfig,
        current_x: float, current_y: float,
        legend_tag_prefix: str,
        app_id: Optional[str] # Added app_id
    ) -> float:
        layout = legend_config.layout
        title_layer_name = self._get_sanitized_layer_name(f"Legend_{legend_config.id}_Title")

        # Create a dummy source for the temporary LayerConfig
        dummy_source = GeoJSONSourceConfig(path="internal_legend_layer.geojson", type=DataSourceType.GEOJSON)

        if legend_config.title:
            title_style_props = self.style_service.get_text_style_properties(
                style_reference=legend_config.overall_title_text_style_inline if legend_config.overall_title_text_style_inline else legend_config.overall_title_text_style_preset_name,
            )
            if not title_style_props or (not title_style_props.font_name_or_style_preset and not legend_config.overall_title_text_style_preset_name and not legend_config.overall_title_text_style_inline):
                self.logger.warning(f"No title text style found for legend '{legend_config.id}'. Using defaults.")
                title_style_props = TextStylePropertiesConfig() # Default empty style

            # Create LayerStyleConfig for the MTEXT entity
            # Layer properties for the text itself (color, linetype, etc.) will be part of text_style within LayerStyleConfig
            # The main color/linetype of LayerStyleConfig here would be for the layer the text is on, if not overridden by text_style's color.

            # CORRECTED CALL: Pass a LayerConfig object
            temp_layer_cfg_title = LayerConfig(name=title_layer_name, source=dummy_source)
            layer_display_properties = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_title)

            legend_item_layer_style = LayerStyleConfig(
                name=title_layer_name,
                color=layer_display_properties.color, # Color for the layer
                linetype=layer_display_properties.linetype, # Linetype for the layer
                lineweight=layer_display_properties.lineweight,
                transparency=layer_display_properties.transparency,
                plot=layer_display_properties.plot,
                text_style=title_style_props # Specific text style properties
            )

            mtext_model = DxfMText(
                text_content=legend_config.title,
                insertion_point=(current_x, current_y, 0),
                layer=title_layer_name,
                style=title_style_props.font_name_or_style_preset or "Standard",
                char_height=title_style_props.height or 1.0,
                rotation=title_style_props.rotation_degrees or 0.0, # DxfMText uses 'rotation'
                attachment_point=title_style_props.attachment_point.upper() if title_style_props.attachment_point else None, # Pass string, converter handles specific ezdxf const
                width=layout.max_text_width,
                line_spacing_factor=title_style_props.paragraph_props.line_spacing_factor if title_style_props.paragraph_props else None,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, f"{legend_tag_prefix}_main_title")] if app_id else None
            )
            # XDATA: The legend_item_id (e.g., f"{legend_tag_prefix}_main_title") needs to be passed to the converter service.
            # This requires DxfEntityConverterService.add_dxf_entity_to_modelspace to accept legend_item_id or similar.
            # For now, this is a gap to be addressed in the converter or DxfEntity model.

            created_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, doc, mtext_model, legend_item_layer_style # Pass the LayerStyleConfig
            )
            actual_height = 0.0
            if created_entity:
                try:
                    bbox = ezdxf.bbox.extents([created_entity], fast=True)
                    if bbox.has_data: actual_height = bbox.size.y
                except Exception as e_bbox: self.logger.warning(f"Could not calculate bbox for legend title MTEXT: {e_bbox}")

            current_y -= actual_height + layout.title_spacing_to_content

        if legend_config.subtitle:
            subtitle_style_props = self.style_service.get_text_style_properties(
                style_reference=legend_config.overall_subtitle_text_style_inline if legend_config.overall_subtitle_text_style_inline else legend_config.overall_subtitle_text_style_preset_name
            )
            if not subtitle_style_props or (not subtitle_style_props.font_name_or_style_preset and not legend_config.overall_subtitle_text_style_preset_name and not legend_config.overall_subtitle_text_style_inline):
                self.logger.warning(f"No subtitle text style found for legend '{legend_config.id}'. Using defaults.")
                subtitle_style_props = TextStylePropertiesConfig()

            # CORRECTED CALL: Pass a LayerConfig object
            temp_layer_cfg_subtitle = LayerConfig(name=title_layer_name, source=dummy_source) # Still uses title_layer_name for the subtitle's layer
            layer_display_properties_sub = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_subtitle)
            legend_item_layer_style_sub = LayerStyleConfig(
                name=title_layer_name,
                color=layer_display_properties_sub.color,
                linetype=layer_display_properties_sub.linetype,
                lineweight=layer_display_properties_sub.lineweight,
                transparency=layer_display_properties_sub.transparency,
                plot=layer_display_properties_sub.plot,
                text_style=subtitle_style_props
            )

            mtext_subtitle_model = DxfMText(
                text_content=legend_config.subtitle,
                insertion_point=(current_x, current_y, 0),
                layer=title_layer_name,
                style=subtitle_style_props.font_name_or_style_preset or "Standard",
                char_height=subtitle_style_props.height or 1.0,
                rotation=subtitle_style_props.rotation_degrees or 0.0,
                attachment_point=subtitle_style_props.attachment_point.upper() if subtitle_style_props.attachment_point else None,
                width=layout.max_text_width,
                line_spacing_factor=subtitle_style_props.paragraph_props.line_spacing_factor if subtitle_style_props.paragraph_props else None,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, f"{legend_tag_prefix}_main_subtitle")] if app_id else None
            )

            created_subtitle_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, doc, mtext_subtitle_model, legend_item_layer_style_sub
            )
            actual_height_sub = 0.0
            if created_subtitle_entity:
                try:
                    bbox_sub = ezdxf.bbox.extents([created_subtitle_entity], fast=True)
                    if bbox_sub.has_data: actual_height_sub = bbox_sub.size.y
                except Exception as e_bbox_sub: self.logger.warning(f"Could not calculate bbox for legend subtitle MTEXT: {e_bbox_sub}")

            current_y -= actual_height_sub + layout.subtitle_spacing_after_title

        return current_y

    async def _create_legend_group(
        self, doc: Any, msp: Any,
        group_config: LegendGroupConfig,
        legend_definition: LegendDefinitionConfig,
        group_layer_name: str,
        current_x: float, current_y: float,
        legend_tag_prefix: str,
        app_id: Optional[str] # Added app_id
    ) -> float:
        layout = legend_definition.layout
        original_y_for_group = current_y
        dummy_source = GeoJSONSourceConfig(path="internal_legend_layer.geojson", type=DataSourceType.GEOJSON) # ADDED dummy_source

        self.logger.debug(f"Creating group: {group_config.name} on layer {group_layer_name}")

        group_title_style_props = self.style_service.get_text_style_properties(
            style_reference=group_config.title_text_style_inline if group_config.title_text_style_inline else group_config.title_text_style_preset_name,
            layer_config_fallback=None # Group title style should be self-contained or from preset
        )
        if not group_title_style_props or (not group_title_style_props.font_name_or_style_preset and not group_config.title_text_style_preset_name and not group_config.title_text_style_inline):
            self.logger.warning(f"No text style found for group title '{group_config.name}' in legend '{legend_definition.id}'. Using defaults.")
            group_title_style_props = TextStylePropertiesConfig()

        # CORRECTED CALL: Pass a LayerConfig object
        temp_layer_cfg_group_title = LayerConfig(name=group_layer_name, source=dummy_source)
        layer_display_properties_group_title = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_group_title)

        group_title_layer_style = LayerStyleConfig(
            name=group_layer_name,
            color=layer_display_properties_group_title.color,
            linetype=layer_display_properties_group_title.linetype,
            lineweight=layer_display_properties_group_title.lineweight,
            transparency=layer_display_properties_group_title.transparency,
            plot=layer_display_properties_group_title.plot,
            text_style=group_title_style_props
        )

        mtext_grp_title_model = DxfMText(
            text_content=group_config.name,
            insertion_point=(current_x, current_y, 0),
            layer=group_layer_name,
            style=group_title_style_props.font_name_or_style_preset or "Standard",
            char_height=group_title_style_props.height or 1.0,
            rotation=group_title_style_props.rotation_degrees or 0.0,
            attachment_point=group_title_style_props.attachment_point.upper() if group_title_style_props.attachment_point else None,
            width=layout.max_text_width,
            line_spacing_factor=group_title_style_props.paragraph_props.line_spacing_factor if group_title_style_props.paragraph_props else None,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, f"{legend_tag_prefix}_group_{self._sanitize_for_tag(group_config.name)}_title")] if app_id else None
        )

        created_grp_title_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
            msp, doc, mtext_grp_title_model, group_title_layer_style
        )
        actual_height_grp_title = 0.0
        if created_grp_title_entity:
            try:
                bbox_grp_title = ezdxf.bbox.extents([created_grp_title_entity], fast=True)
                if bbox_grp_title.has_data: actual_height_grp_title = bbox_grp_title.size.y
            except Exception as e_bbox_grp_title: self.logger.warning(f"Could not calculate bbox for group title MTEXT: {e_bbox_grp_title}")

        current_y -= actual_height_grp_title + layout.title_spacing_to_content

        if group_config.subtitle:
            group_subtitle_style_props = self.style_service.get_text_style_properties(
                style_reference=group_config.subtitle_text_style_inline if group_config.subtitle_text_style_inline else group_config.subtitle_text_style_preset_name
            )
            if not group_subtitle_style_props or (not group_subtitle_style_props.font_name_or_style_preset and not group_config.subtitle_text_style_preset_name and not group_config.subtitle_text_style_inline):
                self.logger.debug(f"No subtitle style for group '{group_config.name}', using default.")
                group_subtitle_style_props = TextStylePropertiesConfig()

            layer_display_props_grp_sub = self.style_service.get_layer_display_properties(layer_name_or_config=group_layer_name)
            legend_item_layer_style_grp_sub = LayerStyleConfig(
                name=group_layer_name,
                color=layer_display_props_grp_sub.color,
                linetype=layer_display_props_grp_sub.linetype,
                lineweight=layer_display_props_grp_sub.lineweight,
                transparency=layer_display_props_grp_sub.transparency,
                plot=layer_display_props_grp_sub.plot,
                text_style=group_subtitle_style_props
            )

            mtext_grp_subtitle_model = DxfMText(
                text_content=group_config.subtitle,
                insertion_point=(current_x, current_y, 0),
                layer=group_layer_name,
                style=group_subtitle_style_props.font_name_or_style_preset or "Standard",
                char_height=group_subtitle_style_props.height or 1.0,
                rotation=group_subtitle_style_props.rotation_degrees or 0.0,
                attachment_point=group_subtitle_style_props.attachment_point.upper() if group_subtitle_style_props.attachment_point else None,
                width=layout.max_text_width,
                line_spacing_factor=group_subtitle_style_props.paragraph_props.line_spacing_factor if group_subtitle_style_props.paragraph_props else None,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, f"{legend_tag_prefix}_group_{self._sanitize_for_tag(group_config.name)}_subtitle")] if app_id else None
            )

            created_grp_subtitle_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, doc, mtext_grp_subtitle_model, legend_item_layer_style_grp_sub
            )
            actual_height_grp_sub = 0.0
            if created_grp_subtitle_entity:
                try:
                    bbox_grp_sub = ezdxf.bbox.extents([created_grp_subtitle_entity], fast=True)
                    if bbox_grp_sub.has_data: actual_height_grp_sub = bbox_grp_sub.size.y
                except Exception as e_bbox_grp_sub: self.logger.warning(f"Could not calculate bbox for group subtitle MTEXT: {e_bbox_grp_sub}")

            current_y -= actual_height_grp_sub + layout.subtitle_spacing_after_title

        for idx, item_conf in enumerate(group_config.items):
            current_y = await self._create_legend_item(
                doc, msp, item_conf, legend_definition, group_layer_name, current_x, current_y,
                legend_tag_prefix, self._sanitize_for_tag(f"group_{group_config.name}_item_{item_conf.name}_{idx}"), app_id
            )
        return current_y

    async def _create_legend_item(
        self, doc: Any, msp: Any,
        item_config: LegendItemConfig,
        legend_definition: LegendDefinitionConfig, # To access global layout and style presets
        item_layer_name: str, # This is actually the group layer name
        current_x: float, current_y: float,
        legend_tag_prefix: str, # Added legend_tag_prefix
        item_tag_suffix: str, # Added item_tag_suffix for specific XDATA
        app_id: Optional[str] # Added app_id
    ) -> float:
        layout = legend_definition.layout
        item_text_x = current_x + layout.swatch_width + layout.swatch_to_text_spacing
        item_text_y = current_y
        dummy_source = GeoJSONSourceConfig(path="internal_legend_layer.geojson", type=DataSourceType.GEOJSON) # ADDED dummy_source

        self.logger.debug(f"Creating item: {item_config.name} on layer {item_layer_name}")

        item_swatch_style_config = item_config.item_style
        swatch_legend_item_id_tag = f"{legend_tag_prefix}_swatch_{item_tag_suffix}" # Used for swatch entities

        # Resolve the style for the swatch geometry itself
        # MODIFIED: Use StyleService
        swatch_object_style = self.style_service.get_resolved_style_object(
            preset_name=item_swatch_style_config.style_preset_name,
            inline_definition=item_swatch_style_config.style_inline,
            # No override definition in LegendItemStyleConfig currently
            context_name=f"legend item {item_config.name} swatch"
        )
        # Ensure swatch_object_style is not None (StyleService returns default if all inputs are None)
        if swatch_object_style is None: # Should not happen with current StyleService logic
             self.logger.warning(f"Could not resolve swatch style for item '{item_config.name}'. Using default StyleObjectConfig.")
             swatch_object_style = StyleObjectConfig()

        # Define swatch bounds
        x1, y1_swatch_top = current_x, current_y
        x2, y2_swatch_bottom = x1 + layout.item_swatch_width, y1_swatch_top - layout.item_swatch_height

        # Refactored swatch creation: _create_swatch_xxx methods will return List[AnyDxfEntity] (domain models)
        swatch_domain_models: List[AnyDxfEntity] = []
        if item_swatch_style_config.item_type == 'area':
            swatch_domain_models = await self._create_swatch_area(
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id, # Pass app_id
                specific_legend_item_tag=swatch_legend_item_id_tag # Pass specific tag
            )
        elif item_swatch_style_config.item_type == 'line':
            swatch_domain_models = await self._create_swatch_line(
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id, # Pass app_id
                specific_legend_item_tag=swatch_legend_item_id_tag # Pass specific tag
            )
        elif item_swatch_style_config.item_type == 'diagonal_line':
            swatch_domain_models = await self._create_swatch_diagonal_line(
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id, # Pass app_id
                specific_legend_item_tag=swatch_legend_item_id_tag # Pass specific tag
            )
        elif item_swatch_style_config.item_type == 'empty':
            swatch_domain_models = await self._create_swatch_empty(
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id, # Pass app_id
                specific_legend_item_tag=swatch_legend_item_id_tag # Pass specific tag
            )
        else:
            self.logger.error(f"Unknown legend item type: {item_swatch_style_config.item_type} for item '{item_config.name}'")
            # Return current_y decremented by swatch height and item spacing to skip the item
            return current_y - layout.item_swatch_height - layout.item_spacing

        # Convert domain models to ezdxf entities and collect them
        created_swatch_ezdxf_entities = []
        for domain_model in swatch_domain_models:
            # Create LayerStyleConfig for this specific swatch entity
            # swatch_object_style is a StyleObjectConfig containing layer_props and hatch_props
            # This LayerStyleConfig is crucial for the DxfEntityConverterService

            default_border_color = ColorModel(r=0,g=0,b=0) # Black
            default_linetype = "Continuous"
            default_lineweight = 0 # Default/thin

            current_layer_props = swatch_object_style.layer_props if swatch_object_style else None
            current_hatch_props = swatch_object_style.hatch_props if swatch_object_style else None
            # current_text_props = swatch_object_style.text_props if swatch_object_style else None # Should be None for swatches

            effective_layer_style = LayerStyleConfig(name=domain_model.layer or item_layer_name)

            if isinstance(domain_model, DxfHatch):
                effective_layer_style.color = current_layer_props.color if current_layer_props and current_layer_props.color else None
                effective_layer_style.hatch_pattern = current_hatch_props
            elif isinstance(domain_model, (DxfLWPolyline, DxfLine)):
                is_border_for_diagonal = False
                if domain_model.xdata_tags and domain_model.xdata_tags[-1]:
                    tag_value = domain_model.xdata_tags[-1][1]
                    if isinstance(tag_value, str) and "border" in tag_value and item_swatch_style_config.item_type == 'diagonal_line':
                        is_border_for_diagonal = True

                if is_border_for_diagonal:
                    effective_layer_style.color = default_border_color
                    effective_layer_style.linetype = default_linetype
                    effective_layer_style.lineweight = default_lineweight
                elif current_layer_props:
                    effective_layer_style.color = current_layer_props.color
                    effective_layer_style.linetype = current_layer_props.linetype
                    effective_layer_style.lineweight = current_layer_props.lineweight
                    effective_layer_style.transparency = current_layer_props.transparency
                    effective_layer_style.plot = current_layer_props.plot
                else:
                    effective_layer_style.color = default_border_color
                    effective_layer_style.linetype = default_linetype
            elif isinstance(domain_model, DxfInsert):
                 if current_layer_props:
                    effective_layer_style.color = current_layer_props.color

            if effective_layer_style.color is None and not isinstance(domain_model, DxfHatch):
                 effective_layer_style.color = default_border_color

            ezdxf_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, doc, domain_model, effective_layer_style
            )
            if ezdxf_entity:
                created_swatch_ezdxf_entities.append(ezdxf_entity)

        item_swatch_bbox = await self.dxf_writer.get_entities_bbox(created_swatch_ezdxf_entities)
        if item_swatch_bbox is None:
            item_swatch_bbox_min_y = y2_swatch_bottom
            item_swatch_bbox_max_y = y1_swatch_top
        else:
            item_swatch_bbox_min_y = item_swatch_bbox.extmin.y
            item_swatch_bbox_max_y = item_swatch_bbox.extmax.y

        item_center_y = (item_swatch_bbox_min_y + item_swatch_bbox_max_y) / 2

        text_x = x2 + layout.text_offset_from_swatch
        text_entities = []

        # Resolve item text style
        item_text_style_props = self.style_service.get_text_style_properties(
            style_reference=item_config.item_text_style_inline if item_config.item_text_style_inline else item_config.item_text_style_preset_name,
            # No layer_config_fallback here, item styles are specific
        )
        if not item_text_style_props or (not item_text_style_props.font_name_or_style_preset and not item_config.item_text_style_preset_name and not item_config.item_text_style_inline):
            self.logger.warning(f"No text style found for legend item '{item_config.label}'. Using defaults.")
            item_text_style_props = TextStylePropertiesConfig()

        # LayerStyleConfig for the item's text
        # CORRECTED CALL: Pass a LayerConfig object
        temp_layer_cfg_item_text = LayerConfig(name=item_layer_name, source=dummy_source) # Text is on the group's layer
        layer_display_properties_item_text = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_item_text)

        item_text_dxf_layer_style = LayerStyleConfig(
            name=item_layer_name, # Text is on the group's layer
            color=layer_display_properties_item_text.color,
            linetype=layer_display_properties_item_text.linetype,
            lineweight=layer_display_properties_item_text.lineweight,
            transparency=layer_display_properties_item_text.transparency,
            plot=layer_display_properties_item_text.plot,
            text_style=item_text_style_props
        )

        # Create item name text model
        item_name_legend_tag = f"{legend_tag_prefix}_text_name_{item_tag_suffix}"
        mtext_item_name_model = DxfMText(
            text_content=item_config.name,
            insertion_point=(text_x, item_center_y, 0), # Initial Y, will be adjusted
            layer=item_layer_name,
            style=item_text_style_props.font_name_or_style_preset or "Standard",
            char_height=item_text_style_props.height or 1.0,
            rotation=item_text_style_props.rotation_degrees or 0.0,
            attachment_point=item_text_style_props.attachment_point.upper() if item_text_style_props.attachment_point else 'MIDDLE_LEFT',
            width=layout.max_text_width - layout.item_swatch_width - layout.text_offset_from_swatch,
            line_spacing_factor=item_text_style_props.paragraph_props.line_spacing_factor if item_text_style_props.paragraph_props else None,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, item_name_legend_tag)] if app_id else None
        )
        # XDATA for item name - to be handled by converter if it gets legend_item_id
        # legend_item_id_name_tag = f"{legend_tag_prefix}_item_{item_tag_suffix}_name"

        name_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
            msp, doc, mtext_item_name_model, item_text_dxf_layer_style
        )
        if name_entity: text_entities.append(name_entity)

        # Create item subtitle text if present
        if item_config.subtitle:
            item_subtitle_style_props = self.style_service.get_text_style_properties(
                style_reference=item_config.subtitle_text_style_inline if item_config.subtitle_text_style_inline else item_config.subtitle_text_style_preset_name
            )
            if not item_subtitle_style_props or (not item_subtitle_style_props.font_name_or_style_preset and not item_config.subtitle_text_style_preset_name and not item_config.subtitle_text_style_inline):
                self.logger.debug(f"No subtitle style for item '{item_config.name}', using default.")
                item_subtitle_style_props = TextStylePropertiesConfig()

            item_subtitle_layer_display_props = self.style_service.get_layer_display_properties(layer_name_or_config=item_layer_name)
            item_subtitle_layer_style = LayerStyleConfig(
                name=item_layer_name,
                color=item_subtitle_layer_display_props.color,
                linetype=item_subtitle_layer_display_props.linetype,
                lineweight=item_subtitle_layer_display_props.lineweight,
                transparency=item_subtitle_layer_display_props.transparency,
                plot=item_subtitle_layer_display_props.plot,
                text_style=item_subtitle_style_props
            )

            # Position subtitle below main text; get bbox of main text first
            # This part requires name_entity to be the ezdxf entity, which it is now.
            main_text_bbox = await self.dxf_writer.get_entities_bbox([name_entity]) if name_entity else None
            name_actual_height_approx = item_text_style_props.height or 1.0 # Fallback if bbox fails
            if main_text_bbox and main_text_bbox.has_data: name_actual_height_approx = main_text_bbox.size.y

            subtitle_y_pos = (main_text_bbox.extmin.y - layout.subtitle_spacing_after_title) if main_text_bbox and main_text_bbox.has_data else (item_center_y - name_actual_height_approx - layout.subtitle_spacing_after_title)

            item_subtitle_legend_tag = f"{legend_tag_prefix}_text_subtitle_{item_tag_suffix}"
            mtext_item_subtitle_model = DxfMText(
                text_content=item_config.subtitle,
                insertion_point=(text_x, subtitle_y_pos, 0),
                layer=item_layer_name,
                style=item_subtitle_style_props.font_name_or_style_preset or "Standard",
                char_height=item_subtitle_style_props.height or 1.0,
                rotation=item_subtitle_style_props.rotation_degrees or 0.0,
                attachment_point=item_subtitle_style_props.attachment_point.upper() if item_subtitle_style_props.attachment_point else 'TOP_LEFT',
                width=layout.max_text_width - layout.item_swatch_width - layout.text_offset_from_swatch,
                line_spacing_factor=item_subtitle_style_props.paragraph_props.line_spacing_factor if item_subtitle_style_props.paragraph_props else None,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, item_subtitle_legend_tag)] if app_id else None
            )
            # legend_item_id_subtitle_tag = f"{legend_tag_prefix}_item_{item_tag_suffix}_subtitle"

            subtitle_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, doc, mtext_item_subtitle_model, item_subtitle_layer_style
            )
            if subtitle_entity: text_entities.append(subtitle_entity)

        # Vertically align text block with swatch center
        if text_entities:
            all_text_bbox = await self.dxf_writer.get_entities_bbox(text_entities)
            if all_text_bbox:
                text_center_y = (all_text_bbox.extmin.y + all_text_bbox.extmax.y) / 2
                vertical_adjustment = item_center_y - text_center_y
                await self.dxf_writer.translate_entities(text_entities, 0, vertical_adjustment, 0)
                all_text_bbox = await self.dxf_writer.get_entities_bbox(text_entities) # Update bbox after translate
            else:
                all_text_bbox = None # No text entities or bbox error
        else:
            all_text_bbox = None

        # Determine overall height and adjust current_y
        # Combine swatch bbox and text bbox for overall item extents
        combined_bbox_min_y = item_swatch_bbox_min_y
        combined_bbox_max_y = item_swatch_bbox_max_y

        if all_text_bbox:
            combined_bbox_min_y = min(combined_bbox_min_y, all_text_bbox.extmin.y)
            combined_bbox_max_y = max(combined_bbox_max_y, all_text_bbox.extmax.y)

        # Old code did a translate of all entities based on current_y and combined_bbox.extmax.y
        # This seems complex; simpler to calculate height and decrement current_y.
        # The entities are already placed relative to current_x, current_y (via y1_swatch_top).
        # We just need to know how much vertical space this item consumed.

        total_item_height = combined_bbox_max_y - combined_bbox_min_y
        if total_item_height <= 0: # Fallback if bbox calculation failed or item is zero-height
            total_item_height = layout.item_swatch_height # Use swatch height as a minimum

        current_y -= total_item_height + layout.item_spacing
        return current_y

    async def _create_swatch_area(
        self,
        # doc:Any, msp: Any, # Not needed anymore, converter service handles msp, doc
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig, # Renamed from style to be clear
        item_style_cfg: LegendItemStyleConfig,
        app_id: Optional[str], # Added app_id
        specific_legend_item_tag: str # Added specific_legend_item_tag
    ) -> List[AnyDxfEntity]: # Return list of domain models
        x1, y1, x2, y2 = bounds
        domain_entities: List[AnyDxfEntity] = []

        rect_points_coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

        border_lwpolyline_model = DxfLWPolyline(
            points=rect_points_coords + [(x1,y1)],
            is_closed=True,
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_border")] if app_id else None
        )
        domain_entities.append(border_lwpolyline_model)

        if item_style_cfg.apply_hatch_for_area and style_object_config.hatch_props:
            hatch_path_vertices = rect_points_coords
            dxf_hatch_path = DxfHatchPath(vertices=[(v[0], v[1]) for v in hatch_path_vertices], is_closed=True)

            hatch_model = DxfHatch(
                paths=[dxf_hatch_path],
                pattern_name=style_object_config.hatch_props.pattern_name or "SOLID",
                pattern_scale=style_object_config.hatch_props.scale if style_object_config.hatch_props.scale is not None else 1.0,
                pattern_angle=style_object_config.hatch_props.angle if style_object_config.hatch_props.angle is not None else 0.0,
                hatch_style_enum=(style_object_config.hatch_props.style.upper() if style_object_config.hatch_props.style else 'NORMAL'),
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_hatch")] if app_id else None
            )
            if style_object_config.hatch_props.pattern_color:
                if style_object_config.hatch_props.pattern_color.is_aci_color():
                    hatch_model.color_256 = style_object_config.hatch_props.pattern_color.aci_index
                else:
                    hatch_model.true_color = style_object_config.hatch_props.pattern_color.get_rgb_tuple()

            domain_entities.append(hatch_model)

        if item_style_cfg.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_style_cfg.block_symbol_name,
                insertion_point=((x1 + x2) / 2, (y1 + y2) / 2, 0),
                x_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                y_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                z_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                rotation=item_style_cfg.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        return domain_entities

    async def _create_swatch_line(
        self,
        # doc:Any, msp: Any,
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig,
        app_id: Optional[str], # Added app_id
        specific_legend_item_tag: str # Added specific_legend_item_tag
    ) -> List[AnyDxfEntity]:
        x1, y1, x2, y2 = bounds
        middle_y = (y1 + y2) / 2
        domain_entities: List[AnyDxfEntity] = []

        line_points = [(x1, middle_y), (x2, middle_y)]

        line_model = DxfLWPolyline(
            points=line_points,
            is_closed=False,
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag)] if app_id else None
        )
        domain_entities.append(line_model)

        if item_style_cfg.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_style_cfg.block_symbol_name,
                insertion_point=((x1 + x2) / 2, middle_y, 0),
                x_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                y_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                z_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                rotation=item_style_cfg.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        return domain_entities

    async def _create_swatch_diagonal_line(
        self,
        # doc:Any, msp: Any,
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig,
        app_id: Optional[str], # Added app_id
        specific_legend_item_tag: str # Added specific_legend_item_tag
    ) -> List[AnyDxfEntity]:
        x1, y1, x2, y2 = bounds
        domain_entities: List[AnyDxfEntity] = []

        border_points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1,y1)]
        border_model = DxfLWPolyline(
            points=border_points,
            is_closed=True,
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_border")] if app_id else None
        )
        domain_entities.append(border_model)

        diag_line_model = DxfLine(
            start=Coordinate(x=x1, y=y1, z=0),
            end=Coordinate(x=x2, y=y2, z=0),
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_diag")] if app_id else None
        )
        domain_entities.append(diag_line_model)

        if item_style_cfg.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_style_cfg.block_symbol_name,
                insertion_point=((x1 + x2) / 2, (y1 + y2) / 2, 0),
                x_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                y_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                z_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                rotation=item_style_cfg.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        return domain_entities

    async def _create_swatch_empty(
        self,
        # doc:Any, msp: Any,
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig,
        app_id: Optional[str], # Added app_id
        specific_legend_item_tag: str # Added specific_legend_item_tag
    ) -> List[AnyDxfEntity]:
        x1, y1, x2, y2 = bounds
        domain_entities: List[AnyDxfEntity] = []

        if item_style_cfg.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_style_cfg.block_symbol_name,
                insertion_point=((x1 + x2) / 2, (y1 + y2) / 2, 0),
                x_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                y_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                z_scale=item_style_cfg.block_symbol_scale if item_style_cfg.block_symbol_scale is not None else 1.0,
                rotation=item_style_cfg.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        elif not item_style_cfg.block_symbol_name and style_object_config and style_object_config.layer_props and (
            style_object_config.layer_props.color or
            (style_object_config.layer_props.lineweight is not None and style_object_config.layer_props.lineweight >=0) or
            style_object_config.layer_props.linetype
        ):
            border_points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1,y1)]
            border_model = DxfLWPolyline(
                points=border_points,
                is_closed=True,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_border")] if app_id else None
            )
            domain_entities.append(border_model)
        return domain_entities

    def _get_sanitized_layer_name(self, name: str) -> str:
        name = re.sub(r'[^A-Za-z0-9_\-$]', '_', name)
        return name[:255]

    def _sanitize_for_tag(self, name: str) -> str:
        """Sanitizes a string to be used as part of an XDATA tag or similar identifier."""
        name = re.sub(r'[^A-Za-z0-9_\-]', '_', name)
        return name[:100]
