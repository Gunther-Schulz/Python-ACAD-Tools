import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import (get_color_code, convert_transparency, attach_custom_data, 
                           is_created_by_script, add_text, remove_entities_by_layer, 
                           ensure_layer_exists, update_layer_geometry, get_style,
                           apply_style_to_entity, create_hatch, set_hatch_transparency)
from ezdxf.math import Vec3
from ezdxf import colors

class LegendCreator:
    def __init__(self, doc, msp, project_loader):
        self.doc = doc
        self.msp = msp
        self.project_loader = project_loader
        self.legend_config = project_loader.project_settings.get('legend', {})
        self.position = self.legend_config.get('position', {'x': 0, 'y': 0})
        self.current_y = self.position['y']
        self.group_spacing = 20
        self.item_spacing = 10
        self.item_width = 30
        self.item_height = 15
        self.text_offset = 5
        self.script_identifier = "Created by LegendCreator"
        
        # Global text styles
        self.group_text_style = get_style(self.legend_config.get('groupTextStyle', {}), self.project_loader)
        self.item_text_style = get_style(self.legend_config.get('itemTextStyle', {}), self.project_loader)

    def create_legend(self):
        for group in self.legend_config.get('groups', []):
            self.create_group(group)

    def remove_existing_legend(self):
        legend_layers = [f"Legend_{group['name']}" for group in self.legend_config.get('groups', [])]
        legend_layers.append("Legend")  # Add the main legend layer
        
        for layer_name in legend_layers:
            removed_count = remove_entities_by_layer(self.msp, layer_name, self.script_identifier)

    def create_group(self, group):
        group_name = group.get('name', '')
        layer_name = f"Legend_{group_name}"
        
        # Get and apply group style
        group_style = get_style(group.get('style', {}), self.project_loader)
        ensure_layer_exists(self.doc, layer_name, group_style)
        
        # Add group title with global group text style
        self.add_text(self.position['x'], self.current_y, group_name, layer_name, self.group_text_style)
        self.current_y -= self.group_spacing

        # Create items
        for item in group.get('items', []):
            self.create_item(item, layer_name)

        self.current_y -= self.group_spacing

    def create_item(self, item, layer_name):
        item_name = item.get('name', '')
        item_type = item.get('type', 'empty')
        item_style = get_style(item.get('style', {}), self.project_loader)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        if item_type == 'area':
            self.create_area_item(x1, y1, x2, y2, layer_name, item_style)
        elif item_type == 'line':
            self.create_line_item(x1, y1, x2, y2, layer_name, item_style)
        elif item_type == 'empty':
            self.create_empty_item(x1, y1, x2, y2, layer_name)

        # Add item name with global item text style
        text_x = x2 + self.text_offset
        text_y = y1 - self.item_height / 2  # Center the text vertically
        self.add_text(text_x, text_y, item_name, layer_name, self.item_text_style)

        self.current_y -= self.item_height + self.item_spacing

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

    def add_text(self, x, y, text, layer_name, text_style):
        text_entity = add_text(self.msp, text, x, y, layer_name, 'Standard')
        apply_style_to_entity(text_entity, text_style, self.project_loader)
        self.attach_custom_data(text_entity)

    def attach_custom_data(self, entity):
        attach_custom_data(entity, self.script_identifier)

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, self.script_identifier)
