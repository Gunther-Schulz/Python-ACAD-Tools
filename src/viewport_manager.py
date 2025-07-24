import traceback
from ezdxf.lldxf import const
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import get_color_code, attach_custom_data, XDATA_APP_ID, find_entity_by_xdata_name
from src.sync_manager_base import SyncManagerBase
from src.sync_hash_utils import calculate_entity_content_hash, clean_entity_config_for_yaml_output

class ViewportManager(SyncManagerBase):
    def __init__(self, project_settings, script_identifier, name_to_aci, style_manager, project_loader=None):
        # Initialize base class
        super().__init__(project_settings, script_identifier, 'viewport', project_loader)

        # Viewport-specific dependencies
        self.name_to_aci = name_to_aci
        self.style_manager = style_manager
        self.viewports = {}

        # Extract viewport-specific global settings (non-generalized)
        self.default_layer = project_settings.get('viewport_layer', 'VIEWPORTS')

        log_debug(f"ViewportManager initialized with discovery={self.discovery_enabled}, "
                 f"deletion_policy={self.deletion_policy}, default_layer={self.default_layer}, "
                 f"default_sync={self.default_sync}")

    def _get_entity_configs(self):
        """Get viewport configurations from project settings."""
        return self.project_settings.get('viewports', []) or []

    def sync_viewports(self, doc, msp):
        """Enhanced viewport synchronization with bidirectional support."""
        paper_space = doc.paperspace()

        # Ensure configured viewport layer exists and set it to not plot
        if self.default_layer not in doc.layers:
            doc.layers.new(self.default_layer)
        viewports_layer = doc.layers.get(self.default_layer)
        viewports_layer.dxf.plot = 0
        log_debug(f"Using viewport layer: {self.default_layer}")

        try:
            # Use base class functionality for discovery, sync, and deletion
            processed_viewports = self.process_entities(doc, paper_space)
            self.viewports.update(processed_viewports)

            return self.viewports

        except Exception as e:
            log_error(f"Error during viewport synchronization: {str(e)}")
            return {}

    def _write_entity_yaml(self):
        """Write updated viewport configuration back to YAML file."""
        if not self.project_loader:
            log_warning("Cannot write viewport YAML - no project_loader available")
            return False

        try:
            # Clean and prepare viewport configurations for YAML output
            cleaned_viewports = []
            for viewport_config in self.project_settings.get('viewports', []):
                # Clean the configuration for YAML output (handles sync metadata properly)
                cleaned_config = clean_entity_config_for_yaml_output(viewport_config)
                cleaned_viewports.append(cleaned_config)

            # Prepare viewport data structure
            viewport_data = {
                'viewports': cleaned_viewports
            }

            # Add global viewport settings using new generalized structure
            if 'viewport_discovery' in self.project_settings:
                viewport_data['discovery'] = self.project_settings['viewport_discovery']
            if 'viewport_deletion_policy' in self.project_settings:
                viewport_data['deletion_policy'] = self.project_settings['viewport_deletion_policy']
            if 'viewport_layer' in self.project_settings:
                viewport_data['layer'] = self.project_settings['viewport_layer']
            if 'viewport_sync' in self.project_settings:
                viewport_data['sync'] = self.project_settings['viewport_sync']

            # Write back to viewports.yaml
            success = self.project_loader.write_yaml_file('viewports.yaml', viewport_data)
            if success:
                log_info("Successfully updated viewports.yaml with sync changes")
            else:
                log_error("Failed to write viewport configuration back to YAML")
            return success

        except Exception as e:
            log_error(f"Error writing viewport YAML: {str(e)}")
            log_error(f"Traceback: {traceback.format_exc()}")
            return False

    def _sync_push(self, doc, space, config):
        """Sync YAML → AutoCAD (create/update viewport from config)."""
        name = config.get('name', 'unnamed')
        paper_space = doc.paperspace()  # Viewports are always in paperspace

        # Use existing create/update logic
        viewport = self._create_or_get_viewport(paper_space, config)
        if viewport is None:
            log_warning(f"Failed to create or get viewport: {name}")
            return None

        self._update_viewport_properties(viewport, config)
        self._update_viewport_layers(doc, viewport, config)
        self._attach_viewport_metadata(viewport, config)
        self.viewports[name] = viewport
        return viewport

    def _sync_pull(self, doc, space, config):
        """Sync AutoCAD → YAML (update config from AutoCAD viewport)."""
        name = config.get('name', 'unnamed')

        # Find existing viewport in AutoCAD
        existing_viewport = self.get_viewport_by_name(doc, name)
        if existing_viewport is None:
            log_warning(f"Cannot pull viewport '{name}' - not found in AutoCAD")
            return None

        # Extract properties from AutoCAD viewport
        try:
            updated_config = self._extract_entity_properties(existing_viewport, config)

            # Update the configuration in project_settings
            viewport_configs = self.project_settings.get('viewports', []) or []
            for i, original_config in enumerate(viewport_configs):
                if original_config.get('name') == name:
                    # Preserve sync direction and other non-geometric properties
                    # Only preserve explicitly set sync directions - let entities inherit global default
                    if 'sync' in original_config:
                        updated_config['sync'] = original_config['sync']
                    # DO NOT automatically add explicit sync settings
                    if 'frozenLayers' in original_config:
                        updated_config['frozenLayers'] = original_config['frozenLayers']
                    if 'visibleLayers' in original_config:
                        updated_config['visibleLayers'] = original_config['visibleLayers']
                    if 'lockZoom' in original_config:
                        updated_config['lockZoom'] = original_config['lockZoom']
                    if 'color' in original_config:
                        updated_config['color'] = original_config['color']
                    if 'layer' in original_config:
                        updated_config['layer'] = original_config['layer']

                    viewport_configs[i] = updated_config
                    break

            self.viewports[name] = existing_viewport
            return {'entity': existing_viewport, 'yaml_updated': True}

        except Exception as e:
            log_error(f"Error pulling viewport properties for '{name}': {str(e)}")
            return None

    def _create_or_get_viewport(self, paper_space, vp_config):
        """Creates new viewport or retrieves existing one."""
        existing_viewport = self.get_viewport_by_name(paper_space.doc, vp_config['name'])

        if existing_viewport:
            return existing_viewport

        # Determine viewport layer
        viewport_layer = self._get_viewport_layer(vp_config)

        # Ensure the viewport layer exists
        doc = paper_space.doc
        if viewport_layer not in doc.layers:
            doc.layers.new(viewport_layer)
            # Set to not plot by default for viewport layers
            doc.layers.get(viewport_layer).dxf.plot = 0

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
        viewport.dxf.layer = viewport_layer

        return viewport

    def set_viewport_2d_properties(self, viewport):
        """Set viewport properties to ensure strict 2D behavior."""
        viewport.dxf.flags = 0  # Clear all flags first
        viewport.dxf.flags = 128 | 512  # Set only VSF_FAST_ZOOM (128) and VSF_GRID_MODE (512)
        viewport.dxf.render_mode = 0  # 2D Optimized
        viewport.dxf.view_direction_vector = (0, 0, 1)  # Straight top-down view

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
        # Calculate content hash for the configuration
        content_hash = self._calculate_entity_hash(vp_config)

        # Use unified XDATA function with content hash
        attach_custom_data(viewport, self.script_identifier, vp_config['name'], 'VIEWPORT', content_hash)

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

    def attach_custom_data(self, entity, entity_name=None, entity_type=None):
        attach_custom_data(entity, self.script_identifier, entity_name, entity_type)

    def _get_viewport_layer(self, vp_config):
        """Determine the layer for a viewport, supporting per-viewport override."""
        viewport_layer = vp_config.get('layer', self.default_layer)
        return viewport_layer

    def get_viewport_by_name(self, doc, name):
        """Retrieve a viewport by its name using xdata."""
        for layout in doc.layouts:
            viewport = find_entity_by_xdata_name(layout, name, ['VIEWPORT'])
            if viewport:
                # Validate entity handle (auto sync integrity check)
                if self._validate_entity_handle(viewport, name):
                    return viewport
                else:
                    # Entity found but failed validation (copied entity)
                    return None  # Treat as missing to trigger push
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

        # Always set app-controlled hyperlink (NOT copy from original)
        # The hyperlink should always be controlled by our app, never pulled from AutoCAD
        new_viewport.set_hyperlink(vp_config['name'])

        # Create clipping boundary
        path_points = vp_config['clipPath']
        boundary = pspace.add_lwpolyline(path_points)
        boundary.dxf.layer = new_viewport.dxf.layer

        # Apply clipping
        new_viewport.dxf.flags |= const.VSF_NON_RECTANGULAR_CLIPPING
        new_viewport.dxf.clipping_boundary_handle = boundary.dxf.handle

        # Delete the old viewport
        pspace.delete_entity(viewport)

        # Attach metadata to new viewport
        self._attach_viewport_metadata(new_viewport, vp_config)

        return new_viewport

    def _discover_unknown_entities(self, doc, space):
        """Discover viewports in AutoCAD that aren't managed by this script."""
        # Use centralized discovery logic from SyncManagerBase
        return super()._discover_unknown_entities(doc, space)

    def _handle_entity_deletions(self, doc, space):
        """Handle deletion of viewports that exist in YAML but not in AutoCAD."""
        if self.deletion_policy == 'ignore':
            return []

        viewport_configs = self.project_settings.get('viewports', []) or []
        missing_viewports = []
        corrupted_viewports = []

        # Check each configured viewport to see if it still exists in AutoCAD
        for vp_config in viewport_configs:
            viewport_name = vp_config.get('name')
            if not viewport_name:
                continue

            # Only check viewports that are in 'pull' mode
            # In pull mode, AutoCAD is the source of truth, so missing viewports should be removed from YAML
            # In push mode, YAML is the source of truth, so missing viewports should be created in AutoCAD
            sync_direction = self._get_sync_direction(vp_config)
            if sync_direction != 'pull':
                continue

            # Check if viewport exists in AutoCAD
            existing_viewport = self.get_viewport_by_name(doc, viewport_name)
            if existing_viewport is None:
                missing_viewports.append(vp_config)
                log_info(f"Viewport '{viewport_name}' configured in YAML but not found in AutoCAD")
            else:
                # Check if the found viewport is corrupted (center == view_center)
                try:
                    center = existing_viewport.dxf.center
                    view_center = existing_viewport.dxf.view_center_point
                    viewport_id = getattr(existing_viewport.dxf, 'id', None)

                    # Skip corruption check for main viewport (ID=1) - it's supposed to have identical coordinates
                    if viewport_id != 1 and (abs(center[0] - view_center[0]) < 0.001 and
                                              abs(center[1] - view_center[1]) < 0.001):
                        log_error(f"Viewport '{viewport_name}' is CORRUPTED (identical center/view_center)")
                        log_error(f"  Center: {center}")
                        log_error(f"  View Center: {view_center}")
                        log_error(f"  Handle: {existing_viewport.dxf.handle}")
                        corrupted_viewports.append(vp_config)
                except Exception as e:
                    log_debug(f"Error checking viewport corruption for {viewport_name}: {e}")

        # Combine missing and corrupted viewports for removal
        all_deletions = missing_viewports + corrupted_viewports

        if not all_deletions:
            return []

        # Handle deletions according to deletion policy
        if self.deletion_policy == 'auto':
            return self._auto_delete_missing_entities(all_deletions)
        elif self.deletion_policy == 'confirm':
            return self._confirm_delete_missing_entities(all_deletions)
        else:
            log_warning(f"Unknown deletion policy '{self.deletion_policy}' - skipping deletions")
            return []

    def _extract_entity_properties(self, entity, base_config):
        """Extract viewport properties from AutoCAD viewport entity."""
        config = {'name': base_config['name']}

        try:
            # Extract physical viewport properties
            center = entity.dxf.center
            config['center'] = {'x': float(center[0]), 'y': float(center[1])}
            config['width'] = float(entity.dxf.width)
            config['height'] = float(entity.dxf.height)

            # Extract view properties
            view_center = entity.dxf.view_center_point
            config['viewCenter'] = {'x': float(view_center[0]), 'y': float(view_center[1])}

            # Calculate scale from view_height and physical height
            view_height = float(entity.dxf.view_height)
            physical_height = float(entity.dxf.height)
            if physical_height > 0:
                scale = view_height / physical_height
                config['scale'] = round(scale, 6)

            # Extract color if it's not default
            if hasattr(entity.dxf, 'color') and entity.dxf.color != 256:  # 256 = BYLAYER
                color_code = entity.dxf.color
                for name, aci in self.name_to_aci.items():
                    if aci == color_code:
                        config['color'] = name
                        break
                else:
                    # If no name found for color code, use the numeric value
                    config['color'] = str(color_code)

            # Extract frozen layers if any
            if hasattr(entity, 'frozen_layers') and entity.frozen_layers:
                config['frozenLayers'] = list(entity.frozen_layers)

            # Extract zoom lock flag
            if hasattr(entity.dxf, 'flags') and (entity.dxf.flags & 16384):  # VSF_LOCK_ZOOM
                config['lockZoom'] = True

            # Extract layer if it's not the default
            if hasattr(entity.dxf, 'layer') and entity.dxf.layer != self.default_layer:
                config['layer'] = entity.dxf.layer

            return config

        except Exception as e:
            log_error(f"Error extracting viewport properties: {str(e)}")
            # Return minimal config on error
            minimal_config = {'name': base_config['name']}
            # Don't add explicit sync settings - let entity inherit global default
            return minimal_config

    def _attach_entity_metadata(self, entity, config):
        """Attach custom metadata to a viewport to mark it as managed by this script."""
        self._attach_viewport_metadata(entity, config)

    def _calculate_entity_hash(self, config):
        """Calculate content hash for a viewport configuration."""
        return calculate_entity_content_hash(config, 'viewport')

    def _find_entity_by_name(self, doc, entity_name):
        """Find a viewport entity by name."""
        return self.get_viewport_by_name(doc, entity_name)

    def _extract_dxf_entity_properties_for_hash(self, entity):
        """
        Extract viewport properties from DXF entity for hash calculation.

        This method extracts all canonical properties, which will then be filtered
        and normalized by the sync schema system for consistent hash calculation.
        """
        if entity is None:
            return {}

        config = {}

        try:
            # Extract physical viewport properties
            if hasattr(entity.dxf, 'center'):
                center = entity.dxf.center
                config['center'] = {'x': float(center[0]), 'y': float(center[1])}

            if hasattr(entity.dxf, 'width'):
                config['width'] = float(entity.dxf.width)
            if hasattr(entity.dxf, 'height'):
                config['height'] = float(entity.dxf.height)

            # Extract view properties
            if hasattr(entity.dxf, 'view_center_point'):
                view_center = entity.dxf.view_center_point
                config['viewCenter'] = {'x': float(view_center[0]), 'y': float(view_center[1])}

            # Calculate scale from view_height and physical height
            if hasattr(entity.dxf, 'view_height') and hasattr(entity.dxf, 'height'):
                view_height = float(entity.dxf.view_height)
                physical_height = float(entity.dxf.height)
                if physical_height > 0:
                    scale = view_height / physical_height
                    config['scale'] = round(scale, 6)

            # Extract color if it's not default
            if hasattr(entity.dxf, 'color') and entity.dxf.color != 256:  # 256 = BYLAYER
                color_code = entity.dxf.color
                for name, aci in self.name_to_aci.items():
                    if aci == color_code:
                        config['color'] = name
                        break
                else:
                    config['color'] = str(color_code)

            # Extract frozen layers if any
            if hasattr(entity, 'frozen_layers') and entity.frozen_layers:
                config['frozenLayers'] = sorted(list(entity.frozen_layers))

            # Extract zoom lock flag
            if hasattr(entity.dxf, 'flags') and (entity.dxf.flags & 16384):  # VSF_LOCK_ZOOM
                config['lockZoom'] = True

            # Extract layer if it's not the default
            if hasattr(entity.dxf, 'layer') and entity.dxf.layer != self.default_layer:
                config['layer'] = entity.dxf.layer

            # Always include the name for hash consistency
            config['name'] = self._get_entity_name_from_xdata(entity)

            return config

        except Exception as e:
            log_error(f"Error extracting viewport properties for hash: {str(e)}")
            return {}

    # Abstract method implementations for centralized discovery
    # ========================================================

    def _get_entity_types(self):
        """Viewport entities: VIEWPORT only."""
        return ['VIEWPORT']

    def _get_discovery_spaces(self, doc):
        """Viewport entities are in all layouts."""
        return list(doc.layouts)

    def _generate_entity_name(self, entity, counter):
        """Generate name based on handle."""
        return f"Viewport_{str(entity.dxf.handle).zfill(3)}"

    def _should_skip_entity(self, entity):
        """Skip main viewport (ID=1) - it's a system viewport, not user-managed."""
        viewport_id = getattr(entity.dxf, 'id', None)
        return viewport_id == 1
