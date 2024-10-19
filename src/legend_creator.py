import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import (get_color_code, attach_custom_data, 
                           is_created_by_script, add_mtext, remove_entities_by_layer, 
                           ensure_layer_exists, get_style, SCRIPT_IDENTIFIER,
                           apply_style_to_entity,
                           sanitize_layer_name, get_available_blocks, add_block_reference)
from ezdxf.math import Vec3
from ezdxf import colors
from src.utils import log_warning, log_error, log_info
from src import dfx_utils
from ezdxf.math import BoundingBox
from ezdxf.lldxf.const import MTEXT_TOP_LEFT  # Add this line
from ezdxf import bbox
import os

class LegendCreator:
    def __init__(self, doc, msp, project_loader, loaded_styles):
        self.doc = doc
        self.msp = msp
        self.project_loader = project_loader
        self.loaded_styles = loaded_styles
        self.script_identifier = SCRIPT_IDENTIFIER
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
        self.available_blocks = get_available_blocks(doc)
        self.layer_name_cache = {}  # Add this line to cache sanitized layer names

    def create_legend(self):
        self.selectively_remove_existing_legend()
        self.current_y = self.position['y']
        self.create_legend_title()
        for group in self.legend_config.get('groups', []):
            self.create_group(group)

    def selectively_remove_existing_legend(self):
        remove_entities_by_layer(self.msp, "Legend_Title", self.script_identifier)
        for group in self.legend_config.get('groups', []):
            if group.get('update', False):
                group_name = group.get('name', '')
                layer_name = f"Legend_{group_name}"
                removed_count = remove_entities_by_layer(self.msp, layer_name, self.script_identifier)

    def create_group(self, group):
        group_name = group.get('name', '')
        subtitle = group.get('subtitle', '')
        items = group.get('items', [])
        layer_name = self.get_sanitized_layer_name(f"Legend_{group_name}")
        
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
        hatch_style = self.get_style(item.get('hatch_style', {}))
        style = self.get_style(item.get('style', {}))  # Changed from rectangle_style to style
        rectangle_style = self.get_style(item.get('rectangle_style', {}))
        block_symbol = item.get('block_symbol')
        block_symbol_scale = item.get('block_symbol_scale', 1.0)
        create_hatch = item.get('create_hatch', True)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        log_info(f"Creating item: {item_name}, type: {item_type}, symbol: {block_symbol}")
        
        sanitized_layer_name = self.get_sanitized_layer_name(layer_name)

        # Prepare hatch style
        prepared_hatch_style = {
            'color': hatch_style.get('color'),
            'transparency': hatch_style.get('transparency'),
            'hatch': {
                'pattern': hatch_style.get('hatch', {}).get('pattern', 'SOLID'),
                'scale': hatch_style.get('hatch', {}).get('scale', 1),
                'individual_hatches': hatch_style.get('hatch', {}).get('individual_hatches', True)
            }
        }

        # Step 1: Create the symbol/area/line item
        if item_type == 'area':
            item_entities = self.create_area_item(x1, y1, x2, y2, sanitized_layer_name, prepared_hatch_style, rectangle_style, create_hatch, block_symbol, block_symbol_scale)
        elif item_type == 'line':
            item_entities = self.create_line_item(x1, y1, x2, y2, sanitized_layer_name, style, block_symbol, block_symbol_scale)
        elif item_type == 'diagonal_line':
            item_entities = self.create_diagonal_line_item(x1, y1, x2, y2, sanitized_layer_name, style, block_symbol, block_symbol_scale)
        elif item_type == 'empty':
            item_entities = self.create_empty_item(x1, y1, x2, y2, sanitized_layer_name, block_symbol, block_symbol_scale)
        else:
            raise ValueError(f"Unknown item type: {item_type}")

        # Calculate bounding box for the symbol or virtual box
        item_bbox = bbox.BoundingBox()
        item_bbox.extend([Vec3(x1, y2, 0), Vec3(x2, y1, 0)])

        for entity in item_entities:
            if entity:
                entity_bbox = self.get_entity_bbox(entity)
                item_bbox.extend(entity_bbox)

        # Calculate the vertical center of the item symbol or virtual box
        item_center_y = (item_bbox.extmin.y + item_bbox.extmax.y) / 2

        # Step 2: Create the item title text
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

        # Step 3: Align the text with the symbol
        text_bbox = bbox.extents([text_entity])
        text_center_y = (text_bbox.extmin.y + text_bbox.extmax.y) / 2
        vertical_adjustment = item_center_y - text_center_y
        text_entity.translate(0, vertical_adjustment, 0)

        # Step 4: Get the bounding box of the entire item (symbol + text)
        text_bbox = bbox.extents([text_entity])
        combined_bbox = item_bbox.union(text_bbox)

        # Step 5: Position the entire item according to our placement rules
        vertical_offset = self.current_y - combined_bbox.extmax.y
        for entity in item_entities + [text_entity]:
            if entity:
                entity.translate(0, vertical_offset, 0)

        # Calculate the total height of the item
        total_height = combined_bbox.size.y

        # Adjust the current_y by the total height plus spacing
        self.current_y -= total_height + self.item_spacing

        # Attach custom data to all entities
        for entity in item_entities + [text_entity]:
            if entity:
                attach_custom_data(entity, self.script_identifier)

    def create_area_item(self, x1, y1, x2, y2, layer_name, hatch_style, rectangle_style, create_hatch, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        # Create the rectangle
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        
        # Apply the style to the rectangle
        self.apply_style(rectangle, rectangle_style)
        
        self.attach_custom_data(rectangle)
        entities.append(rectangle)

        # Create hatch if specified
        if create_hatch:
            hatch_paths = [[(x1, y1), (x2, y1), (x2, y2), (x1, y2)]]
            hatch = dfx_utils.create_hatch(self.msp, hatch_paths, hatch_style, self.project_loader, is_legend=True)
            hatch.dxf.layer = layer_name
            self.attach_custom_data(hatch)
            entities.append(hatch)

        # Add symbol if specified
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

    def create_line_item(self, x1, y1, x2, y2, layer_name, rectangle_style, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        # Create the line as before
        middle_y = (y1 + y2) / 2
        points = [(x1, middle_y), (x2, middle_y)]
        line = self.msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
        self.apply_style(line, rectangle_style)
        entities.append(line)

        # Add symbol if specified
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

    def create_diagonal_line_item(self, x1, y1, x2, y2, layer_name, style, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        # Create the rectangle (no styling)
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        self.attach_custom_data(rectangle)
        entities.append(rectangle)

        # Create the diagonal line
        line = self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'layer': layer_name})
        self.apply_style(line, style)
        self.attach_custom_data(line)
        entities.append(line)

        # Add symbol if specified
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

    def create_empty_item(self, x1, y1, x2, y2, layer_name, block_symbol=None, block_symbol_scale=1.0):
        entities = []
        
        # Add symbol if specified
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
            
            # Calculate the bounding box using the bbox module
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

    def create_legend_title(self):
        title = self.legend_config.get('title', '')
        subtitle = self.legend_config.get('subtitle', '')
        layer_name = self.get_sanitized_layer_name("Legend_Title")

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

    def get_sanitized_layer_name(self, name):
        if name not in self.layer_name_cache:
            self.layer_name_cache[name] = sanitize_layer_name(name)
        return self.layer_name_cache[name]

    def get_style(self, style):
        if isinstance(style, str):
            return self.project_loader.get_style(style)
        return style

    def apply_style(self, entity, style):
        if isinstance(style, str):
            style = self.project_loader.get_style(style)
        apply_style_to_entity(entity, style, self.project_loader, self.loaded_styles)
