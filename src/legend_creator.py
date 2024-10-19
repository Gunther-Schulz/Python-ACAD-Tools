import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import (get_color_code, convert_transparency, attach_custom_data, 
                           is_created_by_script, add_mtext, remove_entities_by_layer, 
                           ensure_layer_exists, update_layer_geometry, get_style, script_identifier,
                           apply_style_to_entity, create_hatch, set_hatch_transparency, script_identifier)
from ezdxf.math import Vec3
from ezdxf import colors
from src.utils import log_warning, log_error, log_info
from src import dfx_utils
from ezdxf.math import BoundingBox
from ezdxf.lldxf.const import MTEXT_TOP_LEFT  # Add this line
from ezdxf import bbox
import os

class LegendCreator:
    def __init__(self, doc, msp, project_loader):
        self.doc = doc
        self.msp = msp
        self.script_identifier = script_identifier
        self.project_loader = project_loader
        self.legend_config = project_loader.project_settings.get('legend', {})
        self.position = self.legend_config.get('position', {'x': 0, 'y': 0})
        self.current_y = self.position['y']
        self.group_spacing = self.legend_config.get('group_spacing', 20)  # Default group spacing of 20 units
        self.item_spacing = self.legend_config.get('item_spacing', 2)
        self.item_width = 30
        self.item_height = 15
        self.text_offset = 5
        self.subtitle_text_style = get_style(self.legend_config.get('subtitleTextStyle', {}), self.project_loader)
        self.subtitle_spacing = self.legend_config.get('subtitle_spacing', 6)
        self.group_title_spacing = self.legend_config.get('group_title_spacing', 8)
        self.group_subtitle_spacing = self.legend_config.get('group_subtitle_spacing', 4)
        
        # Global text styles
        self.group_text_style = get_style(self.legend_config.get('groupTextStyle', {}), self.project_loader)
        self.item_text_style = get_style(self.legend_config.get('itemTextStyle', {}), self.project_loader)
        self.name_to_aci = project_loader.name_to_aci
        self.max_width = self.legend_config.get('max_width', 200)  # Default max width of 200 units
        self.total_item_width = self.item_width + self.text_offset + self.max_width
        self.title_text_style = get_style(self.legend_config.get('titleTextStyle', {}), self.project_loader)
        self.title_subtitle_style = get_style(self.legend_config.get('titleSubtitleStyle', {}), self.project_loader)
        self.title_spacing = self.legend_config.get('title_spacing', 10)
        
        # Instead, get the list of available blocks in the document
        self.available_blocks = set(block.name for block in self.doc.blocks if not block.name.startswith('*'))

    def create_legend(self):
        self.selectively_remove_existing_legend()
        self.current_y = self.position['y']
        self.create_legend_title()
        for group in self.legend_config.get('groups', []):
            self.create_group(group)

    def selectively_remove_existing_legend(self):
        remove_entities_by_layer(self.msp, "Legend_Title", script_identifier)
        for group in self.legend_config.get('groups', []):
            if group.get('update', False):
                group_name = group.get('name', '')
                layer_name = f"Legend_{group_name}"
                removed_count = remove_entities_by_layer(self.msp, layer_name, script_identifier)

    def create_group(self, group):
        group_name = group.get('name', '')
        subtitle = group.get('subtitle', '')
        items = group.get('items', [])
        layer_name = f"Legend_{group_name}"
        
        # Add group title
        title_result = self.add_mtext(self.position['x'], self.current_y, group_name, layer_name, self.group_text_style, self.max_width)
        if title_result is not None and title_result[0] is not None:
            title_entity, actual_title_height = title_result
            self.current_y -= actual_title_height + self.group_title_spacing  # Use group_title_spacing here
        else:
            log_warning(f"Failed to create title MTEXT for group '{group_name}'")
            self.current_y -= self.group_text_style.get('height', 5) + self.group_title_spacing  # Use group_title_spacing here

        # Add subtitle
        if subtitle:
            subtitle_result = self.add_mtext(self.position['x'], self.current_y, subtitle, layer_name, self.subtitle_text_style, self.max_width)
            if subtitle_result is not None and subtitle_result[0] is not None:
                subtitle_entity, actual_subtitle_height = subtitle_result
                self.current_y -= actual_subtitle_height + self.group_subtitle_spacing
            else:
                log_warning(f"Failed to create subtitle MTEXT for group '{group_name}'")
                self.current_y -= self.subtitle_text_style.get('height', 4) + self.group_subtitle_spacing

        # Create items
        for item in items:
            self.create_item(item, layer_name)
        
        self.current_y -= self.group_spacing

    def create_item(self, item, layer_name):
        item_name = item.get('name', '')
        item_type = item.get('type', 'empty')
        item_style = get_style(item.get('style', {}), self.project_loader)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        symbol_name = item.get('symbol')  # This will be None if 'symbol' key is not present
        log_info(f"Creating item: {item_name}, type: {item_type}, symbol: {symbol_name}")
        
        if symbol_name:
            log_info(f"Available blocks: {list(self.available_blocks)}")

        if item_type == 'area':
            item_entities = self.create_area_item(x1, y1, x2, y2, layer_name, item_style, symbol_name)
        elif item_type == 'line':
            item_entities = self.create_line_item(x1, y1, x2, y2, layer_name, item_style, symbol_name)
        elif item_type == 'empty':
            item_entities = self.create_empty_item(x1, y1, x2, y2, layer_name, symbol_name)
        else:
            raise ValueError(f"Unknown item type: {item_type}")

        # Calculate bounding box for the symbol or virtual box
        item_bbox = bbox.BoundingBox()
        item_bbox.extend([Vec3(x1, y2, 0), Vec3(x2, y1, 0)])

        if item_type != 'empty':
            for entity in item_entities:
                if entity:  # Check if the entity is not None
                    entity_bbox = self.get_entity_bbox(entity)
                    item_bbox.extend(entity_bbox)

        # Ensure the item_bbox is at least as big as the defined item dimensions
        item_bbox.extend([Vec3(x1, y1, 0), Vec3(x2, y2, 0)])

        # Calculate the vertical center of the item symbol or virtual box
        item_center_y = (item_bbox.extmin.y + item_bbox.extmax.y) / 2

        # Create the item text using MTEXT
        text_x = x2 + self.text_offset
        text_result = add_mtext(
            self.msp,
            item_name,
            text_x,
            item_center_y,  # Use the center of the symbol or virtual box for text placement
            layer_name,
            self.item_text_style.get('font', 'Standard'),
            self.item_text_style,
            self.project_loader.name_to_aci,
            self.max_width - self.item_width - self.text_offset
        )

        if text_result is None or text_result[0] is None:
            log_warning(f"Failed to create text entity for item '{item_name}'")
            self.current_y -= self.item_height + self.item_spacing
            return

        text_entity, actual_text_height = text_result

        # Adjust text vertical position to align with symbol center or virtual box center
        text_bbox = bbox.extents([text_entity])
        text_center_y = (text_bbox.extmin.y + text_bbox.extmax.y) / 2
        vertical_adjustment = item_center_y - text_center_y
        text_entity.translate(0, vertical_adjustment, 0)

        # Recalculate combined bounding box
        text_bbox = bbox.extents([text_entity])
        combined_bbox = item_bbox.union(text_bbox)

        # Calculate the total height of the item (including symbol/virtual box and text)
        total_height = combined_bbox.size.y

        # Move all entities as a unit to respect the item spacing
        vertical_offset = self.current_y - combined_bbox.extmax.y
        for entity in item_entities + [text_entity]:
            if entity:  # Check if the entity is not None
                entity.translate(0, vertical_offset, 0)

        # Adjust the current_y by the total height plus spacing
        self.current_y -= total_height + self.item_spacing

        # Attach custom data to all entities (only text entity for 'empty' type)
        for entity in item_entities + [text_entity]:
            if entity:  # Check if the entity is not None
                attach_custom_data(entity, self.script_identifier)

    def create_area_item(self, x1, y1, x2, y2, layer_name, item_style, symbol_name=None):
        entities = []
        
        # Create the rectangle and hatch as before
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        self.attach_custom_data(rectangle)
        entities.append(rectangle)

        hatch_paths = [[(x1, y1), (x2, y1), (x2, y2), (x1, y2)]]
        hatch = create_hatch(self.msp, hatch_paths, item_style, self.project_loader, is_legend=True)
        hatch.dxf.layer = layer_name
        self.attach_custom_data(hatch)
        entities.append(hatch)

        # Add symbol if specified
        if symbol_name and symbol_name in self.available_blocks:
            log_info(f"Adding symbol '{symbol_name}' to area item")
            symbol_entity = self.msp.add_blockref(symbol_name, ((x1 + x2) / 2, (y1 + y2) / 2))
            symbol_entity.dxf.layer = layer_name
            self.attach_custom_data(symbol_entity)
            entities.append(symbol_entity)
        elif symbol_name:
            log_warning(f"Symbol '{symbol_name}' not found for area item")

        return entities

    def create_line_item(self, x1, y1, x2, y2, layer_name, item_style, symbol_name=None):
        entities = []
        
        # Create the line as before
        middle_y = (y1 + y2) / 2
        points = [(x1, middle_y), (x2, middle_y)]
        line = self.msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
        apply_style_to_entity(line, item_style, self.project_loader)
        entities.append(line)

        # Add symbol if specified
        if symbol_name and symbol_name in self.available_blocks:
            symbol_entity = self.msp.add_blockref(symbol_name, ((x1 + x2) / 2, middle_y))
            symbol_entity.dxf.layer = layer_name
            self.attach_custom_data(symbol_entity)
            entities.append(symbol_entity)
        elif symbol_name:
            log_warning(f"Symbol '{symbol_name}' not found for line item")

        return entities

    def create_empty_item(self, x1, y1, x2, y2, layer_name, symbol_name=None):
        entities = []
        
        # Add symbol if specified
        if symbol_name and symbol_name in self.available_blocks:
            symbol_entity = self.msp.add_blockref(symbol_name, ((x1 + x2) / 2, (y1 + y2) / 2))
            symbol_entity.dxf.layer = layer_name
            self.attach_custom_data(symbol_entity)
            entities.append(symbol_entity)
        elif symbol_name:
            log_warning(f"Symbol '{symbol_name}' not found for empty item")

        return entities

    def add_mtext(self, x, y, text, layer_name, text_style, max_width=None):
        try:
            dxfattribs = {
                'style': text_style.get('font', 'Standard'),
                'char_height': text_style.get('height', 2.5),
                'width': max_width,
                'attachment_point': MTEXT_TOP_LEFT,
                'layer': layer_name,
            }
            
            if 'color' in text_style:
                dxfattribs['color'] = get_color_code(text_style['color'], self.name_to_aci)
            
            mtext = self.msp.add_mtext(text, dxfattribs=dxfattribs)
            mtext.set_location((x, y))
            
            # Calculate the bounding box using the bbox module
            bounding_box = bbox.extents([mtext])
            actual_height = bounding_box.size.y
            
            attach_custom_data(mtext, script_identifier)
            return mtext, actual_height
        except Exception as e:
            log_error(f"Error creating MTEXT: {str(e)}")
            return None, 0

    def attach_custom_data(self, entity):
        if entity is not None:
            attach_custom_data(entity, script_identifier)
        else:
            log_warning("Attempted to attach custom data to a None entity")

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, script_identifier)

    def get_color_code(self, color):
        return get_color_code(color, self.name_to_aci)

    def create_legend_title(self):
        title = self.legend_config.get('title', '')
        subtitle = self.legend_config.get('subtitle', '')
        layer_name = "Legend_Title"

        ensure_layer_exists(self.doc, layer_name, {})

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
