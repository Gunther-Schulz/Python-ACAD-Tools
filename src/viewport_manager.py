from ezdxf.lldxf import const
from src.utils import log_info, log_warning
from src.dfx_utils import get_color_code, attach_custom_data

class ViewportManager:
    def __init__(self, project_settings, script_identifier, name_to_aci, style_manager):
        self.project_settings = project_settings
        self.script_identifier = script_identifier
        self.name_to_aci = name_to_aci
        self.style_manager = style_manager
        self.viewports = {}

    def create_viewports(self, doc, msp):
        """Creates or updates viewports based on configuration.
        
        Properties updated for EXISTING viewports:
        - 2D properties (flags, render_mode, view_direction_vector)
        - color (if specified)
        - view_center_point (if specified)
        - view_height (based on scale)
        - frozen_layers
        - zoom lock
        
        Properties set ONLY for NEW viewports:
        - size (width, height)
        - center position
        - status
        - layer assignment
        """
        paper_space = doc.paperspace()
        
        # Ensure VIEWPORTS layer exists and set it to not plot
        if 'VIEWPORTS' not in doc.layers:
            doc.layers.new('VIEWPORTS')
        viewports_layer = doc.layers.get('VIEWPORTS')
        viewports_layer.dxf.plot = 0
        
        for vp_config in self.project_settings.get('viewports', []):
            if not vp_config.get('updateDxf', False):
                log_info(f"Skipping viewport {vp_config.get('name', 'unnamed')} as update flag is not set")
                continue

            viewport = self._create_or_get_viewport(paper_space, vp_config)
            self._update_viewport_properties(viewport, vp_config)
            self._update_viewport_layers(doc, viewport, vp_config)
            self._attach_viewport_metadata(viewport, vp_config)
            
            self.viewports[vp_config['name']] = viewport
            
        return self.viewports

    def _create_or_get_viewport(self, paper_space, vp_config):
        """Creates new viewport or retrieves existing one."""
        existing_viewport = self.get_viewport_by_name(paper_space.doc, vp_config['name'])
        
        if existing_viewport:
            log_info(f"Viewport {vp_config['name']} already exists. Updating properties.")
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
        
        log_info(f"Created new viewport: {vp_config['name']}")
        return viewport

    def set_viewport_2d_properties(self, viewport):
        """Set viewport properties to ensure strict 2D behavior."""
        viewport.dxf.flags = 0  # Clear all flags first
        viewport.dxf.flags = 128 | 512  # Set only VSF_FAST_ZOOM (128) and VSF_GRID_MODE (512)
        viewport.dxf.render_mode = 0  # 2D Optimized
        viewport.dxf.view_direction_vector = (0, 0, 1)  # Straight top-down view
        log_info("Set viewport to strict 2D mode")

    def _update_viewport_properties(self, viewport, vp_config):
        """Updates properties for both new and existing viewports."""
        # Set 2D properties
        self.set_viewport_2d_properties(viewport)
        
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
        all_layers = set(layer.dxf.name for layer in doc.layers if 
                        layer.dxf.name not in ['0', 'DEFPOINTS', 'VIEWPORTS'])
        
        frozen_layers = []
        
        if 'visibleLayers' in vp_config:
            visible_layers = set(vp_config['visibleLayers'])
            frozen_layers = [layer for layer in all_layers if layer not in visible_layers]
            log_info(f"Using visibleLayers setting for viewport {vp_config['name']}")
        elif 'frozenLayers' in vp_config:
            frozen_layers = vp_config['frozenLayers']
            log_info(f"Using frozenLayers setting for viewport {vp_config['name']}")
        
        if frozen_layers:
            viewport.frozen_layers = frozen_layers
            log_info(f"Updated frozen layers for viewport {vp_config['name']}")

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