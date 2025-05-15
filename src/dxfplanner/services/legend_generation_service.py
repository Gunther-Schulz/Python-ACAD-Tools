from typing import Any, Dict, List, Optional, Tuple
from logging import Logger
import re # Moved import re to top level

from ..config.schemas import (
    AppConfig, LegendDefinitionConfig, LegendLayoutConfig, LegendGroupConfig, LegendItemConfig,
    LegendItemStyleConfig, TextStylePropertiesConfig, StyleObjectConfig,
    LayerDisplayPropertiesConfig, HatchPropertiesConfig # Added more specific style configs
)
from ..domain.interfaces import ILegendGenerator, IDxfWriter, IStyleService # Added IStyleService
from ..core.exceptions import ConfigurationError # For missing style presets

# It's better to get SCRIPT_IDENTIFIER from config if it's globally defined
# For now, assume dxf_writer will handle its own script identifier for custom data

class LegendGenerationService(ILegendGenerator):
    """
    Service responsible for generating legends based on configuration
    and adding them to a DXF document.
    """
    def __init__(
        self,
        config: AppConfig,
        logger: Logger,
        dxf_writer: IDxfWriter,
        style_service: IStyleService, # Added style_service
    ):
        self.config = config
        self.logger = logger
        self.dxf_writer = dxf_writer
        self.style_service = style_service # Store style_service
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
            await self._generate_single_legend(doc, msp, legend_def_config, **kwargs)

        self.logger.info("Legend generation completed.")

    async def _generate_single_legend(
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

        # Clean existing legend entities - IDxfWriter needs a robust way to do this
        # e.g., by a unique legend_id tag in xdata or specific layer prefixing
        # For now, conceptual call:
        await self.dxf_writer.clear_legend_content(doc, msp, legend_id=legend_config.id) # Pass the base legend_id

        # Create Legend Title & Subtitle
        current_y = await self._create_legend_main_titles(
            doc, msp, legend_config, current_x, current_y, legend_tag_prefix
        )

        current_y -= layout.group_spacing

        for group_conf in legend_config.groups:
            group_layer_name = self._get_sanitized_layer_name(f"Legend_{legend_config.id}_{group_conf.name}")
            current_y = await self._create_legend_group(
                doc, msp, group_conf, legend_config, group_layer_name, current_x, current_y, legend_tag_prefix
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
        legend_tag_prefix: str # Added legend_tag_prefix
    ) -> float:
        layout = legend_config.layout
        title_layer_name = self._get_sanitized_layer_name(f"Legend_{legend_config.id}_Title")
        await self.dxf_writer.ensure_layer_exists_with_properties(doc, title_layer_name, None) # Ensure layer exists

        if legend_config.title:
            # MODIFIED: Use StyleService
            title_style = self.style_service.get_text_style_properties(
                style_reference=legend_config.overall_title_text_style_inline if legend_config.overall_title_text_style_inline else legend_config.overall_title_text_style_preset_name,
                # No specific layer_config_fallback here, relies on StyleService defaults if needed
            )
            if not title_style or (not title_style.font and not legend_config.overall_title_text_style_preset_name and not legend_config.overall_title_text_style_inline) : # Check if truly default/empty
                self.logger.warning(f"No title text style found for legend '{legend_config.id}'. Using defaults.")
                title_style = TextStylePropertiesConfig() # Default empty style

            _, actual_height = await self.dxf_writer.add_mtext_ez(
                doc, msp, legend_config.title, (current_x, current_y),
                title_layer_name, title_style, layout.max_text_width,
                legend_item_id=f"{legend_tag_prefix}_main_title" # Added legend_item_id
            )
            current_y -= actual_height + layout.title_spacing_to_content

        if legend_config.subtitle:
            # MODIFIED: Use StyleService
            subtitle_style = self.style_service.get_text_style_properties(
                style_reference=legend_config.overall_subtitle_text_style_inline if legend_config.overall_subtitle_text_style_inline else legend_config.overall_subtitle_text_style_preset_name
            )
            if not subtitle_style or (not subtitle_style.font and not legend_config.overall_subtitle_text_style_preset_name and not legend_config.overall_subtitle_text_style_inline):
                self.logger.warning(f"No subtitle text style found for legend '{legend_config.id}'. Using defaults.")
                subtitle_style = TextStylePropertiesConfig()

            _, actual_height = await self.dxf_writer.add_mtext_ez(
                doc, msp, legend_config.subtitle, (current_x, current_y),
                title_layer_name, subtitle_style, layout.max_text_width,
                legend_item_id=f"{legend_tag_prefix}_main_subtitle" # Added legend_item_id
            )
            current_y -= actual_height + layout.subtitle_spacing_after_title # Different spacing for main subtitle

        return current_y

    async def _create_legend_group(
        self, doc: Any, msp: Any,
        group_config: LegendGroupConfig,
        legend_definition: LegendDefinitionConfig, # To access global layout and style presets
        group_layer_name: str,
        current_x: float, current_y: float,
        legend_tag_prefix: str # Added legend_tag_prefix
    ) -> float:
        layout = legend_definition.layout
        await self.dxf_writer.ensure_layer_exists_with_properties(doc, group_layer_name, None)

        self.logger.debug(f"Creating group: {group_config.name} on layer {group_layer_name}")

        # MODIFIED: Use StyleService
        group_title_style = self.style_service.get_text_style_properties(
            style_reference=group_config.title_text_style_inline if group_config.title_text_style_inline else group_config.title_text_style_preset_name
        )
        if not group_title_style or (not group_title_style.font and not group_config.title_text_style_preset_name and not group_config.title_text_style_inline):
            self.logger.debug(f"No title style for group '{group_config.name}', using default.")
            group_title_style = TextStylePropertiesConfig()

        _, actual_height = await self.dxf_writer.add_mtext_ez(
            doc, msp, group_config.name, (current_x, current_y),
            group_layer_name, group_title_style, layout.max_text_width,
            legend_item_id=f"{legend_tag_prefix}_group_{self._get_sanitized_layer_name(group_config.name)}_title" # Added legend_item_id
        )
        current_y -= actual_height + layout.title_spacing_to_content

        if group_config.subtitle:
            # MODIFIED: Use StyleService
            group_subtitle_style = self.style_service.get_text_style_properties(
                style_reference=group_config.subtitle_text_style_inline if group_config.subtitle_text_style_inline else group_config.subtitle_text_style_preset_name
            )
            if not group_subtitle_style or (not group_subtitle_style.font and not group_config.subtitle_text_style_preset_name and not group_config.subtitle_text_style_inline):
                self.logger.debug(f"No subtitle style for group '{group_config.name}', using default.")
                group_subtitle_style = TextStylePropertiesConfig()

            _, actual_height = await self.dxf_writer.add_mtext_ez(
                doc, msp, group_config.subtitle, (current_x, current_y),
                group_layer_name, group_subtitle_style, layout.max_text_width,
                legend_item_id=f"{legend_tag_prefix}_group_{self._get_sanitized_layer_name(group_config.name)}_subtitle" # Added legend_item_id
            )
            current_y -= actual_height + layout.subtitle_spacing_after_title

        for item_conf in group_config.items:
            current_y = await self._create_legend_item(
                doc, msp, item_conf, legend_definition, group_layer_name, current_x, current_y,
                legend_tag_prefix # Pass down prefix
            )
        return current_y

    async def _create_legend_item(
        self, doc: Any, msp: Any,
        item_config: LegendItemConfig,
        legend_definition: LegendDefinitionConfig, # To access global layout and style presets
        item_layer_name: str, # This is actually the group layer name
        current_x: float, current_y: float,
        legend_tag_prefix: str # Added legend_tag_prefix
    ) -> float:
        layout = legend_definition.layout
        self.logger.debug(f"Creating item: {item_config.name} on layer {item_layer_name}")

        item_swatch_style_config = item_config.item_style
        item_tag_suffix = self._get_sanitized_layer_name(item_config.name) # Use sanitized name for tag

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

        swatch_entities = []
        swatch_legend_item_id = f"{legend_tag_prefix}_swatch_{item_tag_suffix}"
        if item_swatch_style_config.item_type == 'area':
            swatch_entities = await self._create_swatch_area(
                doc, msp, (x1, y1_swatch_top, x2, y2_swatch_bottom), item_layer_name,
                swatch_object_style, item_swatch_style_config, swatch_legend_item_id
            )
        elif item_swatch_style_config.item_type == 'line':
            swatch_entities = await self._create_swatch_line(
                doc, msp, (x1, y1_swatch_top, x2, y2_swatch_bottom), item_layer_name,
                swatch_object_style, item_swatch_style_config, swatch_legend_item_id
            )
        elif item_swatch_style_config.item_type == 'diagonal_line':
            swatch_entities = await self._create_swatch_diagonal_line(
                doc, msp, (x1, y1_swatch_top, x2, y2_swatch_bottom), item_layer_name,
                swatch_object_style, item_swatch_style_config, swatch_legend_item_id
            )
        elif item_swatch_style_config.item_type == 'empty':
            swatch_entities = await self._create_swatch_empty(
                doc, msp, (x1, y1_swatch_top, x2, y2_swatch_bottom), item_layer_name,
                swatch_object_style, item_swatch_style_config, swatch_legend_item_id
            )
        else:
            self.logger.error(f"Unknown legend item type: {item_swatch_style_config.item_type} for item '{item_config.name}'")
            return current_y - layout.item_swatch_height - layout.item_spacing # Skip item

        item_swatch_bbox = await self.dxf_writer.get_entities_bbox(swatch_entities)
        # Fallback if bbox is None (e.g. no entities or error)
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
        # MODIFIED: Use StyleService
        item_text_style = self.style_service.get_text_style_properties(
            style_reference=item_config.text_style_inline if item_config.text_style_inline else item_config.text_style_preset_name
        )
        if not item_text_style or (not item_text_style.font and not item_config.text_style_preset_name and not item_config.text_style_inline):
            self.logger.debug(f"No text style for item '{item_config.name}', using default.")
            item_text_style = TextStylePropertiesConfig()

        # Create item name text
        name_entity, name_actual_height = await self.dxf_writer.add_mtext_ez(
            doc, msp, item_config.name, (text_x, item_center_y), # Initial Y, will be adjusted
            item_layer_name, item_text_style,
            layout.max_text_width - layout.item_swatch_width - layout.text_offset_from_swatch,
            legend_item_id=f"{legend_tag_prefix}_item_{item_tag_suffix}_name" # Added legend_item_id
        )
        if name_entity: text_entities.append(name_entity)

        # Create item subtitle text if present
        if item_config.subtitle:
            # Resolve item subtitle style
            # MODIFIED: Use StyleService
            item_subtitle_style = self.style_service.get_text_style_properties(
                style_reference=item_config.subtitle_text_style_inline if item_config.subtitle_text_style_inline else item_config.subtitle_text_style_preset_name
            )
            if not item_subtitle_style or (not item_subtitle_style.font and not item_config.subtitle_text_style_preset_name and not item_config.subtitle_text_style_inline):
                self.logger.debug(f"No subtitle style for item '{item_config.name}', using default.")
                item_subtitle_style = TextStylePropertiesConfig()

            # Position subtitle below main text; get bbox of main text first
            main_text_bbox = await self.dxf_writer.get_entities_bbox([name_entity]) if name_entity else None
            subtitle_y_pos = (main_text_bbox.extmin.y - layout.subtitle_spacing_after_title) if main_text_bbox else (item_center_y - name_actual_height - layout.subtitle_spacing_after_title)

            subtitle_entity, _ = await self.dxf_writer.add_mtext_ez(
                doc, msp, item_config.subtitle, (text_x, subtitle_y_pos),
                item_layer_name, item_subtitle_style,
                layout.max_text_width - layout.item_swatch_width - layout.text_offset_from_swatch,
                legend_item_id=f"{legend_tag_prefix}_item_{item_tag_suffix}_subtitle" # Added legend_item_id
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
        self, doc:Any, msp: Any, bounds: Tuple[float, float, float, float],
        layer_name: str, style: StyleObjectConfig, item_style_cfg: LegendItemStyleConfig,
        legend_item_id_tag: str # Added specific tag parameter
    ) -> List[Any]:
        x1, y1, x2, y2 = bounds
        entities = []
        # DXF writer adds rectangle and applies style. StyleObjectConfig contains layer_props.
        rect = await self.dxf_writer.add_lwpolyline(
            doc, msp, [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], # Closed polyline
            layer_name, style.layer_props, is_closed=True, # Explicitly set is_closed
            legend_item_id=legend_item_id_tag
        )
        if rect: entities.append(rect)

        if item_style_cfg.apply_hatch_for_area and style.hatch_props:
            hatch_paths = [[(x1, y1), (x2, y1), (x2, y2), (x1, y2)]] # Path for hatch
            hatch = await self.dxf_writer.add_hatch(
                doc, msp, hatch_paths, layer_name, style.hatch_props,
                legend_item_id=legend_item_id_tag
            )
            if hatch: entities.append(hatch)

        if item_style_cfg.block_symbol_name:
            # Block reference layer_props come from the block definition, not typically overridden by style_props here.
            # Passing None for style_props for block_reference to avoid unintended color/linetype overrides.
            block_ref = await self.dxf_writer.add_block_reference(
                doc, msp, item_style_cfg.block_symbol_name, ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale, # scale x,y,z
                item_style_cfg.block_symbol_rotation or 0, None, # rotation, style_props
                legend_item_id=legend_item_id_tag
            )
            if block_ref: entities.append(block_ref)
        return entities

    async def _create_swatch_line(
        self, doc:Any, msp: Any, bounds: Tuple[float, float, float, float],
        layer_name: str, style: StyleObjectConfig, item_style_cfg: LegendItemStyleConfig,
        legend_item_id_tag: str # Added specific tag parameter
    ) -> List[Any]:
        x1, y1, x2, y2 = bounds
        middle_y = (y1 + y2) / 2
        entities = []
        line = await self.dxf_writer.add_lwpolyline( # Using lwpolyline for lines for consistency
            doc, msp, [(x1, middle_y), (x2, middle_y)],
            layer_name, style.layer_props, is_closed=False, # Not closed
            legend_item_id=legend_item_id_tag
        )
        if line: entities.append(line)

        if item_style_cfg.block_symbol_name:
            block_ref = await self.dxf_writer.add_block_reference(
                doc, msp, item_style_cfg.block_symbol_name, ((x1 + x2) / 2, middle_y),
                layer_name, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale,
                item_style_cfg.block_symbol_rotation or 0, None,
                legend_item_id=legend_item_id_tag
            )
            if block_ref: entities.append(block_ref)
        return entities

    async def _create_swatch_diagonal_line(
        self, doc:Any, msp: Any, bounds: Tuple[float, float, float, float],
        layer_name: str, style: StyleObjectConfig, item_style_cfg: LegendItemStyleConfig,
        legend_item_id_tag: str # Added specific tag parameter
    ) -> List[Any]:
        x1, y1, x2, y2 = bounds
        entities = []
        # Rectangle outline (usually styled with default/thin lines)
        # Use a default style for the bounding box of the swatch if needed
        rect_style_props = StyleObjectConfig(layer_props=LayerDisplayPropertiesConfig(color='BLACK', lineweight=0, linetype='Continuous'))
        # Example: Only use a specific color from item if explicitly meant for border, otherwise default
        # This logic can be refined based on how styles for swatch borders are defined
        # For now, let's use a simple black border.
        # if style.layer_props and style.layer_props.color != 'BYLAYER':
        # rect_style_props.layer_props.color = style.layer_props.color

        rect = await self.dxf_writer.add_lwpolyline(
            doc, msp, [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], # Closed polyline
            layer_name, rect_style_props.layer_props, is_closed=True,
            legend_item_id=f"{legend_item_id_tag}_border" # Tag border separately if needed
        )
        if rect: entities.append(rect)

        diag_line = await self.dxf_writer.add_line(
            doc, msp, (x1, y1), (x2, y2),
            layer_name, style.layer_props, # Actual line uses the item style
            legend_item_id=legend_item_id_tag
        )
        if diag_line: entities.append(diag_line)

        if item_style_cfg.block_symbol_name:
            block_ref = await self.dxf_writer.add_block_reference(
                doc, msp, item_style_cfg.block_symbol_name, ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale,
                item_style_cfg.block_symbol_rotation or 0, None,
                legend_item_id=legend_item_id_tag
            )
            if block_ref: entities.append(block_ref)
        return entities

    async def _create_swatch_empty(
        self, doc:Any, msp: Any, bounds: Tuple[float, float, float, float],
        layer_name: str, style: StyleObjectConfig, item_style_cfg: LegendItemStyleConfig,
        legend_item_id_tag: str # Added specific tag parameter
    ) -> List[Any]:
        x1, y1, x2, y2 = bounds
        entities = []
        if item_style_cfg.block_symbol_name:
            block_ref = await self.dxf_writer.add_block_reference(
                doc, msp, item_style_cfg.block_symbol_name, ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale, item_style_cfg.block_symbol_scale,
                item_style_cfg.block_symbol_rotation or 0, None,
                legend_item_id=legend_item_id_tag
            )
            if block_ref: entities.append(block_ref)
        # Optionally draw a border if style.layer_props is defined (e.g. for an empty box with border)
        elif style.layer_props and (style.layer_props.color or style.layer_props.lineweight > 0 or style.layer_props.linetype): # Check if any prop is set
             border = await self.dxf_writer.add_lwpolyline(
                doc, msp, [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], # Closed polyline
                layer_name, style.layer_props, is_closed=True,
                legend_item_id=legend_item_id_tag
            )
             if border: entities.append(border)
        return entities

    def _get_sanitized_layer_name(self, name: str) -> str:
        # Layer name sanitization should ideally be a core utility or part of dxf_writer
        # For now, simple pass-through; dxf_writer or ezdxf itself might handle it.
        # Max layer name length for DXF is typically 255. ezdxf might truncate or error.
        # Characters: A-Z, 0-9, $-_, cannot have spaces.
        name = re.sub(r'[^A-Za-z0-9_\-$]', '_', name)
        return name[:255] # Ensure max length
