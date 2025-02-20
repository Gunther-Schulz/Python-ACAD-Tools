"""Module for managing viewports in DXF files."""

import traceback
from ezdxf.lldxf import const
from src.core.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import get_color_code, attach_custom_data

class ViewportManager:
    def __init__(self, project_settings, script_identifier, name_to_aci, style_manager):
        self.project_settings = project_settings
        self.script_identifier = script_identifier
        self.name_to_aci = name_to_aci
        self.style_manager = style_manager
        self.viewports = {}

    def create_viewports(self, doc, msp):
        """Creates or updates viewports based on configuration."""
        paper_space = doc.paperspace()
        
        # Ensure VIEWPORTS layer exists and set it to not plot
        if 'VIEWPORTS' not in doc.layers:
            doc.layers.new('VIEWPORTS')
        viewports_layer = doc.layers.get('VIEWPORTS')
        viewports_layer.dxf.plot = 0
        
        viewport_configs = self.project_settings.get('viewports', [])
        log_debug(f"Found {len(viewport_configs)} viewport configurations")
        
        for vp_config in viewport_configs:
            try:
                name = vp_config.get('name', 'unnamed')
                if not vp_config.get('updateDxf', False):
                    log_debug(f"Skipping viewport {name} as update flag is not set")
                    continue

                viewport = self._create_or_get_viewport(paper_space, vp_config)
                if viewport is None:
                    log_warning(f"Failed to create or get viewport: {name}")
                    continue
                    
                self._update_viewport_properties(viewport, vp_config)
                self._update_viewport_layers(doc, viewport, vp_config)
                self._attach_viewport_metadata(viewport, vp_config)
                self.viewports[name] = viewport
                log_debug(f"Successfully processed viewport: {name}")
                
            except Exception as e:
                log_error(f"Error processing viewport {vp_config.get('name', 'unnamed')}: {str(e)}")
                log_error(f"Traceback: {traceback.format_exc()}")
                continue
        
        log_debug(f"Completed viewport processing. Created/updated {len(self.viewports)} viewports")
        return self.viewports

    def _create_or_get_viewport(self, paper_space, vp_config):
        """Creates new viewport or retrieves existing one."""
        existing_viewport = self.get_viewport_by_name(paper_space.doc, vp_config['name'])
        
        if existing_viewport:
            log_debug(f"Viewport {vp_config['name']} already exists. Updating properties.")
            return existing_viewport
        
        # Create new viewport with physical properties
        width = vp_config['width']
        height = vp_config['height']
        center_x, center_y = self._calculate_viewport_center(vp_config, width, height)
        view_center_point = self._get_view_center_point(vp_config)
        view_height = self._calculate_view_height(height, vp_config)
        
        viewport = paper_space.add_viewport(
            center=(center_x, center_y),
            size=(width, height),
            view_center_point=view_center_point,
            view_height=view_height
        )
        viewport.dxf.status = 1
        viewport.dxf.layer = 'VIEWPORTS'
        
        log_debug(f"Created new viewport: {vp_config['name']}")
        return viewport

    def set_viewport_2d_properties(self, viewport):
        """Set viewport properties to ensure strict 2D behavior."""
        viewport.dxf.flags = 0  # Clear all flags first
        viewport.dxf.flags = 128 | 512  # Set only VSF_FAST_ZOOM (128) and VSF_GRID_MODE (512)
        viewport.dxf.render_mode = 0  # 2D Optimized
        viewport.dxf.view_direction_vector = (0, 0, 1)  # Straight top-down view
        log_debug("Set viewport to strict 2D mode")

    def _update_viewport_properties(self, viewport, vp_config):
        """Updates properties for both new and existing viewports."""
        # Set 2D properties
        self.set_viewport_2d_properties(viewport)
        
        # Set hyperlink to viewport name
        viewport.set_hyperlink(vp_config['name'])
        
        # Update color if specified
        if 'color' in vp_config:
            color = get_color_code(vp_config['color'], self.name_to_aci)
            if isinstance(color, tuple):
                viewport.rgb = color
            else:
                viewport.dxf.color = color
        
        # Update view center if specified
        if 'viewCenter' in vp_config:
            view_center = vp_config['viewCenter']
            viewport.dxf.view_center_point = (view_center['x'], view_center['y'], 0)
        
        # Update scale/view height
        if 'customScale' in vp_config:
            viewport.dxf.view_height = viewport.dxf.height * (1 / vp_config['customScale'])
        elif 'scale' in vp_config:
            viewport.dxf.view_height = viewport.dxf.height * vp_config['scale']
        
        # Set zoom lock if specified
        if vp_config.get('lockZoom', False):
            viewport.dxf.flags |= 16384  # VSF_LOCK_ZOOM
            
        # Add clipped corners if specified
        self.set_clipped_corners(viewport, vp_config)

    def _update_viewport_layers(self, doc, viewport, vp_config):
        """Updates layer visibility settings for the viewport."""
        # Get all actual layers from the document except system layers
        all_layers = set()
        
        # First collect all layers that actually exist in the document
        for layer in doc.layers:
            if layer.dxf.name not in ['0', 'DEFPOINTS', 'VIEWPORTS']:
                all_layers.add(layer.dxf.name)
        
        # Clear existing frozen layers first
        viewport.frozen_layers = []
        
        if 'visibleLayers' in vp_config:
            # Filter out non-existent layers
            visible_layers = set(layer for layer in vp_config['visibleLayers'] if layer in all_layers)
            frozen_layers = [layer for layer in all_layers if layer not in visible_layers]
            viewport.frozen_layers = frozen_layers
        elif 'frozenLayers' in vp_config:
            # Filter out non-existent layers
            viewport.frozen_layers = [layer for layer in vp_config['frozenLayers'] if layer in all_layers]

    def _attach_viewport_metadata(self, viewport, vp_config):
        """Attaches custom data and identifiers to the viewport."""
        # Initialize xdata if needed
        if not hasattr(viewport, 'xdata'):
            viewport.xdata = {}
            
        self.attach_custom_data(viewport, vp_config['name'])
        viewport.set_xdata(
            'DXFEXPORTER',
            [
                (1000, self.script_identifier),
                (1002, '{'),
                (1000, 'VIEWPORT_NAME'),
                (1000, vp_config['name']),
                (1002, '}')
            ]
        )

    def _calculate_viewport_center(self, vp_config, width, height):
        """Calculates the center point for a new viewport."""
        if 'topLeft' in vp_config:
            top_left = vp_config['topLeft']
            return (top_left['x'] + (width / 2), top_left['y'] - (height / 2))
        elif 'center' in vp_config:
            center = vp_config['center']
            return (center['x'], center['y'])
        raise ValueError(f"No position specified for viewport {vp_config['name']}")

    def _get_view_center_point(self, vp_config):
        """Gets the view center point from config."""
        if 'viewTopLeft' in vp_config:
            view_top_left = vp_config['viewTopLeft']
            width = vp_config['width']
            height = vp_config['height']
            scale = 1 / vp_config['customScale'] if 'customScale' in vp_config else vp_config.get('scale', 1.0)
            return (
                view_top_left['x'] + (width * scale / 2),
                view_top_left['y'] - (height * scale / 2),
                0
            )
        elif 'viewCenter' in vp_config:
            view_center = vp_config['viewCenter']
            return (view_center['x'], view_center['y'], 0)
        return None

    def _calculate_view_height(self, height, vp_config):
        """Calculates the view height based on scale settings."""
        if 'customScale' in vp_config:
            return height * (1 / vp_config['customScale'])
        elif 'scale' in vp_config:
            return height * vp_config['scale']
        return height

    def attach_custom_data(self, entity, entity_name=None):
        attach_custom_data(entity, self.script_identifier, entity_name)

    def get_viewport_by_name(self, doc, name):
        """Retrieve a viewport by its name using xdata."""
        for layout in doc.layouts:
            for entity in layout:
                if entity.dxftype() == 'VIEWPORT':
                    try:
                        xdata = entity.get_xdata('DXFEXPORTER')
                        if xdata:
                            in_viewport_section = False
                            for code, value in xdata:
                                if code == 1000 and value == 'VIEWPORT_NAME':
                                    in_viewport_section = True
                                elif in_viewport_section and code == 1000 and value == name:
                                    return entity
                    except:
                        continue
        return None

    def set_clipped_corners(self, viewport, vp_config):
        """Sets custom viewport shape using a clipping boundary.
        
        Args:
            viewport: The viewport entity to modify
            vp_config: The viewport configuration dictionary containing 'clipPath' coordinates
        """
        if 'clipPath' not in vp_config:
            return

        # First, create a new viewport with the same properties
        doc = viewport.doc
        pspace = doc.paperspace()
        
        # Create new viewport with same properties
        new_viewport = pspace.add_viewport(
            center=viewport.dxf.center,
            size=(viewport.dxf.width, viewport.dxf.height),
            view_center_point=viewport.dxf.view_center_point,
            view_height=viewport.dxf.view_height
        )
        
        # Copy all important properties
        new_viewport.dxf.status = viewport.dxf.status
        new_viewport.dxf.layer = viewport.dxf.layer
        new_viewport.frozen_layers = viewport.frozen_layers
        new_viewport.dxf.flags = viewport.dxf.flags
        new_viewport.dxf.render_mode = viewport.dxf.render_mode
        new_viewport.dxf.view_direction_vector = viewport.dxf.view_direction_vector
        
        # Copy xdata if it exists
        try:
            if hasattr(viewport, 'xdata') and viewport.xdata:
                new_viewport.xdata = viewport.xdata.copy()
        except:
            pass
            
        # Copy hyperlink from original viewport
        if hasattr(viewport, 'get_hyperlink'):
            hyperlink = viewport.get_hyperlink()
            if hyperlink:
                new_viewport.set_hyperlink(hyperlink)
        else:
            # Set hyperlink to viewport name if not already set
            new_viewport.set_hyperlink(vp_config['name'])
        
        # Create clipping boundary
        path_points = vp_config['clipPath']
        boundary = pspace.add_lwpolyline(path_points)
        boundary.dxf.layer = 'VIEWPORTS'
        
        # Apply clipping
        new_viewport.dxf.flags |= const.VSF_NON_RECTANGULAR_CLIPPING
        new_viewport.dxf.clipping_boundary_handle = boundary.dxf.handle
        
        # Delete the old viewport
        pspace.delete_entity(viewport)
        
        # Attach metadata to new viewport
        self._attach_viewport_metadata(new_viewport, vp_config)
        
        return new_viewport