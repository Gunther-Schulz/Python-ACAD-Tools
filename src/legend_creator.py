import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import (convert_transparency, get_color_code, attach_custom_data, 
                           is_created_by_script, add_mtext, remove_entities_by_layer, 
                           ensure_layer_exists, get_style, SCRIPT_IDENTIFIER,
                           apply_style_to_entity,
                           sanitize_layer_name, get_available_blocks, add_block_reference, set_hatch_transparency)
from ezdxf.math import Vec3
from ezdxf import colors
from src.utils import log_warning, log_error, log_info
from src import dfx_utils
from ezdxf.math import BoundingBox
from ezdxf.lldxf.const import MTEXT_TOP_LEFT  # Add this line
from ezdxf import bbox
import os
from src.style_manager import StyleManager

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
        
        self.subtitle_text_style = get_style(legend_config.get('subtitleTextStyle', {}), self.project_loader)
        self.group_text_style = get_style(legend_config.get('groupTextStyle', {}), self.project_loader)
        self.item_text_style = get_style(legend_config.get('itemTextStyle', {}), self.project_loader)
        self.title_text_style = get_style(legend_config.get('titleTextStyle', {}), self.project_loader)
        self.title_subtitle_style = get_style(legend_config.get('titleSubtitleStyle', {}), self.project_loader)

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
        
        ensure_layer_exists(self.doc, layer_name, {}, self.name_to_aci)

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
        item_type = item.get('type', 'empty')
        
        style = self.get_style(item.get('style', {}))
        
        hatch_style = self.get_style(style.get('hatch', {}))
        layer_style = self.get_style(style.get('layer', {}))
        rectangle_style = self.get_style(item.get('rectangleStyle', {}))
        
        block_symbol = item.get('blockSymbol')
        block_symbol_scale = item.get('blockSymbolScale', 1.0)
        create_hatch = item.get('applyHatch', False)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        log_info(f"Creating item: {item_name}, type: {item_type}, symbol: {block_symbol}")
        
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
        text_result = add_mtext(
            self.msp,
            item_name,
            text_x,
            item_center_y,
            sanitized_layer_name,
            self.item_text_style.get('text_style', 'Standard'),
            self.item_text_style,
            self.project_loader.name_to_aci,
            self.max_width - self.item_width - self.text_offset
        )

        if text_result is None or text_result[0] is None:
            log_warning(f"Failed to create text entity for item '{item_name}'")
            self.current_y -= self.item_height + self.item_spacing
            return

        text_entity, actual_text_height = text_result

        text_bbox = bbox.extents([text_entity])
        text_center_y = (text_bbox.extmin.y + text_bbox.extmax.y) / 2
        vertical_adjustment = item_center_y - text_center_y
        text_entity.translate(0, vertical_adjustment, 0)

        text_bbox = bbox.extents([text_entity])
        combined_bbox = item_bbox.union(text_bbox)

        vertical_offset = self.current_y - combined_bbox.extmax.y
        for entity in item_entities + [text_entity]:
            if entity:
                entity.translate(0, vertical_offset, 0)

        total_height = combined_bbox.size.y

        self.current_y -= total_height + self.item_spacing

        for entity in item_entities + [text_entity]:
            if entity:
                attach_custom_data(entity, self.script_identifier)

    def create_area_item(self, x1, y1, x2, y2, layer_name, hatch_style, layer_style, rectangle_style, create_hatch, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        
        if isinstance(rectangle_style, dict) and 'layer' in rectangle_style:
            self.apply_style(rectangle, rectangle_style['layer'])
        else:
            self.apply_style(rectangle, rectangle_style)
        
        self.attach_custom_data(rectangle)
        entities.append(rectangle)

        if create_hatch:
            hatch_paths = [[(x1, y1), (x2, y1), (x2, y2), (x1, y2)]]
            hatch = dfx_utils.create_hatch(self.msp, hatch_paths, hatch_style, self.project_loader, is_legend=True)
            hatch.dxf.layer = layer_name
            
            if 'color' in hatch_style:
                color = get_color_code(hatch_style['color'], self.project_loader.name_to_aci)
                if isinstance(color, tuple):
                    hatch.rgb = color
                else:
                    hatch.dxf.color = color
            
            if 'pattern' in hatch_style:
                pattern = hatch_style['pattern']
                scale = hatch_style.get('scale', 1)
                try:
                    hatch.set_pattern_fill(pattern, scale=scale)
                except ezdxf.DXFValueError:
                    log_warning(f"Invalid hatch pattern: {pattern}. Using SOLID instead.")
                    hatch.set_solid_fill()
            
            if 'transparency' in hatch_style:
                transparency = convert_transparency(hatch_style['transparency'])
                if transparency is not None:
                    set_hatch_transparency(hatch, transparency)
            
            self.attach_custom_data(hatch)
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
        self.apply_style(line, layer_style)
        self.attach_custom_data(line)
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
        self.apply_style(rectangle, rectangle_style)
        self.attach_custom_data(rectangle)
        entities.append(rectangle)

        line = self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'layer': layer_name})
        self.apply_style(line, layer_style)
        self.attach_custom_data(line)
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
            style_name = text_style.get('text_style', 'Standard')
            if style_name not in self.loaded_styles:
                log_warning(f"Text style '{style_name}' was not loaded during initialization. Using 'Standard' instead.")
                style_name = 'Standard'

            dxfattribs = {
                'style': style_name,
                'char_height': text_style.get('height', 2.5),
                'width': max_width,
                'attachment_point': MTEXT_TOP_LEFT,
                'layer': layer_name,
            }
            
            if 'color' in text_style:
                dxfattribs['color'] = get_color_code(text_style['color'], self.name_to_aci)
            
            mtext = self.msp.add_mtext(text, dxfattribs=dxfattribs)
            mtext.set_location((x, y))
            
            bounding_box = bbox.extents([mtext])
            actual_height = bounding_box.size.y
            
            attach_custom_data(mtext, self.script_identifier)
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

    def get_style(self, style):
        if isinstance(style, str):
            style, warning_generated = self.style_manager.get_style(style)
            if warning_generated:
                return {}
        return style or {}

    def apply_style(self, entity, style):
        if isinstance(style, str):
            style = self.project_loader.get_style(style)
        
        if isinstance(style, dict):
            for key, value in style.items():
                if key == 'color':
                    color = get_color_code(value, self.project_loader.name_to_aci)
                    if isinstance(color, tuple):
                        entity.rgb = color
                    else:
                        entity.dxf.color = color
                elif key == 'linetype':
                    entity.dxf.linetype = value
                elif key == 'lineweight':
                    entity.dxf.lineweight = value
                elif key == 'transparency':
                    entity.transparency = convert_transparency(value)
                # Add more properties as needed

        apply_style_to_entity(entity, style, self.project_loader, self.loaded_styles)




























