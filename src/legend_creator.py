import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import get_color_code, convert_transparency, attach_custom_data, is_created_by_script, add_text, remove_entities_by_layer, ensure_layer_exists
from ezdxf.math import Vec3
from ezdxf import enums

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

    def create_legend(self):
        if not self.legend_config:
            return

        update_flag = self.legend_config.get('update', False)
        if update_flag:
            self.remove_existing_legend()

        for group in self.legend_config.get('groups', []):
            self.create_group(group)

    def remove_existing_legend(self):
        legend_layers = [f"Legend_{group['name']}" for group in self.legend_config.get('groups', [])]
        legend_layers.append("Legend")  # Add the main legend layer
        
        for layer_name in legend_layers:
            removed_count = remove_entities_by_layer(self.msp, layer_name, self.script_identifier)
            print(f"Removed {removed_count} entities from layer {layer_name}")

    def create_group(self, group):
        group_name = group.get('name', '')
        layer_name = f"Legend_{group_name}"
        
        ensure_layer_exists(self.doc, layer_name, {
            'color': get_color_code('White', self.project_loader.name_to_aci),
            'linetype': 'Continuous',
            'lineweight': 13,
            'plot': True,
            'locked': False,
            'frozen': False,
            'is_on': True,
            'transparency': 0.0
        })
        
        self.add_text(self.position['x'], self.current_y, group_name, layer_name)
        self.current_y -= self.item_spacing

        for item in group.get('items', []):
            self.create_item(item, layer_name)

        self.current_y -= self.group_spacing

    def create_item(self, item, layer_name):
        item_name = item.get('name', '')
        style = item.get('style', {})

        # Create rectangle
        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height
        self.msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)], dxfattribs={'layer': layer_name})

        # Apply style
        color = get_color_code(style.get('color', 'White'), self.project_loader.name_to_aci)
        linetype = style.get('linetype', 'Continuous')
        self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'color': color, 'linetype': linetype, 'layer': layer_name})

        # Add hatch if specified
        if 'hatch' in style:
            hatch = self.msp.add_hatch(color=color, dxfattribs={'layer': layer_name})
            hatch.set_pattern_fill(style['hatch'].get('pattern', 'SOLID'), scale=style['hatch'].get('scale', 1))
            hatch.paths.add_polyline_path([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])

        # Add item name
        text_x = x2 + self.text_offset
        text_y = y1 - self.item_height / 2  # Center the text vertically
        self.add_text(text_x, text_y, item_name, layer_name)

        self.current_y -= self.item_height + self.item_spacing

    def add_text(self, x, y, text, layer_name):
        text_entity = add_text(self.msp, text, x, y, layer_name, 'Standard', height=5, color=get_color_code('White', self.project_loader.name_to_aci))
        attach_custom_data(text_entity, self.script_identifier)

    def attach_custom_data(self, entity):
        attach_custom_data(entity, self.script_identifier)

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, self.script_identifier)
