import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import (get_color_code, convert_transparency, attach_custom_data, 
                           is_created_by_script, add_mtext, remove_entities_by_layer, 
                           ensure_layer_exists, update_layer_geometry, get_style,
                           apply_style_to_entity, create_hatch, set_hatch_transparency, script_identifier)
from ezdxf.math import Vec3
from ezdxf import colors
from src.utils import log_warning

class LegendCreator:
    def __init__(self, doc, msp, project_loader):
        self.doc = doc
        self.msp = msp
        self.project_loader = project_loader
        self.legend_config = project_loader.project_settings.get('legend', {})
        self.position = self.legend_config.get('position', {'x': 0, 'y': 0})
        self.current_y = self.position['y']
        self.group_spacing = self.legend_config.get('group_spacing', 20)  # Default group spacing of 20 units
        self.item_spacing = 10
        self.item_width = 30
        self.item_height = 15
        self.text_offset = 5
        self.subtitle_text_style = get_style(self.legend_config.get('subtitleTextStyle', {}), self.project_loader)
        self.subtitle_spacing = 15  # Add spacing for subtitle
        
        # Global text styles
        self.group_text_style = get_style(self.legend_config.get('groupTextStyle', {}), self.project_loader)
        self.item_text_style = get_style(self.legend_config.get('itemTextStyle', {}), self.project_loader)
        self.name_to_aci = project_loader.name_to_aci
        self.max_width = self.legend_config.get('max_width', 200)  # Default max width of 200 units
        self.total_item_width = self.item_width + self.text_offset + self.max_width
        self.between_group_spacing = self.legend_config.get('between_group_spacing', 40)  # Default spacing of 40 units between groups
        self.text_line_spacing = 1.5  # Line spacing factor

    def create_legend(self):
        self.selectively_remove_existing_legend()
        for group in self.legend_config.get('groups', []):
            self.create_group(group)

    def selectively_remove_existing_legend(self):
        for group in self.legend_config.get('groups', []):
            if group.get('update', False):
                group_name = group.get('name', '')
                layer_name = f"Legend_{group_name}"
                removed_count = remove_entities_by_layer(self.msp, layer_name, script_identifier)

    def create_group(self, group):
        group_name = group.get('name', '')
        subtitle = group.get('subtitle', '')
        layer_name = f"Legend_{group_name}"
        
        group_style = get_style(group.get('style', {}), self.project_loader)
        ensure_layer_exists(self.doc, layer_name, group_style)
        
        # Add group title
        title_height = self.group_text_style.get('height', 5)
        title_entity = self.add_mtext(self.position['x'], self.current_y, group_name, layer_name, self.group_text_style, self.max_width)
        self.current_y = title_entity.dxf.insert.y - title_height - self.group_spacing

        # Add subtitle
        if subtitle:
            subtitle_height = self.subtitle_text_style.get('height', 3)
            subtitle_entity = self.add_mtext(self.position['x'], self.current_y, subtitle, layer_name, self.subtitle_text_style, self.max_width)
            self.current_y = subtitle_entity.dxf.insert.y - subtitle_height - self.subtitle_spacing

        # Create items
        for item in group.get('items', []):
            self.create_item(item, layer_name)
        
        # Add extra spacing after the group
        self.current_y -= self.between_group_spacing

    def create_item(self, item, layer_name):
        item_name = item.get('name', '')
        item_type = item.get('type', 'empty')
        item_style = get_style(item.get('style', {}), self.project_loader)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        if item_type == 'area':
            item_entity = self.create_area_item(x1, y1, x2, y2, layer_name, item_style)
        elif item_type == 'line':
            item_entity = self.create_line_item(x1, y1, x2, y2, layer_name, item_style)
        elif item_type == 'empty':
            item_entity = self.create_empty_item(x1, y1, x2, y2, layer_name)

        # Add item name
        text_x = x2 + self.text_offset
        text_y = y1  # Align text with top of the item
        text_width = self.max_width - self.item_width - self.text_offset
        text_entity = self.add_mtext(text_x, text_y, item_name, layer_name, self.item_text_style, text_width)
        
        # Calculate the bottom of the entire item (including text)
        text_height = self.item_text_style.get('height', 3)
        bottom_y = min(y2, text_entity.dxf.insert.y - text_height)

        # Update current_y to be below the item or text, whichever is lower
        self.current_y = bottom_y - self.item_spacing

    def create_area_item(self, x1, y1, x2, y2, layer_name, item_style):
        # Create the rectangle without applying any style
        rectangle = self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})
        self.attach_custom_data(rectangle)

        # Create and style the hatch
        hatch_paths = [[(x1, y1), (x2, y1), (x2, y2), (x1, y2)]]
        hatch = create_hatch(self.msp, hatch_paths, item_style, self.project_loader, is_legend=True)
        hatch.dxf.layer = layer_name
        self.attach_custom_data(hatch)

        # Set hatch transparency
        if 'transparency' in item_style:
            transparency = convert_transparency(item_style['transparency'])
            set_hatch_transparency(hatch, transparency)

        return hatch

    def create_line_item(self, x1, y1, x2, y2, layer_name, item_style):
        line = self.msp.add_line((x1, y1 - self.item_height / 2), (x2, y1 - self.item_height / 2), dxfattribs={'layer': layer_name})
        apply_style_to_entity(line, item_style, self.project_loader, item_type='line')
        self.attach_custom_data(line)

    def create_empty_item(self, x1, y1, x2, y2, layer_name):
        # For empty items, we don't need to draw anything
        pass

    def add_mtext(self, x, y, text, layer_name, text_style, text_width=None):
        mtext_entity = add_mtext(self.msp, text, x, y, layer_name, 'Standard', text_style, self.name_to_aci, text_width)
        apply_style_to_entity(mtext_entity, text_style, self.project_loader)
        self.attach_custom_data(mtext_entity)
        
        # Ensure char_height is set
        if 'height' in text_style:
            mtext_entity.dxf.char_height = text_style['height']
        
        # Set line spacing
        mtext_entity.dxf.line_spacing_factor = self.text_line_spacing
        
        return mtext_entity

    def attach_custom_data(self, entity):
        attach_custom_data(entity, script_identifier)

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, script_identifier)

    def get_color_code(self, color):
        return get_color_code(color, self.name_to_aci)
