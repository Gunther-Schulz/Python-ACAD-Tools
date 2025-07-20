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
        self.default_layer = project_settings.get('viewport_layer', 'VIEWPORTS')

        log_debug(f"ViewportManager initialized with discovery={self.discovery_enabled}, "
                 f"deletion_policy={self.deletion_policy}, default_layer={self.default_layer}")

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

        # Ensure configured viewport layer exists and set it to not plot
        if self.default_layer not in doc.layers:
            doc.layers.new(self.default_layer)
        viewports_layer = doc.layers.get(self.default_layer)
        viewports_layer.dxf.plot = 0
        log_debug(f"Using viewport layer: {self.default_layer}")

        try:
            # Step 1: Discover existing viewports in AutoCAD if enabled
            discovered_viewports = []
            if self.discovery_enabled:
                discovered_viewports = self._discover_unknown_viewports(paper_space)
                if discovered_viewports:
                    log_info(f"Discovered {len(discovered_viewports)} unknown viewports")

            # Step 2: Process configured viewports according to sync direction
            viewport_configs = self.project_settings.get('viewports', []) or []

            yaml_updated = False
            for vp_config in viewport_configs:
                try:
                    result = self._process_viewport_sync(paper_space, doc, vp_config)
                    if result and result.get('yaml_updated'):
                        yaml_updated = True
                except Exception as e:
                    log_error(f"Error syncing viewport {vp_config.get('name', 'unnamed')}: {str(e)}")
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

            # Step 4: Handle viewport deletions according to deletion policy
            deleted_configs = self._handle_viewport_deletions(paper_space, doc)
            if deleted_configs:
                yaml_updated = True
                log_info(f"Removed {len(deleted_configs)} deleted viewports from configuration")

            # Step 5: Write back YAML if any changes were made
            if yaml_updated and self.project_loader:
                self._write_viewport_yaml()

            return self.viewports

        except Exception as e:
            log_error(f"Error during viewport synchronization: {str(e)}")
            return {}

    def _process_viewport_sync(self, paper_space, doc, vp_config):
        """Process a single viewport according to its sync direction."""
        name = vp_config.get('name', 'unnamed')

        # Determine sync direction
        sync_direction = self._get_sync_direction(vp_config)

        if sync_direction == 'skip':
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
                    if 'layer' in config:
                        updated_config['layer'] = config['layer']

                    viewport_configs[i] = updated_config
                    break

            self.viewports[name] = existing_viewport
            return {'success': True, 'yaml_updated': True}

        except Exception as e:
            log_error(f"Error pulling viewport properties for '{name}': {str(e)}")
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

    def _get_viewport_layer(self, vp_config):
        """Determine the layer for a viewport, supporting per-viewport override."""
        viewport_layer = vp_config.get('layer', self.default_layer)
        return viewport_layer

    def get_viewport_by_name(self, doc, name):
        """Retrieve a viewport by its name using xdata."""
        for layout in doc.layouts:
            for entity in layout:
                if entity.dxftype() == 'VIEWPORT':
                    try:
                        xdata = entity.get_xdata('DXFEXPORTER')
                        if xdata:
                            in_viewport_section = False
                            viewport_name = None

                            for code, value in xdata:
                                if code == 1000 and value == 'VIEWPORT_NAME':
                                    in_viewport_section = True
                                elif in_viewport_section and code == 1000:
                                    viewport_name = value
                                    break

                            if viewport_name == name:
                                return entity
                    except Exception as e:
                        # Only log if there's an actual error (not just missing XDATA)
                        if "DXFEXPORTER" not in str(e):
                            log_debug(f"Error checking viewport {entity.dxf.handle}: {str(e)}")
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
        boundary.dxf.layer = new_viewport.dxf.layer

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

        for layout in paper_space.doc.layouts:
            for entity in layout:
                if entity.dxftype() == 'VIEWPORT':
                    try:
                        # Check if this viewport has our script metadata
                        try:
                            xdata = entity.get_xdata('DXFEXPORTER')
                            has_our_metadata = False
                            if xdata:
                                for code, value in xdata:
                                    if code == 1000 and value == self.script_identifier:
                                        has_our_metadata = True
                                        break
                        except:
                            has_our_metadata = False

                        if has_our_metadata:
                            continue

                        # Skip main viewport (ID=1) - it's a system viewport, not user-managed
                        viewport_id = getattr(entity.dxf, 'id', None)
                        if viewport_id == 1:
                            continue

                        # This is an unknown viewport - generate a name and add it
                        viewport_name = f"Viewport_{str(entity.dxf.handle).zfill(3)}"
                        log_info(f"Discovered manual viewport in layout '{layout.name}', assigned name: {viewport_name}")

                        # Attach metadata to mark it as ours
                        entity.set_xdata(
                            'DXFEXPORTER',
                            [
                                (1000, self.script_identifier),
                                (1002, '{'),
                                (1000, 'VIEWPORT_NAME'),
                                (1000, viewport_name),
                                (1002, '}')
                            ]
                        )

                        discovered.append({
                            'entity': entity,
                            'name': viewport_name,
                            'layout': layout.name
                        })
                        viewport_counter += 1

                    except Exception as e:
                        log_error(f"Error checking viewport metadata: {str(e)}")
                        continue

        # Simple summary
        total_viewports = sum(1 for layout in paper_space.doc.layouts for entity in layout if entity.dxftype() == 'VIEWPORT')
        log_info(f"Discovery completed: Found {len(discovered)} unknown viewports across {len(paper_space.doc.layouts)} layouts")
        log_info(f"  Layout 'Layout1': {total_viewports} total viewports, {len(discovered)} newly discovered")

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

            # Extract layer if it's not the default
            if hasattr(viewport.dxf, 'layer') and viewport.dxf.layer != self.default_layer:
                config['layer'] = viewport.dxf.layer

            return config

        except Exception as e:
            log_error(f"Error extracting viewport properties: {str(e)}")
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
            if 'viewport_layer' in self.project_settings:
                viewport_data['viewport_layer'] = self.project_settings['viewport_layer']

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

    def _handle_viewport_deletions(self, paper_space, doc):
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

            # Only check viewports that aren't set to 'skip' sync
            sync_direction = self._get_sync_direction(vp_config)
            if sync_direction == 'skip':
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
            return self._auto_delete_missing_viewports(all_deletions)
        elif self.deletion_policy == 'confirm':
            return self._confirm_delete_missing_viewports(all_deletions)
        else:
            log_warning(f"Unknown deletion policy '{self.deletion_policy}' - skipping deletions")
            return []

    def _auto_delete_missing_viewports(self, missing_viewports):
        """Automatically delete missing viewports from configuration."""
        log_info(f"Auto-deleting {len(missing_viewports)} missing viewports from configuration")

        viewport_configs = self.project_settings.get('viewports', []) or []
        original_count = len(viewport_configs)

        # Remove missing viewports from configuration
        for missing_vp in missing_viewports:
            viewport_name = missing_vp.get('name')
            viewport_configs = [vp for vp in viewport_configs if vp.get('name') != viewport_name]

        # Update the project settings
        self.project_settings['viewports'] = viewport_configs

        deleted_count = original_count - len(viewport_configs)
        log_info(f"Successfully removed {deleted_count} missing viewports from configuration")
        return missing_viewports

    def _confirm_delete_missing_viewports(self, missing_viewports):
        """Ask user confirmation before deleting missing viewports."""
        viewport_names = [vp.get('name', 'unnamed') for vp in missing_viewports]

        log_warning(f"\nFound {len(missing_viewports)} viewports in YAML that no longer exist in AutoCAD:")
        for name in viewport_names:
            log_warning(f"- {name}")

        # Ask for confirmation
        response = input(f"\nDo you want to remove these {len(missing_viewports)} viewports from the YAML configuration? (y/N): ").lower()
        if response == 'y':
            return self._auto_delete_missing_viewports(missing_viewports)
        else:
            log_info("Viewport deletion cancelled by user")
            return []
