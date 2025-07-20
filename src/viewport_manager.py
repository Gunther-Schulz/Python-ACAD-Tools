import traceback
from ezdxf.lldxf import const
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import get_color_code, attach_custom_data

class ViewportManager:
    def __init__(self, project_settings, script_identifier, name_to_aci, style_manager, project_loader=None):
        self.project_settings = project_settings
        self.script_identifier = script_identifier
        self.name_to_aci = name_to_aci
        self.style_manager = style_manager
        self.project_loader = project_loader
        self.viewports = {}

        # Extract global viewport settings
        self.discovery_enabled = project_settings.get('viewport_discovery', False)
        self.deletion_policy = project_settings.get('viewport_deletion_policy', 'auto')

        log_debug(f"ViewportManager initialized with discovery={self.discovery_enabled}, "
                 f"deletion_policy={self.deletion_policy}")

    def _get_sync_direction(self, vp_config):
        """Determine sync direction for viewport. Only uses sync field - no updateDxf compatibility."""
        # Check for deprecated updateDxf usage
        if 'updateDxf' in vp_config:
            log_warning(f"Viewport '{vp_config.get('name')}' uses deprecated 'updateDxf' flag. "
                       f"Use 'sync: push' instead of 'updateDxf: true' or 'sync: skip' instead of 'updateDxf: false'.")

        # Require sync field for all viewports
        if 'sync' not in vp_config:
            log_warning(f"Viewport '{vp_config.get('name')}' missing required 'sync' field. "
                       f"Valid values are: push, pull, skip. Using 'skip'.")
            return 'skip'

        sync = vp_config['sync']
        if sync in ['push', 'pull', 'skip']:
            return sync
        else:
            log_warning(f"Invalid sync direction '{sync}' for viewport {vp_config.get('name')}. "
                       f"Valid values are: push, pull, skip. Using 'skip'.")
            return 'skip'

    def sync_viewports(self, doc, msp):
        """Enhanced viewport synchronization with bidirectional support."""
        paper_space = doc.paperspace()

        # Ensure VIEWPORTS layer exists and set it to not plot
        if 'VIEWPORTS' not in doc.layers:
            doc.layers.new('VIEWPORTS')
        viewports_layer = doc.layers.get('VIEWPORTS')
        viewports_layer.dxf.plot = 0

        try:
            # Step 1: Discover existing viewports in AutoCAD if enabled
            discovered_viewports = []
            if self.discovery_enabled:
                discovered_viewports = self._discover_unknown_viewports(paper_space)
                if discovered_viewports:
                    log_info(f"Discovered {len(discovered_viewports)} unknown viewports")

            # Step 2: Process configured viewports according to sync direction
            viewport_configs = self.project_settings.get('viewports', []) or []
            log_debug(f"Processing {len(viewport_configs)} configured viewports")

            yaml_updated = False
            for vp_config in viewport_configs:
                try:
                    result = self._process_viewport_sync(paper_space, doc, vp_config)
                    if result and result.get('yaml_updated'):
                        yaml_updated = True
                except Exception as e:
                    log_error(f"Error syncing viewport {vp_config.get('name', 'unnamed')}: {str(e)}")
                    log_error(f"Traceback: {traceback.format_exc()}")
                    continue

            # Step 3: Handle discovered viewports
            if discovered_viewports:
                new_configs = self._process_discovered_viewports(paper_space, discovered_viewports)
                if new_configs:
                    # Add discovered viewports to configuration
                    if self.project_settings.get('viewports') is None:
                        self.project_settings['viewports'] = []
                    self.project_settings['viewports'].extend(new_configs)
                    yaml_updated = True
                    log_info(f"Added {len(new_configs)} discovered viewports to configuration")

            # Step 4: Write back YAML if any changes were made
            if yaml_updated and self.project_loader:
                self._write_viewport_yaml()

            log_debug(f"Completed viewport synchronization. Processed {len(self.viewports)} viewports")
            return self.viewports

        except Exception as e:
            log_error(f"Error during viewport synchronization: {str(e)}")
            log_error(f"Traceback: {traceback.format_exc()}")
            return {}

    def _process_viewport_sync(self, paper_space, doc, vp_config):
        """Process a single viewport according to its sync direction."""
        name = vp_config.get('name', 'unnamed')

        # Determine sync direction
        sync_direction = self._get_sync_direction(vp_config)

        if sync_direction == 'skip':
            log_debug(f"Skipping viewport {name} - sync direction is 'skip'")
            return None

        # Get existing viewport if it exists
        existing_viewport = self.get_viewport_by_name(paper_space.doc, name)

        if sync_direction == 'push':
            # YAML → AutoCAD: Create/update viewport from YAML config
            return self._sync_push(paper_space, doc, vp_config, existing_viewport)
        elif sync_direction == 'pull':
            # AutoCAD → YAML: Update YAML config from AutoCAD viewport
            return self._sync_pull(paper_space, doc, vp_config, existing_viewport)
        else:
            log_warning(f"Unknown sync direction '{sync_direction}' for viewport {name}")
            return None

    def _sync_push(self, paper_space, doc, vp_config, existing_viewport):
        """Sync YAML → AutoCAD (create/update viewport from config)."""
        name = vp_config.get('name', 'unnamed')

        # Use existing create/update logic
        viewport = self._create_or_get_viewport(paper_space, vp_config)
        if viewport is None:
            log_warning(f"Failed to create or get viewport: {name}")
            return None

        self._update_viewport_properties(viewport, vp_config)
        self._update_viewport_layers(doc, viewport, vp_config)
        self._attach_viewport_metadata(viewport, vp_config)
        self.viewports[name] = viewport
        log_debug(f"Pushed viewport config to AutoCAD: {name}")
        return {'success': True}

    def _sync_pull(self, paper_space, doc, vp_config, existing_viewport):
        """Sync AutoCAD → YAML (update config from AutoCAD viewport)."""
        name = vp_config.get('name', 'unnamed')

        if existing_viewport is None:
            log_warning(f"Cannot pull viewport '{name}' - not found in AutoCAD")
            return None

        # Extract properties from AutoCAD viewport
        try:
            updated_config = self._extract_viewport_properties(existing_viewport, vp_config)

            # Update the configuration in project_settings
            viewport_configs = self.project_settings.get('viewports', []) or []
            for i, config in enumerate(viewport_configs):
                if config.get('name') == name:
                    # Preserve sync direction and other non-geometric properties
                    updated_config['sync'] = 'pull'
                    if 'frozenLayers' in config:
                        updated_config['frozenLayers'] = config['frozenLayers']
                    if 'visibleLayers' in config:
                        updated_config['visibleLayers'] = config['visibleLayers']
                    if 'lockZoom' in config:
                        updated_config['lockZoom'] = config['lockZoom']
                    if 'color' in config:
                        updated_config['color'] = config['color']

                    viewport_configs[i] = updated_config
                    break

            self.viewports[name] = existing_viewport
            log_debug(f"Pulled viewport properties from AutoCAD: {name}")
            return {'success': True, 'yaml_updated': True}

        except Exception as e:
            log_error(f"Error pulling viewport properties for '{name}': {str(e)}")
            log_error(f"Traceback: {traceback.format_exc()}")
            return None

    # DEPRECATED: Use sync_viewports instead
    def create_viewports(self, doc, msp):
        """DEPRECATED: Use sync_viewports() instead. Viewports now use sync modes (push/pull/skip) only."""
        log_warning("create_viewports() is deprecated. Use sync_viewports() with 'sync' field instead of 'updateDxf'.")
        return self.sync_viewports(doc, msp)

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

    def _discover_unknown_viewports(self, paper_space):
        """Discover viewports in AutoCAD that aren't managed by this script."""
        discovered = []
        viewport_counter = 1

        log_debug(f"Starting viewport discovery in document with {len(paper_space.doc.layouts)} layouts")

        for layout in paper_space.doc.layouts:
            log_debug(f"Checking layout: {layout.name}")
            entity_count = 0
            viewport_count = 0

            for entity in layout:
                entity_count += 1
                if entity.dxftype() == 'VIEWPORT':
                    viewport_count += 1
                    log_debug(f"Found VIEWPORT entity in layout {layout.name}")

                    # Check if this viewport has our script metadata
                    try:
                        try:
                            xdata = entity.get_xdata('DXFEXPORTER')
                            has_our_metadata = False
                            if xdata:
                                log_debug(f"Viewport has xdata: {xdata}")
                                for code, value in xdata:
                                    if code == 1000 and value == self.script_identifier:
                                        has_our_metadata = True
                                        log_debug(f"Viewport has our script identifier: {self.script_identifier}")
                                        break
                            else:
                                log_debug("Viewport has no xdata - this is a manual viewport")
                        except:
                            # get_xdata throws exception if appid doesn't exist - this is a manual viewport
                            log_debug("Viewport has no DXFEXPORTER xdata - this is a manual viewport")
                            has_our_metadata = False

                        if not has_our_metadata:
                            # This is an unknown viewport - add it to discovery list
                            viewport_name = f"Viewport_{viewport_counter:03d}"
                            while self._viewport_name_exists(viewport_name):
                                viewport_counter += 1
                                viewport_name = f"Viewport_{viewport_counter:03d}"

                            # Set hyperlink for easy identification in AutoCAD
                            entity.set_hyperlink(viewport_name)

                            discovered.append({
                                'entity': entity,
                                'name': viewport_name,
                                'layout': layout.name
                            })
                            log_info(f"Discovered manual viewport in layout {layout.name}, assigned name: {viewport_name}")
                            viewport_counter += 1

                    except Exception as e:
                        log_error(f"Error checking viewport metadata: {str(e)}")
                        log_error(f"Traceback: {traceback.format_exc()}")
                        continue

            log_debug(f"Layout {layout.name}: {entity_count} total entities, {viewport_count} viewports")

        log_info(f"Discovery completed: Found {len(discovered)} unknown viewports")
        return discovered

    def _viewport_name_exists(self, name):
        """Check if a viewport name already exists in the configuration."""
        viewport_configs = self.project_settings.get('viewports', []) or []
        for config in viewport_configs:
            if config.get('name') == name:
                return True
        return False

    def _process_discovered_viewports(self, paper_space, discovered_viewports):
        """Process discovered viewports and create YAML configurations for them."""
        new_configs = []

        for discovered in discovered_viewports:
            try:
                entity = discovered['entity']
                name = discovered['name']

                # Extract properties and create configuration
                config = self._extract_viewport_properties(entity, {'name': name})
                config['sync'] = 'pull'  # Default discovered viewports to pull mode

                # Add our metadata to the discovered viewport
                self._attach_viewport_metadata(entity, config)

                new_configs.append(config)
                log_debug(f"Created configuration for discovered viewport: {name}")

            except Exception as e:
                log_warning(f"Failed to process discovered viewport {discovered['name']}: {str(e)}")
                continue

        return new_configs

    def _extract_viewport_properties(self, viewport, base_config):
        """Extract viewport properties from AutoCAD viewport entity."""
        config = {'name': base_config['name']}

        try:
            # Extract physical viewport properties
            center = viewport.dxf.center
            config['center'] = {'x': float(center[0]), 'y': float(center[1])}
            config['width'] = float(viewport.dxf.width)
            config['height'] = float(viewport.dxf.height)

            # Extract view properties
            view_center = viewport.dxf.view_center_point
            config['viewCenter'] = {'x': float(view_center[0]), 'y': float(view_center[1])}

            # Calculate scale from view_height and physical height
            view_height = float(viewport.dxf.view_height)
            physical_height = float(viewport.dxf.height)
            if physical_height > 0:
                scale = view_height / physical_height
                config['scale'] = round(scale, 6)

            # Extract color if it's not default
            if hasattr(viewport.dxf, 'color') and viewport.dxf.color != 256:  # 256 = BYLAYER
                # Try to map ACI code back to color name
                color_code = viewport.dxf.color
                for name, aci in self.name_to_aci.items():
                    if aci == color_code:
                        config['color'] = name
                        break
                else:
                    config['color'] = str(color_code)

            # Extract frozen layers if any
            if hasattr(viewport, 'frozen_layers') and viewport.frozen_layers:
                config['frozenLayers'] = list(viewport.frozen_layers)

            # Extract zoom lock flag
            if hasattr(viewport.dxf, 'flags') and (viewport.dxf.flags & 16384):  # VSF_LOCK_ZOOM
                config['lockZoom'] = True

            log_debug(f"Extracted properties for viewport: {config['name']}")
            return config

        except Exception as e:
            log_error(f"Error extracting viewport properties: {str(e)}")
            log_error(f"Traceback: {traceback.format_exc()}")
            # Return minimal config on error
            return {'name': base_config['name'], 'sync': 'pull'}

    def _write_viewport_yaml(self):
        """Write updated viewport configuration back to YAML file."""
        if not self.project_loader:
            log_warning("Cannot write viewport YAML - no project_loader available")
            return False

        try:
            # Prepare viewport data structure
            viewport_data = {
                'viewports': self.project_settings.get('viewports', [])
            }

            # Add global viewport settings if they exist
            if 'viewport_discovery' in self.project_settings:
                viewport_data['viewport_discovery'] = self.project_settings['viewport_discovery']
            if 'viewport_deletion_policy' in self.project_settings:
                viewport_data['viewport_deletion_policy'] = self.project_settings['viewport_deletion_policy']

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
