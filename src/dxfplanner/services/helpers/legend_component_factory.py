from typing import Any, Dict, List, Optional, Tuple
from logging import Logger
import re # Add this

# Config and schema imports (mirroring LegendGenerationService for now)
from ...config.schemas import (
    ProjectConfig, LegendDefinitionConfig, LegendLayoutConfig, LegendGroupConfig, LegendItemConfig,
    LegendItemStyleConfig, TextStylePropertiesConfig, StyleObjectConfig, LayerConfig, LayerDisplayPropertiesConfig, LayerStyleConfig,
    HatchPropertiesConfig # Ensure HatchPropertiesConfig is imported
)
from ...config.reader_schemas import GeoJSONSourceConfig, DataSourceType # For dummy_source if used here
from ...domain.interfaces import IStyleService, IDxfEntityConverterService
from ...domain.models.dxf_models import DxfMText, AnyDxfEntity, DxfLWPolyline, DxfHatch, DxfInsert, DxfHatchPath, DxfLine
from ...domain.models.common import Coordinate
from ...core.exceptions import ConfigurationError # If style preset errors are handled here
import ezdxf # Keep this if ezdxf.const or other top-level things are used.
from ezdxf import bbox # ADD THIS IMPORT specifically for bbox
from ...config.common_schemas import ColorModel # ADD THIS IMPORT

# For ezdxf type hints if necessary, though actual ezdxf ops should be in converter
# import ezdxf
# from ezdxf import const as ezdxf_const


class LegendComponentFactory:
    """
    Factory class responsible for creating individual components of a DXF legend,
    such as titles, groups, items, and swatches.
    It encapsulates the detailed logic for styling and constructing these components
    as DxfEntity domain models, which are then passed to the DxfEntityConverterService.
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
        self.logger.info("LegendComponentFactory initialized.")

    def _get_sanitized_layer_name(self, name: str) -> str:
        name = re.sub(r"[^A-Za-z0-9_\\-\\$]", '_', name)
        return name[:255]

    async def _create_legend_main_titles(
        self,
        msp: Any,
        block_definition_container: Any,
        legend_config: LegendDefinitionConfig,
        current_x: float,
        current_y: float,
        legend_tag_prefix: str,
        app_id: Optional[str]
    ) -> float:
        layout = legend_config.layout
        title_layer_name = self._get_sanitized_layer_name(f"Legend_{legend_config.id}_Title")
        dummy_source = GeoJSONSourceConfig(path="internal_legend_layer.geojson", type=DataSourceType.GEOJSON)

        if legend_config.title:
            title_style_props = self.style_service.get_text_style_properties(
                style_reference=legend_config.overall_title_text_style_inline if legend_config.overall_title_text_style_inline else legend_config.overall_title_text_style_preset_name,
            )
            if not title_style_props or (not title_style_props.font_name_or_style_preset and not legend_config.overall_title_text_style_preset_name and not legend_config.overall_title_text_style_inline):
                self.logger.warning(f"No title text style found for legend '{legend_config.id}'. Using defaults.")
                title_style_props = TextStylePropertiesConfig()

            temp_layer_cfg_title = LayerConfig(name=title_layer_name, source=dummy_source)
            layer_display_properties = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_title)

            self.logger.debug(f"LSC_Debug _create_legend_main_titles (title): layer_props type: {type(layer_display_properties)}, text_props type: {type(title_style_props)}")
            legend_item_layer_style = LayerStyleConfig(
                layer_props=LayerDisplayPropertiesConfig(
                    color=layer_display_properties.color,
                    linetype=layer_display_properties.linetype,
                    lineweight=layer_display_properties.lineweight,
                    transparency=layer_display_properties.transparency,
                    plot=layer_display_properties.plot
                ),
                text_style=title_style_props
            )

            mtext_model = DxfMText(
                text_content=legend_config.title,
                insertion_point=Coordinate(x=current_x, y=current_y, z=0.0),
                layer=title_layer_name,
                style=title_style_props.font_name_or_style_preset or "Standard",
                char_height=title_style_props.height or 1.0,
                rotation=title_style_props.rotation_degrees or 0.0,
                attachment_point=title_style_props.attachment_point.upper() if title_style_props.attachment_point else None,
                width=layout.max_text_width,
                line_spacing_factor=title_style_props.paragraph_props.line_spacing_factor if title_style_props.paragraph_props else None,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, f"{legend_tag_prefix}_main_title")] if app_id else None
            )

            created_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, block_definition_container, mtext_model, legend_item_layer_style
            )
            actual_height = 0.0
            if created_entity:
                try:
                    extents_data = bbox.extents([created_entity], fast=True)
                    if extents_data.has_data: actual_height = extents_data.size.y
                except Exception as e_bbox: self.logger.warning(f"Could not calculate bbox for legend title MTEXT: {e_bbox}")
            current_y -= actual_height + layout.title_spacing_to_content

        if legend_config.subtitle:
            subtitle_style_props = self.style_service.get_text_style_properties(
                style_reference=legend_config.overall_subtitle_text_style_inline if legend_config.overall_subtitle_text_style_inline else legend_config.overall_subtitle_text_style_preset_name
            )
            if not subtitle_style_props or (not subtitle_style_props.font_name_or_style_preset and not legend_config.overall_subtitle_text_style_preset_name and not legend_config.overall_subtitle_text_style_inline):
                self.logger.warning(f"No subtitle text style found for legend '{legend_config.id}'. Using defaults.")
                subtitle_style_props = TextStylePropertiesConfig()

            temp_layer_cfg_subtitle = LayerConfig(name=title_layer_name, source=dummy_source)
            layer_display_properties_sub = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_subtitle)

            self.logger.debug(f"LSC_Debug _create_legend_main_titles (subtitle): layer_props type: {type(layer_display_properties_sub)}, text_props type: {type(subtitle_style_props)}")
            legend_item_layer_style_sub = LayerStyleConfig(
                layer_props=LayerDisplayPropertiesConfig(
                    color=layer_display_properties_sub.color,
                    linetype=layer_display_properties_sub.linetype,
                    lineweight=layer_display_properties_sub.lineweight,
                    transparency=layer_display_properties_sub.transparency,
                    plot=layer_display_properties_sub.plot
                ),
                text_style=subtitle_style_props
            )

            mtext_subtitle_model = DxfMText(
                text_content=legend_config.subtitle,
                insertion_point=Coordinate(x=current_x, y=current_y, z=0.0),
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
                msp, block_definition_container, mtext_subtitle_model, legend_item_layer_style_sub
            )
            actual_height_sub = 0.0
            if created_subtitle_entity:
                try:
                    extents_data_sub = bbox.extents([created_subtitle_entity], fast=True)
                    if extents_data_sub.has_data: actual_height_sub = extents_data_sub.size.y
                except Exception as e_bbox_sub: self.logger.warning(f"Could not calculate bbox for legend subtitle MTEXT: {e_bbox_sub}")
            current_y -= actual_height_sub + layout.subtitle_spacing_after_title
        return current_y

    def _sanitize_for_tag(self, name: str) -> str:
        """Sanitizes a string to be used as part of an XDATA tag or similar identifier."""
        name = re.sub(r'[^A-Za-z0-9_\\-]', '_', name) # Use re.sub
        return name[:100]

    async def _create_legend_group(
        self,
        msp: Any, # Modelspace
        block_definition_container: Any, # e.g., doc.blocks
        group_config: LegendGroupConfig,
        legend_definition: LegendDefinitionConfig, # For layout
        group_layer_name: str,
        current_x: float,
        current_y: float,
        legend_tag_prefix: str,
        app_id: Optional[str]
    ) -> float:
        layout = legend_definition.layout
        dummy_source = GeoJSONSourceConfig(path="internal_legend_layer.geojson", type=DataSourceType.GEOJSON)

        self.logger.debug(f"Creating group: {group_config.name} on layer {group_layer_name}")

        group_title_style_props = self.style_service.get_text_style_properties(
            style_reference=group_config.group_text_style_inline if group_config.group_text_style_inline else group_config.group_text_style_preset_name,
            layer_config_fallback=None
        )
        if not group_title_style_props or (not group_title_style_props.font_name_or_style_preset and not group_config.group_text_style_preset_name and not group_config.group_text_style_inline):
            self.logger.warning(f"No text style found for group title '{group_config.name}' in legend '{legend_definition.id}'. Using defaults.")
            group_title_style_props = TextStylePropertiesConfig()

        temp_layer_cfg_group_title = LayerConfig(name=group_layer_name, source=dummy_source)
        layer_display_properties_group_title = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_group_title)

        self.logger.debug(f"LSC_Debug _create_legend_group: layer_props type: {type(layer_display_properties_group_title)}, text_props type: {type(group_title_style_props)}")
        group_title_layer_style = LayerStyleConfig(
            layer_props=LayerDisplayPropertiesConfig(
                color=layer_display_properties_group_title.color,
                linetype=layer_display_properties_group_title.linetype,
                lineweight=layer_display_properties_group_title.lineweight,
                transparency=layer_display_properties_group_title.transparency,
                plot=layer_display_properties_group_title.plot
            ),
            text_style=group_title_style_props
        )

        mtext_grp_title_model = DxfMText(
            text_content=group_config.name,
            insertion_point=Coordinate(x=current_x, y=current_y, z=0.0),
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
            msp, block_definition_container, mtext_grp_title_model, group_title_layer_style
        )
        actual_height_grp_title = 0.0
        if created_grp_title_entity:
            try:
                extents_data_grp_title = bbox.extents([created_grp_title_entity], fast=True)
                if extents_data_grp_title.has_data: actual_height_grp_title = extents_data_grp_title.size.y
            except Exception as e_bbox_grp_title: self.logger.warning(f"Could not calculate bbox for group title MTEXT: {e_bbox_grp_title}")

        current_y -= actual_height_grp_title + layout.title_spacing_to_content

        for idx, item_conf in enumerate(group_config.items):
            item_tag_suffix = self._sanitize_for_tag(f"group_{group_config.name}_item_{item_conf.label}_{idx}")
            current_y = await self._create_legend_item(
                msp, block_definition_container,
                item_config=item_conf,
                legend_definition=legend_definition,
                item_layer_name=group_layer_name,
                current_x=current_x,
                current_y=current_y,
                legend_tag_prefix=legend_tag_prefix,
                item_tag_suffix=item_tag_suffix,
                app_id=app_id
            )
        return current_y

    async def _create_legend_item(
        self,
        msp: Any, # Corrected: This is the Modelspace, was 'doc'
        block_definition_container: Any, # Corrected: This is the e.g. doc.blocks, was 'msp'
        item_config: LegendItemConfig,
        legend_definition: LegendDefinitionConfig,
        item_layer_name: str, # Group layer name
        current_x: float,
        current_y: float,
        legend_tag_prefix: str,
        item_tag_suffix: str,
        app_id: Optional[str]
    ) -> float:
        layout = legend_definition.layout
        dummy_source = GeoJSONSourceConfig(path="internal_legend_layer.geojson", type=DataSourceType.GEOJSON)

        self.logger.debug(f"Factory: Creating item: {item_config.label} on layer {item_layer_name}")

        item_swatch_style_config = item_config.item_specific_style
        if item_swatch_style_config is None: # Ensure it's not None, provide default if so
            item_swatch_style_config = LegendItemStyleConfig()

        swatch_legend_item_id_tag = f"{legend_tag_prefix}_swatch_{item_tag_suffix}"

        swatch_object_style = self.style_service.get_resolved_style_object(
            preset_name=item_config.style_preset_source, # In schema this is style_preset_name
            inline_definition=item_config.style_inline_override, # In schema this is style_inline_definition
            context_name=f"legend item {item_config.label} swatch"
        )
        if swatch_object_style is None:
            self.logger.warning(f"Could not resolve swatch style for item '{item_config.label}'. Using default StyleObjectConfig.")
            swatch_object_style = StyleObjectConfig()

        # Define the LayerStyleConfig for the swatch entities ONCE, based on the resolved swatch_object_style.
        self.logger.debug(f"LSC_Debug _create_legend_item (defining swatch_dxf_layer_style): swatch_object_style.layer_props type: {type(swatch_object_style.layer_props)}, swatch_object_style.hatch_props type: {type(swatch_object_style.hatch_props)}")
        swatch_dxf_layer_style = LayerStyleConfig(
            layer_props=swatch_object_style.layer_props, # This should be LayerDisplayPropertiesConfig or None
            hatch_props=swatch_object_style.hatch_props  # This should be HatchPropertiesConfig or None
        )

        # Ensure layer_props exists for border color fallback if needed
        if swatch_dxf_layer_style.layer_props is None:
            swatch_dxf_layer_style.layer_props = LayerDisplayPropertiesConfig()

        # Fallback for border color if not set by resolved style
        if swatch_dxf_layer_style.layer_props.color is None:
            self.logger.debug(f"Swatch for '{item_config.label}' has no color in layer_props, applying default black border color.")
            swatch_dxf_layer_style.layer_props.color = ColorModel(rgb=(0,0,0)) # Default Black border


        # Define swatch bounds
        x1, y1_swatch_top = current_x, current_y
        x2, y2_swatch_bottom = x1 + layout.swatch_width, y1_swatch_top - layout.swatch_height

        swatch_domain_models: List[AnyDxfEntity] = []
        # Calls to swatch methods are now self.
        if item_swatch_style_config.swatch_type == 'area':
            # Pass swatch_object_style for _create_swatch_area to use for hatch properties etc.
            # item_config is also passed for block symbol details if swatch_type implied a block.
            hatch_model_list, poly_model_list = await self._create_swatch_area( # Modified to return two lists
                item_config=item_config,
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style, # Pass the resolved style for hatch
                item_style_cfg=item_swatch_style_config,
                app_id=app_id,
                specific_legend_item_tag=swatch_legend_item_id_tag
            )
            swatch_domain_models.extend(poly_model_list)
            swatch_domain_models.extend(hatch_model_list)
        elif item_swatch_style_config.swatch_type == 'line':
            swatch_domain_models = await self._create_swatch_line(
                item_config=item_config,
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id,
                specific_legend_item_tag=swatch_legend_item_id_tag
            )
        elif item_swatch_style_config.swatch_type == 'diagonal_line':
            swatch_domain_models = await self._create_swatch_diagonal_line(
                item_config=item_config,
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id,
                specific_legend_item_tag=swatch_legend_item_id_tag
            )
        elif item_swatch_style_config.swatch_type == 'empty':
            swatch_domain_models = await self._create_swatch_empty(
                item_config=item_config,
                bounds=(x1, y1_swatch_top, x2, y2_swatch_bottom),
                layer_name=item_layer_name,
                style_object_config=swatch_object_style,
                item_style_cfg=item_swatch_style_config,
                app_id=app_id,
                specific_legend_item_tag=swatch_legend_item_id_tag
            )
        else:
            self.logger.error(f"Unknown legend item type: {item_swatch_style_config.swatch_type} for item '{item_config.label}'")
            return current_y - layout.swatch_height - layout.item_spacing

        created_swatch_ezdxf_entities = []
        for domain_model in swatch_domain_models:
            # Removed all the complex 'effective_layer_style' logic from inside this loop.
            # Removed 'effective_layer_style.name = ...'
            # Removed the LSC_Debug log for 'effective_layer_style init'
            # The LSC_Debug log for 'swatch_dxf_layer_style' (previously using 'effective_style_object_config')
            # is now correctly placed before this loop and uses 'swatch_object_style'.

            ezdxf_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
                msp, block_definition_container, domain_model, swatch_dxf_layer_style # Corrected: msp first, then block_definition_container
            )
            if ezdxf_entity:
                created_swatch_ezdxf_entities.append(ezdxf_entity)

        # Bounding box calculation for swatch
        item_swatch_bbox_min_y = y2_swatch_bottom
        item_swatch_bbox_max_y = y1_swatch_top

        item_center_y = (item_swatch_bbox_min_y + item_swatch_bbox_max_y) / 2
        text_x = x2 + layout.swatch_to_text_spacing # Corrected attribute
        text_entities = []

        item_text_style_props = self.style_service.get_text_style_properties(
            style_reference=item_config.item_text_style_inline if item_config.item_text_style_inline else item_config.item_text_style_preset_name,
        )
        if not item_text_style_props or (not item_text_style_props.font_name_or_style_preset and not item_config.item_text_style_preset_name and not item_config.item_text_style_inline):
            self.logger.warning(f"No text style found for legend item '{item_config.label}'. Using defaults.")
            item_text_style_props = TextStylePropertiesConfig()

        temp_layer_cfg_item_text = LayerConfig(name=item_layer_name, source=dummy_source)
        layer_display_properties_item_text = self.style_service.get_layer_display_properties(layer_config=temp_layer_cfg_item_text)

        self.logger.debug(f"LSC_Debug _create_legend_item (item_text_dxf_layer_style): layer_props obj type: {type(layer_display_properties_item_text)}, text_props obj type: {type(item_text_style_props)}")
        item_text_dxf_layer_style = LayerStyleConfig(
            layer_props=layer_display_properties_item_text,
            text_style=item_text_style_props
        )

        mtext_item_name_model = DxfMText(
            text_content=item_config.label,
            insertion_point=Coordinate(x=text_x, y=item_center_y, z=0.0),
            layer=item_layer_name,
            style=item_text_style_props.font_name_or_style_preset or "Standard",
            char_height=item_text_style_props.height or 1.0,
            rotation=item_text_style_props.rotation_degrees or 0.0,
            attachment_point=item_text_style_props.attachment_point.upper() if item_text_style_props.attachment_point else 'MIDDLE_LEFT',
            width=layout.max_text_width - layout.swatch_width - layout.swatch_to_text_spacing, # Corrected attribute
            line_spacing_factor=item_text_style_props.paragraph_props.line_spacing_factor if item_text_style_props.paragraph_props else None,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, f"{legend_tag_prefix}_text_name_{item_tag_suffix}")] if app_id else None
        )
        name_entity = await self.entity_converter_service.add_dxf_entity_to_modelspace(
            msp, block_definition_container, mtext_item_name_model, item_text_dxf_layer_style # Corrected: msp first, then block_definition_container
        )
        if name_entity: text_entities.append(name_entity)

        # Placeholder for vertical alignment if self.dxf_writer is not available
        # This section also needs review.
        # if text_entities:
        #     all_text_bbox = await self.dxf_writer.get_entities_bbox(text_entities) # KNOWN ISSUE
        #     if all_text_bbox:
        #         text_center_y = (all_text_bbox.extmin.y + all_text_bbox.extmax.y) / 2
        #         vertical_adjustment = item_center_y - text_center_y
        #         await self.dxf_writer.translate_entities(text_entities, 0, vertical_adjustment, 0) # KNOWN ISSUE
        #         # all_text_bbox = await self.dxf_writer.get_entities_bbox(text_entities) # Update bbox after translate
        #     else:
        #         all_text_bbox = None
        # else:
        #     all_text_bbox = None

        # Fallback height calculation if bbox logic is deferred
        combined_bbox_min_y = item_swatch_bbox_min_y
        combined_bbox_max_y = item_swatch_bbox_max_y

        # Assuming MTEXT height is roughly char_height if bbox fails
        # This is a rough approximation.
        text_height_approx = item_text_style_props.height or layout.swatch_height # Fallback to swatch_height

        # Simulate text bbox relative to item_center_y for overall height calc
        # This avoids errors but is not accurate.
        sim_text_bbox_min_y = item_center_y - (text_height_approx / 2)
        sim_text_bbox_max_y = item_center_y + (text_height_approx / 2)

        combined_bbox_min_y = min(combined_bbox_min_y, sim_text_bbox_min_y)
        combined_bbox_max_y = max(combined_bbox_max_y, sim_text_bbox_max_y)

        total_item_height = combined_bbox_max_y - combined_bbox_min_y
        if total_item_height <= 0:
            total_item_height = layout.swatch_height

        current_y -= total_item_height + layout.item_spacing
        return current_y

    async def _create_swatch_area(
        self,
        item_config: LegendItemConfig, # For block_symbol_name etc.
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig, # For swatch_type and other specific swatch styles
        app_id: Optional[str],
        specific_legend_item_tag: str
    ) -> Tuple[List[AnyDxfEntity], List[AnyDxfEntity]]:
        x1, y1, x2, y2 = bounds
        domain_entities: List[AnyDxfEntity] = []

        rect_points_coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        # Ensure Coordinate objects are used as per DxfLWPolyline model
        rect_coords = [Coordinate(x=pt[0], y=pt[1]) for pt in rect_points_coords]

        border_lwpolyline_model = DxfLWPolyline(
            points=rect_coords + [Coordinate(x=x1, y=y1)], # Ensure closing point is also a Coordinate
            is_closed=True,
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_border")] if app_id else None
        )
        domain_entities.append(border_lwpolyline_model)

        if item_style_cfg.swatch_type == 'area' and style_object_config.hatch_props:
            dxf_hatch_path = DxfHatchPath(
                vertices=rect_coords, # Use the List[Coordinate]
                is_closed=True
            )

            current_hatch_props_config = style_object_config.hatch_props

            hatch_model = DxfHatch(
                paths=[dxf_hatch_path],
                hatch_props=current_hatch_props_config,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_hatch")] if app_id else None
            )
            if current_hatch_props_config and current_hatch_props_config.color:
                if current_hatch_props_config.color.is_aci_color():
                    hatch_model.color_256 = current_hatch_props_config.color.aci_index
                else:
                    hatch_model.true_color = current_hatch_props_config.color.get_rgb_tuple()
            domain_entities.append(hatch_model)

        # MODIFIED: Use item_config for block symbol properties
        if item_config.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_config.block_symbol_name,
                insertion_point=((x1 + x2) / 2, (y1 + y2) / 2, 0), # Assuming Coordinate is not needed here by DxfInsert model
                x_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                y_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                z_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                rotation=item_config.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        return domain_entities, []

    async def _create_swatch_line(
        self,
        item_config: LegendItemConfig,
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig,
        app_id: Optional[str],
        specific_legend_item_tag: str
    ) -> List[AnyDxfEntity]:
        x1, y1, x2, y2 = bounds
        middle_y = (y1 + y2) / 2
        domain_entities: List[AnyDxfEntity] = []

        line_points_tuples = [(x1, middle_y), (x2, middle_y)]
        line_coords = [Coordinate(x=pt[0], y=pt[1]) for pt in line_points_tuples]

        line_model = DxfLWPolyline( # Assuming a simple line swatch can be an open LWPolyline
            points=line_coords,
            is_closed=False,
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag)] if app_id else None
        )
        domain_entities.append(line_model)

        # MODIFIED: Use item_config for block symbol properties
        if item_config.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_config.block_symbol_name,
                insertion_point=((x1 + x2) / 2, middle_y, 0),
                x_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                y_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                z_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                rotation=item_config.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        return domain_entities

    async def _create_swatch_diagonal_line(
        self,
        item_config: LegendItemConfig,
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig,
        app_id: Optional[str],
        specific_legend_item_tag: str
    ) -> List[AnyDxfEntity]:
        x1, y1, x2, y2 = bounds
        domain_entities: List[AnyDxfEntity] = []

        border_points_tuples = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1,y1)] # Closed
        border_coords = [Coordinate(x=pt[0], y=pt[1]) for pt in border_points_tuples]
        border_model = DxfLWPolyline(
            points=border_coords,
            is_closed=True, # Explicitly true, though last point == first implies it for LWPolyline points
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_border")] if app_id else None
        )
        domain_entities.append(border_model)

        diag_line_model = DxfLine( # DxfLine uses Coordinate for start/end directly
            start=Coordinate(x=x1, y=y1, z=0),
            end=Coordinate(x=x2, y=y2, z=0),
            layer=layer_name,
            xdata_app_id=app_id if app_id else None,
            xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_diag")] if app_id else None
        )
        domain_entities.append(diag_line_model)

        # MODIFIED: Use item_config for block symbol properties
        if item_config.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_config.block_symbol_name,
                insertion_point=((x1 + x2) / 2, (y1 + y2) / 2, 0),
                x_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                y_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                z_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                rotation=item_config.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        return domain_entities

    async def _create_swatch_empty(
        self,
        item_config: LegendItemConfig,
        bounds: Tuple[float, float, float, float],
        layer_name: str,
        style_object_config: StyleObjectConfig,
        item_style_cfg: LegendItemStyleConfig, # Kept for swatch_type, though not directly used in this method's logic beyond if-conditions
        app_id: Optional[str],
        specific_legend_item_tag: str
    ) -> List[AnyDxfEntity]:
        x1, y1, x2, y2 = bounds
        domain_entities: List[AnyDxfEntity] = []

        # MODIFIED: Use item_config for block symbol properties
        if item_config.block_symbol_name:
            insert_model = DxfInsert(
                block_name=item_config.block_symbol_name,
                insertion_point=((x1 + x2) / 2, (y1 + y2) / 2, 0),
                x_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                y_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                z_scale=item_config.block_symbol_scale if item_config.block_symbol_scale is not None else 1.0,
                rotation=item_config.block_symbol_rotation or 0.0,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_block")] if app_id else None
            )
            domain_entities.append(insert_model)
        # This elif condition is from the original code for drawing a border if no block symbol
        # AND if there are any layer properties defined for the swatch (color, lineweight, linetype)
        elif not item_config.block_symbol_name and style_object_config and style_object_config.layer_props and (
            style_object_config.layer_props.color or
            (style_object_config.layer_props.lineweight is not None and style_object_config.layer_props.lineweight >=0) or # Corrected to >=0 as per typical lineweight values
            style_object_config.layer_props.linetype
        ):
            border_points_tuples = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1,y1)]
            border_coords = [Coordinate(x=pt[0], y=pt[1]) for pt in border_points_tuples]
            border_model = DxfLWPolyline(
                points=border_coords,
                is_closed=True,
                layer=layer_name,
                xdata_app_id=app_id if app_id else None,
                xdata_tags=[(1000, "legend_item"), (1000, specific_legend_item_tag + "_border")] if app_id else None
            )
            domain_entities.append(border_model)
        return domain_entities
