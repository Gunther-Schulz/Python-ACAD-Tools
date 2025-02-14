"""Module for creating legends in DXF files."""

import math
import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from ezdxf.math import Vec3
from ezdxf import colors
from ezdxf.math import BoundingBox
from ezdxf.lldxf.const import MTEXT_TOP_LEFT
from ezdxf import bbox
import os
from src.core.utils import log_warning, log_error, log_info, log_debug
from src.dxf_exporter.style_manager import StyleManager
from src.dxf_exporter.utils import (
    convert_transparency,
    get_color_code,
    attach_custom_data,
    is_created_by_script,
    add_mtext,
    remove_entities_by_layer,
    ensure_layer_exists,
    SCRIPT_IDENTIFIER,
    apply_style_to_entity,
    sanitize_layer_name,
    get_available_blocks,
    add_block_reference,
    set_hatch_transparency,
    update_layer_properties,
    create_hatch
)
from ezdxf.lldxf import const
from ..dxf_exporter.utils.style_defaults import DEFAULT_TEXT_STYLE

class LegendCreator:
    def __init__(self, doc, msp, project_loader, loaded_styles):
        self.doc = doc
        self.msp = msp
        self.project_loader = project_loader
        self.loaded_styles = loaded_styles
        self.script_identifier = SCRIPT_IDENTIFIER
        self.legends_config = project_loader.project_settings.get('legends', [])
        if not self.legends_config and 'legend' in project_loader.project_settings:
            self.legends_config = [project_loader.project_settings['legend']]
        
        self.layer_name_cache = {}
        self.name_to_aci = project_loader.name_to_aci
        self.style_manager = StyleManager(project_loader)
        self.default_text_style = DEFAULT_TEXT_STYLE.copy()
        
        self.initialize_default_settings()

    def initialize_default_settings(self):
        self.position = {'x': 0, 'y': 0}
        self.group_spacing = 20
        self.item_spacing = 2
        self.item_width = 30
        self.item_height = 15
        self.text_offset = 5
        self.subtitle_spacing = 6
        self.group_title_spacing = 8
        self.group_subtitle_spacing = 4
        self.max_width = 200
        self.title_spacing = 10
        self.total_item_width = self.item_width + self.text_offset + self.max_width

    def create_legend(self):
        for legend_config in self.legends_config:
            self.apply_legend_config(legend_config)
            self.create_single_legend(legend_config)

    def apply_legend_config(self, legend_config):
        self.position = legend_config.get('position', {'x': 0, 'y': 0})
        self.current_y = self.position['y']
        self.group_spacing = legend_config.get('group_spacing', 20)
        self.item_spacing = legend_config.get('item_spacing', 2)
        self.item_width = legend_config.get('item_width', 30)
        self.item_height = legend_config.get('item_height', 15)
        self.text_offset = legend_config.get('text_offset', 5)
        self.subtitle_spacing = legend_config.get('subtitle_spacing', 6)
        self.group_title_spacing = legend_config.get('group_title_spacing', 8)
        self.group_subtitle_spacing = legend_config.get('group_subtitle_spacing', 4)
        self.max_width = legend_config.get('max_width', 200)
        self.title_spacing = legend_config.get('title_spacing', 10)
        self.total_item_width = self.item_width + self.text_offset + self.max_width
        
        self.subtitle_text_style = self.style_manager.get_style(legend_config.get('subtitleTextStyle', {}))
        self.group_text_style = self.style_manager.get_style(legend_config.get('groupTextStyle', {}))
        self.item_text_style = self.style_manager.get_style(legend_config.get('itemTextStyle', {}))
        self.title_text_style = self.style_manager.get_style(legend_config.get('titleTextStyle', {}))
        self.title_subtitle_style = self.style_manager.get_style(legend_config.get('titleSubtitleStyle', {}))

    def create_single_legend(self, legend_config):
        legend_id = legend_config.get('id', 'default')
        self.clean_legend_layers(legend_id)
        self.current_y = self.position['y']
        self.create_legend_title(legend_config)
        for group in legend_config.get('groups', []):
            self.create_group(group, legend_id)

    def clean_legend_layers(self, legend_id):
        # Remove title layer for this legend
        remove_entities_by_layer(self.msp, f"Legend_{legend_id}_Title", self.script_identifier)
        
        # Find the current legend config
        current_legend = next((legend for legend in self.legends_config if legend.get('id') == legend_id), None)
        if current_legend:
            # Get groups from the current legend
            for group in current_legend.get('groups', []):
                group_name = group.get('name', '')
                layer_name = self.get_sanitized_layer_name(f"Legend_{legend_id}_{group_name}")
                remove_entities_by_layer(self.msp, layer_name, self.script_identifier)

    def create_legend_title(self, legend_config):
        title = legend_config.get('title', '')
        subtitle = legend_config.get('subtitle', '')
        legend_id = legend_config.get('id', 'default')
        layer_name = self.get_sanitized_layer_name(f"Legend_{legend_id}_Title")
        
        # First ensure layer exists
        ensure_layer_exists(self.doc, layer_name)
        
        # Then update layer properties if needed
        layer = self.doc.layers.get(layer_name)
        if layer:
            update_layer_properties(layer, {}, self.name_to_aci)

        if title:
            title_result = self.add_mtext(self.position['x'], self.current_y, title, layer_name, self.title_text_style, self.max_width)
            if title_result is not None and title_result[0] is not None:
                title_entity, actual_title_height = title_result
                self.current_y -= actual_title_height + self.title_spacing
            else:
                log_warning(f"Failed to create title MTEXT for legend")
                self.current_y -= self.title_text_style.get('height', 8) + self.title_spacing

        if subtitle:
            subtitle_result = self.add_mtext(self.position['x'], self.current_y, subtitle, layer_name, self.title_subtitle_style, self.max_width)
            if subtitle_result is not None and subtitle_result[0] is not None:
                subtitle_entity, actual_subtitle_height = subtitle_result
                self.current_y -= actual_subtitle_height + self.subtitle_spacing
            else:
                log_warning(f"Failed to create subtitle MTEXT for legend")
                self.current_y -= self.title_subtitle_style.get('height', 4) + self.subtitle_spacing

        self.current_y -= self.group_spacing

    def create_group(self, group, legend_id):
        group_name = group.get('name', '')
        layer_name = self.get_sanitized_layer_name(f"Legend_{legend_id}_{group_name}")
        
        title_result = self.add_mtext(self.position['x'], self.current_y, group_name, layer_name, self.group_text_style, self.max_width)
        if title_result is not None and title_result[0] is not None:
            title_entity, actual_title_height = title_result
            self.current_y -= actual_title_height + self.group_title_spacing
        else:
            log_warning(f"Failed to create title MTEXT for group '{group_name}'")
            self.current_y -= self.group_text_style.get('height', 5) + self.group_title_spacing

        subtitle = group.get('subtitle', '')
        if subtitle:
            subtitle_result = self.add_mtext(self.position['x'], self.current_y, subtitle, layer_name, self.subtitle_text_style, self.max_width)
            if subtitle_result is not None and subtitle_result[0] is not None:
                subtitle_entity, actual_subtitle_height = subtitle_result
                self.current_y -= actual_subtitle_height + self.group_subtitle_spacing
            else:
                log_warning(f"Failed to create subtitle MTEXT for group '{group_name}'")
                self.current_y -= self.subtitle_text_style.get('height', 4) + self.group_subtitle_spacing

        items = group.get('items', [])
        for item in items:
            self.create_item(item, layer_name)
        
        self.current_y -= self.group_spacing

    def create_item(self, item, layer_name):
        item_name = item.get('name', '')
        item_subtitle = item.get('subtitle', '')
        item_type = item.get('type', 'empty')
        
        # Modified style handling
        style = item.get('style', {})
        if isinstance(style, dict) and 'preset' in style:
            preset_style, _ = self.style_manager.get_style(style['preset'])
            # Deep merge the preset with any overrides
            style = self.style_manager.deep_merge(preset_style or {}, {k: v for k, v in style.items() if k != 'preset'})
        else:
            style = self.style_manager.get_style(style)
        
        # Get the processed styles
        hatch_style = self.style_manager.get_style(style.get('hatch', {}))
        layer_style = self.style_manager.get_style(style.get('layer', {}))
        rectangle_style = self.style_manager.get_style(item.get('rectangleStyle', {}))
        
        block_symbol = item.get('blockSymbol')
        block_symbol_scale = item.get('blockSymbolScale', 1.0)
        create_hatch = item.get('applyHatch', False)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        log_debug(f"Creating item: {item_name}, type: {item_type}, symbol: {block_symbol}")
        
        sanitized_layer_name = self.get_sanitized_layer_name(layer_name)

        if item_type == 'area':
            item_entities = self.create_area_item(x1, y1, x2, y2, sanitized_layer_name, hatch_style, layer_style, rectangle_style, create_hatch, block_symbol, block_symbol_scale)
        elif item_type == 'line':
            item_entities = self.create_line_item(x1, y1, x2, y2, sanitized_layer_name, layer_style, rectangle_style, block_symbol, block_symbol_scale)
        elif item_type == 'diagonal_line':
            item_entities = self.create_diagonal_line_item(x1, y1, x2, y2, sanitized_layer_name, layer_style, rectangle_style, block_symbol, block_symbol_scale)
        elif item_type == 'empty':
            item_entities = self.create_empty_item(x1, y1, x2, y2, sanitized_layer_name, rectangle_style, block_symbol, block_symbol_scale)
        else:
            raise ValueError(f"Unknown item type: {item_type}")

        item_bbox = bbox.BoundingBox()
        item_bbox.extend([Vec3(x1, y2, 0), Vec3(x2, y1, 0)])

        for entity in item_entities:
            if entity:
                entity_bbox = self.get_entity_bbox(entity)
                item_bbox.extend(entity_bbox)

        item_center_y = (item_bbox.extmin.y + item_bbox.extmax.y) / 2

        text_x = x2 + self.text_offset
        
        # Create name text first
        text_result = add_mtext(
            self.msp,
            item_name,
            text_x,
            item_center_y,
            sanitized_layer_name,
            self.item_text_style.get('text_style', 'Standard'),
            self.item_text_style,
            self.name_to_aci,
            self.max_width - self.item_width - self.text_offset
        )

        if text_result is None or text_result[0] is None:
            log_warning(f"Failed to create text entity for item '{item_name}'")
            self.current_y -= self.item_height + self.item_spacing
            return

        text_entity, actual_text_height = text_result
        entities = [text_entity]

        # Add subtitle if present
        if item_subtitle:
            # Get the actual bounding box of the main text to account for multiple lines
            main_text_bbox = bbox.extents([text_entity])
            subtitle_y = main_text_bbox.extmin.y - self.group_subtitle_spacing  # Position below the last line
            
            subtitle_result = add_mtext(
                self.msp,
                item_subtitle,
                text_x,
                subtitle_y,
                sanitized_layer_name,
                self.subtitle_text_style.get('text_style', 'Standard'),
                self.subtitle_text_style,
                self.name_to_aci,
                self.max_width - self.item_width - self.text_offset
            )
            
            if subtitle_result is not None and subtitle_result[0] is not None:
                subtitle_entity, subtitle_height = subtitle_result
                entities.append(subtitle_entity)

        # Calculate combined bounding box
        text_bbox = bbox.BoundingBox()
        for entity in entities:
            text_bbox.extend(bbox.extents([entity]))

        text_center_y = (text_bbox.extmin.y + text_bbox.extmax.y) / 2
        vertical_adjustment = item_center_y - text_center_y
        
        # Adjust position of all text entities
        for entity in entities:
            entity.translate(0, vertical_adjustment, 0)

        text_bbox = bbox.BoundingBox()
        for entity in entities:
            text_bbox.extend(bbox.extents([entity]))
        
        combined_bbox = item_bbox.union(text_bbox)

        vertical_offset = self.current_y - combined_bbox.extmax.y
        for entity in item_entities + entities:
            if entity:
                entity.translate(0, vertical_offset, 0)

        total_height = combined_bbox.size.y

        self.current_y -= total_height + self.item_spacing

        # Attach custom data to all entities
        for entity in item_entities + entities:
            if entity:
                attach_custom_data(entity, self.script_identifier)

    def create_area_item(self, x1, y1, x2, y2, layer_name, hatch_style, layer_style, rectangle_style, create_hatch, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        
        if isinstance(rectangle_style, dict) and 'layer' in rectangle_style:
            self.style_manager.apply_style(rectangle, rectangle_style['layer'])
        else:
            self.style_manager.apply_style(rectangle, rectangle_style)
        
        self.style_manager.attach_custom_data(rectangle)
        entities.append(rectangle)

        if create_hatch:
            hatch_paths = [[(x1, y1), (x2, y1), (x2, y2), (x1, y2)]]
            
            # Create a layer_info-like structure for the style manager
            legend_layer_info = {
                'style': {'hatch': hatch_style}  # Match the structure expected by style_manager
            }
            
            # Use the same style processing as regular geometry
            hatch_config = self.style_manager.get_hatch_config(legend_layer_info)
            
            hatch = create_hatch(self.msp, hatch_paths, hatch_config, self.project_loader)
            hatch.dxf.layer = layer_name
            
            if 'color' in hatch_style:
                color = get_color_code(hatch_style['color'], self.name_to_aci)
                if isinstance(color, tuple):
                    hatch.rgb = color
                else:
                    hatch.dxf.color = color
            
            if 'transparency' in hatch_style:
                transparency = convert_transparency(hatch_style['transparency'])
                if transparency is not None:
                    set_hatch_transparency(hatch, transparency)
            
            self.style_manager.attach_custom_data(hatch)
            entities.append(hatch)

        if block_symbol:
            symbol_entity = add_block_reference(
                self.msp,
                block_symbol,
                ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name,
                scale=block_symbol_scale
            )
            if symbol_entity:
                entities.append(symbol_entity)

        return entities

    def create_line_item(self, x1, y1, x2, y2, layer_name, layer_style, rectangle_style, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        middle_y = (y1 + y2) / 2
        points = [(x1, middle_y), (x2, middle_y)]
        line = self.msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
        self.style_manager.apply_style(line, layer_style)
        self.style_manager.attach_custom_data(line)
        entities.append(line)

        if block_symbol:
            symbol_entity = add_block_reference(
                self.msp,
                block_symbol,
                ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name,
                scale=block_symbol_scale
            )
            if symbol_entity:
                entities.append(symbol_entity)

        return entities

    def create_diagonal_line_item(self, x1, y1, x2, y2, layer_name, layer_style, rectangle_style, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        self.style_manager.apply_style(rectangle, rectangle_style)
        self.style_manager.attach_custom_data(rectangle)
        entities.append(rectangle)

        line = self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'layer': layer_name})
        self.style_manager.apply_style(line, layer_style)
        self.style_manager.attach_custom_data(line)
        entities.append(line)

        if block_symbol:
            symbol_entity = add_block_reference(
                self.msp,
                block_symbol,
                ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name,
                scale=block_symbol_scale
            )
            if symbol_entity:
                entities.append(symbol_entity)

        return entities

    def create_empty_item(self, x1, y1, x2, y2, layer_name, rectangle_style, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        if block_symbol:
            symbol_entity = add_block_reference(
                self.msp,
                block_symbol,
                ((x1 + x2) / 2, (y1 + y2) / 2),
                layer_name,
                scale=block_symbol_scale
            )
            if symbol_entity:
                entities.append(symbol_entity)

        return entities

    def add_mtext(self, x, y, text, layer_name, text_style, max_width=None):
        try:
            style_name = text_style.get('font', self.default_text_style['font'])
            if style_name not in self.doc.styles:
                log_warning(f"Text style '{style_name}' was not loaded during initialization. Using '{self.default_text_style['font']}' instead.")
                style_name = self.default_text_style['font']

            # Create MText editor for paragraph formatting
            editor = ezdxf.tools.text.MTextEditor()
            
            # Handle paragraph properties
            if 'paragraph' in text_style:
                para_props = text_style['paragraph']
                alignment_map = {
                    'LEFT': const.MTEXT_LEFT,
                    'RIGHT': const.MTEXT_RIGHT,
                    'CENTER': const.MTEXT_CENTER,
                    'JUSTIFIED': const.MTEXT_JUSTIFIED,
                    'DISTRIBUTED': const.MTEXT_DISTRIBUTED
                }
                
                props = ezdxf.tools.text.ParagraphProperties(
                    indent=para_props.get('indent', 0),
                    left=para_props.get('leftMargin', 0),
                    right=para_props.get('rightMargin', 0),
                    align=alignment_map.get(para_props.get('align', 'LEFT').upper(), const.MTEXT_LEFT),
                    tab_stops=para_props.get('tabStops', tuple())
                )
                editor.paragraph(props)

            # Add text content
            for paragraph in text.split('\n'):
                editor.append(paragraph)
                editor.append('\\P')  # Add paragraph break

            # Build dxfattribs with camelCase properties
            dxfattribs = {
                'style': style_name,
                'layer': layer_name,
                'char_height': text_style.get('height', 2.5),
                'width': text_style.get('maxWidth', max_width) if max_width is not None else 0,
            }

            # Apply text style properties
            if 'color' in text_style:
                dxfattribs['color'] = get_color_code(text_style['color'], self.name_to_aci)
                
            if 'attachmentPoint' in text_style:
                attachment = text_style['attachmentPoint'].upper()
                dxfattribs['attachment_point'] = const.attachment_map.get(attachment, MTEXT_TOP_LEFT)
                
            if 'flowDirection' in text_style:
                flow_dir = text_style['flowDirection'].upper()
                dxfattribs['flow_direction'] = const.flow_direction_map.get(flow_dir, 
                                             const.MTEXT_LEFT_TO_RIGHT)
                
            if 'lineSpacingStyle' in text_style:
                spacing_style = text_style['lineSpacingStyle'].upper()
                dxfattribs['line_spacing_style'] = const.spacing_style_map.get(spacing_style, 
                                                  const.MTEXT_AT_LEAST)
                
            if 'lineSpacingFactor' in text_style:
                dxfattribs['line_spacing_factor'] = text_style['lineSpacingFactor']
                
            if 'bgFill' in text_style:
                dxfattribs['bg_fill'] = text_style['bgFill']
                
            if 'bgFillColor' in text_style:
                dxfattribs['bg_fill_color'] = get_color_code(text_style['bgFillColor'], self.name_to_aci)
                
            if 'bgFillScale' in text_style:
                dxfattribs['box_fill_scale'] = text_style['bgFillScale']
                
            if 'obliqueAngle' in text_style:
                dxfattribs['oblique_angle'] = text_style['obliqueAngle']

            # Create MTEXT entity
            mtext = self.msp.add_mtext(str(editor), dxfattribs=dxfattribs)
            mtext.set_location((x, y))
            
            # Apply additional text formatting
            if text_style:
                formatting = []
                if text_style.get('underline'):
                    formatting.append(('\\L', '\\l'))
                if text_style.get('overline'):
                    formatting.append(('\\O', '\\o'))
                if text_style.get('strikeThrough'):
                    formatting.append(('\\K', '\\k'))
                    
                # Apply all formatting
                text_content = mtext.text
                for start, end in formatting:
                    text_content = f"{start}{text_content}{end}"
                mtext.text = text_content
            
            bounding_box = bbox.extents([mtext])
            actual_height = bounding_box.size.y
            
            self.style_manager.attach_custom_data(mtext)
            return mtext, actual_height
            
        except Exception as e:
            log_error(f"Error creating MTEXT: {str(e)}")
            return None, 0

    def attach_custom_data(self, entity):
        if entity is not None:
            attach_custom_data(entity, self.script_identifier)
        else:
            log_warning("Attempted to attach custom data to a None entity")

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, self.script_identifier)

    def get_color_code(self, color):
        return get_color_code(color, self.name_to_aci)

    def get_entity_bbox(self, entity):
        if isinstance(entity, ezdxf.entities.Hatch):
            item_bbox = bbox.BoundingBox()
            for path in entity.paths:
                if hasattr(path, 'vertices'):
                    item_bbox.extend(path.vertices)
                elif hasattr(path, 'control_points'):
                    item_bbox.extend(path.control_points)
            return item_bbox
        else:
            return bbox.extents([entity])

    def get_sanitized_layer_name(self, name):
        if name not in self.layer_name_cache:
            self.layer_name_cache[name] = sanitize_layer_name(name)
        return self.layer_name_cache[name]

    def apply_style(self, entity, style):
        if isinstance(style, str):
            style, warning_generated = self.style_manager.get_style(style)
            if warning_generated:
                return
        
        if isinstance(style, dict):
            # Use our specialized function to apply the style
            apply_style_to_entity(entity, style, self.project_loader, self.loaded_styles)




























