import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf import const
from src.dfx_utils import (get_color_code, convert_transparency, attach_custom_data, 
                           is_created_by_script, add_mtext, remove_entities_by_layer, 
                           ensure_layer_exists, update_layer_geometry, get_style, script_identifier,
                           apply_style_to_entity, create_hatch, set_hatch_transparency, script_identifier)
from ezdxf.math import Vec3
from ezdxf import colors
from src.utils import log_warning, log_error
from src import dfx_utils
from ezdxf.math import BoundingBox
from ezdxf.lldxf.const import MTEXT_TOP_LEFT  # Add this line
from ezdxf import bbox

class LegendCreator:
    def __init__(self, doc, msp, project_loader):
        self.doc = doc
        self.msp = msp
        self.project_loader = project_loader
        self.legend_config = project_loader.project_settings.get('legend', {})
        self.position = self.legend_config.get('position', {'x': 0, 'y': 0})
        self.current_y = self.position['y']
        self.group_spacing = self.legend_config.get('group_spacing', 15)  # Default group spacing of 15 units
        self.item_spacing = self.legend_config.get('item_spacing', 10)
        self.item_width = 30
        self.item_height = 15
        self.text_offset = 5
        self.subtitle_text_style = get_style(self.legend_config.get('subtitleTextStyle', {}), self.project_loader)
        self.subtitle_spacing = self.legend_config.get('subtitle_spacing', 10)
        
        # Global text styles
        self.group_text_style = get_style(self.legend_config.get('groupTextStyle', {}), self.project_loader)
        self.item_text_style = get_style(self.legend_config.get('itemTextStyle', {}), self.project_loader)
        self.name_to_aci = project_loader.name_to_aci
        self.max_width = self.legend_config.get('max_width', 200)  # Default max width of 200 units
        self.total_item_width = self.item_width + self.text_offset + self.max_width
        self.between_group_spacing = self.legend_config.get('between_group_spacing', 25)  # Default spacing of 25 units between groups
        self.text_line_spacing = min(max(1.5, 0.25), 4.00)  # Ensure it's within the valid range
        self.title_text_style = get_style(self.legend_config.get('titleTextStyle', {}), self.project_loader)
        self.title_subtitle_style = get_style(self.legend_config.get('titleSubtitleStyle', {}), self.project_loader)
        self.title_spacing = self.legend_config.get('title_spacing', 20)

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
        group_name = group['name']
        items = group['items']
        subtitle = group.get('subtitle', '')
        layer_name = f"Legend_{group_name}"
        
        # Add group title
        title_result = self.add_mtext(
            self.position['x'],
            self.current_y,
            group_name,
            layer_name,
            self.group_text_style,
            self.max_width
        )
        
        if title_result is None or title_result[0] is None:
            log_warning(f"Failed to create title MTEXT for group '{group_name}'")
            self.current_y -= self.group_text_style.get('height', 7) + self.group_spacing
        else:
            title_entity, actual_title_height = title_result
            self.current_y -= actual_title_height + self.group_spacing

        # Add subtitle
        if subtitle:
            subtitle_result = self.add_mtext(self.position['x'], self.current_y, subtitle, layer_name, self.subtitle_text_style, self.max_width)
            if subtitle_result is not None and subtitle_result[0] is not None:
                subtitle_entity, actual_subtitle_height = subtitle_result
                self.current_y -= actual_subtitle_height + self.subtitle_spacing
            else:
                log_warning(f"Failed to create subtitle MTEXT for group '{group_name}'")
                self.current_y -= self.subtitle_text_style.get('height', 4) + self.subtitle_spacing

        # Create items
        for item in items:
            self.create_item(item, layer_name)
        
        self.current_y -= self.between_group_spacing

    def create_item(self, item, layer_name):
        item_name = item.get('name', '')
        item_type = item.get('type', 'empty')
        item_style = get_style(item.get('style', {}), self.project_loader)

        x1, y1 = self.position['x'], self.current_y
        x2, y2 = x1 + self.item_width, y1 - self.item_height

        # Create the item symbol
        if item_type == 'area':
            item_entity = self.create_area_item(x1, y1, x2, y2, layer_name, item_style)
        elif item_type == 'line':
            item_entity = self.create_line_item(x1, y1, x2, y2, layer_name, item_style)
        elif item_type == 'empty':
            item_entity = None
        else:
            raise ValueError(f"Unknown item type: {item_type}")

        # Create the item text using MTEXT
        text_x = x2 + self.text_offset
        text_result = add_mtext(
            self.msp,
            item_name,
            text_x,
            y1,
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

        # Calculate bounding boxes
        if item_entity:
            if isinstance(item_entity, ezdxf.entities.Hatch):
                # For Hatch entities, we need to use the bounding box of its paths
                item_bbox = bbox.BoundingBox()
                for path in item_entity.paths:
                    if hasattr(path, 'vertices'):
                        item_bbox.extend(path.vertices)
                    elif hasattr(path, 'control_points'):
                        item_bbox.extend(path.control_points)
            else:
                item_bbox = bbox.extents([item_entity])
        else:
            item_bbox = bbox.BoundingBox(Vec3(x1, y2, 0), Vec3(x2, y1, 0))
        
        text_bbox = bbox.extents([text_entity])
        combined_bbox = item_bbox.union(text_bbox)

        # Calculate the vertical center of the item symbol
        item_center_y = (item_bbox.extmin.y + item_bbox.extmax.y) / 2

        # Adjust the text position to align with the center of the item symbol
        text_entity.dxf.insert = Vec3(text_x, item_center_y + actual_text_height / 2, 0)

        # Calculate the total height of the item (including symbol and text)
        total_height = combined_bbox.size.y

        # Adjust the current_y by the total height plus spacing
        self.current_y -= total_height + self.item_spacing

        # Move both the item symbol and text to respect the item spacing
        if item_entity:
            item_entity.translate(0, -self.item_spacing, 0)
        text_entity.translate(0, -self.item_spacing, 0)

        # Attach custom data to both entities
        if item_entity:
            attach_custom_data(item_entity, script_identifier)
        attach_custom_data(text_entity, script_identifier)

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

        self.current_y -= self.between_group_spacing
