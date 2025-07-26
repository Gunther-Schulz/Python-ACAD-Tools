import traceback
from ezdxf.lldxf import const
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import get_color_code, attach_custom_data, XDATA_APP_ID, find_entity_by_xdata_name
from src.unified_sync_processor import UnifiedSyncProcessor
from src.sync_hash_utils import calculate_entity_content_hash, clean_entity_config_for_yaml_output

class ViewportManager(UnifiedSyncProcessor):
    def __init__(self, project_settings, script_identifier, name_to_aci, style_manager, project_loader=None):
        # Initialize base class
        super().__init__(project_settings, script_identifier, 'viewport', project_loader)

        # Viewport-specific dependencies
        self.name_to_aci = name_to_aci
        self.style_manager = style_manager
        self.viewports = {}

        log_debug(f"ViewportManager initialized with discovery={self._is_discovery_enabled()}, "
                 f"deletion_policy={self.deletion_policy}, default_layer={self.default_layer}, "
                 f"default_sync={self.default_sync}")

    def _get_entity_configs(self):
        """Get viewport configurations from project settings."""
        return self.project_settings.get(self._get_config_key(), []) or []

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

    # _write_entity_yaml is now implemented in UnifiedSyncProcessor

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
        self._attach_entity_metadata(viewport, config)  # Use centralized method
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
            # Extract ONLY the changeable properties from AutoCAD viewport
            extracted_props = self._extract_entity_properties(existing_viewport, config)

            if not extracted_props:
                log_warning(f"No properties extracted from viewport '{name}' - keeping original config")
                return None

            # Update the configuration in project_settings with intelligent merging
            viewport_configs = self.project_settings.get('viewports', []) or []
            for i, original_config in enumerate(viewport_configs):
                if original_config.get('name') == name:
                    # Start with complete original config to preserve ALL metadata
                    updated_config = original_config.copy()

                    # Update only the extracted properties (changeable from DXF)
                    updated_config.update(extracted_props)

                    # Replace the config in the list
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

        try:
            viewport = paper_space.add_viewport(
                center=(center_x, center_y),
                size=(width, height),
                view_center_point=view_center_point,
                view_height=view_height
            )

            viewport.dxf.status = 1
            viewport.dxf.layer = viewport_layer

            return viewport
        except Exception as e:
            log_error(f"Error creating viewport: {str(e)}")
            return None

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
        return self._resolve_entity_layer(vp_config)

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
        self._attach_entity_metadata(new_viewport, vp_config)

        return new_viewport

    def _discover_unknown_entities(self, doc, space):
        """Discover viewports in AutoCAD that aren't managed by this script."""
        # Use centralized discovery logic from UnifiedSyncProcessor
        discovered = super()._discover_unknown_entities(doc, space)

        # ViewportManager doesn't need additional entity-specific behavior
        # Base implementation handles all the discovery logic
        return discovered

    def _find_all_entities_with_xdata_name(self, doc, entity_name):
        """Find all viewports with matching XDATA name. Viewport-specific implementation."""
        paper_space = doc.paperspace()
        matching_entities = []
        from src.dxf_utils import XDATA_APP_ID

        for viewport in paper_space.query('VIEWPORT'):
            # Skip entities based on manager-specific skip logic
            if self._should_skip_entity(viewport):
                continue

            # Check if this viewport has our XDATA with matching name
            try:
                xdata_name = self._get_entity_name_from_xdata(viewport)
                if xdata_name == entity_name:
                    matching_entities.append(viewport)
            except:
                continue

        return matching_entities



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
        """
        Extract only the changeable properties from AutoCAD viewport entity.

        This is a PURE extraction function that only extracts DXF properties
        without touching metadata or other preserved fields.
        """
        # CRITICAL: Always include the name from base_config
        extracted_props = {'name': base_config['name']}

        try:
            # Extract physical viewport properties
            center = entity.dxf.center
            extracted_props['center'] = {'x': float(center[0]), 'y': float(center[1])}
            extracted_props['width'] = float(entity.dxf.width)
            extracted_props['height'] = float(entity.dxf.height)

            # Extract view properties
            view_center = entity.dxf.view_center_point
            extracted_props['viewCenter'] = {'x': float(view_center[0]), 'y': float(view_center[1])}

            # Calculate scale from view_height and physical height
            view_height = float(entity.dxf.view_height)
            physical_height = float(entity.dxf.height)
            if physical_height > 0:
                scale = view_height / physical_height
                extracted_props['scale'] = round(scale, 6)

            # Extract color if it's not default
            if hasattr(entity.dxf, 'color') and entity.dxf.color != 256:  # 256 = BYLAYER
                color_code = entity.dxf.color
                for name, aci in self.name_to_aci.items():
                    if aci == color_code:
                        extracted_props['color'] = name
                        break
                else:
                    # If no name found for color code, use the numeric value
                    extracted_props['color'] = str(color_code)

            # Extract frozen layers if any
            if hasattr(entity, 'frozen_layers') and entity.frozen_layers:
                extracted_props['frozenLayers'] = list(entity.frozen_layers)

            # Extract zoom lock flag
            if hasattr(entity.dxf, 'flags') and (entity.dxf.flags & 16384):  # VSF_LOCK_ZOOM
                extracted_props['lockZoom'] = True

            # Extract layer if it's not the default
            if hasattr(entity.dxf, 'layer') and entity.dxf.layer != self.default_layer:
                extracted_props['layer'] = entity.dxf.layer

            return extracted_props

        except Exception as e:
            log_error(f"Error extracting viewport properties: {str(e)}")
            return {}  # Return empty dict on error - let merge handle it

    def _attach_entity_metadata(self, entity, config):
        """Attach custom metadata to a viewport to mark it as managed by this script."""
        entity_name = config.get('name', 'unnamed')
        content_hash = self._calculate_entity_hash(config)
        entity_handle = str(entity.dxf.handle)

        from src.dxf_utils import attach_custom_data
        attach_custom_data(
            entity,
            self.script_identifier,
            entity_name=entity_name,
            entity_type=self.entity_type.upper(),
            content_hash=content_hash,
            entity_handle=entity_handle
        )

        # Store handle in config for tracking
        if '_sync' not in config:
            config['_sync'] = {}
        config['_sync']['dxf_handle'] = entity_handle



    def _find_entity_by_name(self, doc, entity_name):
        """Find a viewport entity by name."""
        return self.get_viewport_by_name(doc, entity_name)

    def _find_entity_by_name_ignoring_handle_validation(self, doc, entity_name):
        """Find a viewport entity by name without handle validation for recovery purposes."""
        for layout in doc.layouts:
            viewport = find_entity_by_xdata_name(layout, entity_name, ['VIEWPORT'])
            if viewport:
                # Return entity without handle validation for recovery
                return viewport
        return None

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

    def _get_target_space(self, doc, config):
        """
        Get the target space for viewport entities.

        Override base class behavior because viewports are ALWAYS in paperspace,
        regardless of the 'paperspace' setting in the YAML config.

        Args:
            doc: DXF document
            config: Entity configuration dictionary (ignored for viewports)

        Returns:
            Space object - always returns paperspace for viewports
        """
        return doc.paperspace()  # Viewports are always in paperspace

    def _get_entity_types(self):
        """Viewport entities: VIEWPORT only."""
        return ['VIEWPORT']

    def _get_discovery_spaces(self, doc):
        """Viewport entities are always in paperspace - no need to search all layouts."""
        return [doc.paperspace()]

    def _generate_entity_name(self, entity, counter):
        """Generate name based on handle."""
        return f"Viewport_{str(entity.dxf.handle).zfill(3)}"

    def _should_skip_entity(self, entity):
        """Skip main viewport (ID=1) - it's a system viewport, not user-managed."""
        viewport_id = getattr(entity.dxf, 'id', None)
        return viewport_id == 1

    def _get_entity_types_for_search(self):
        """Get DXF entity types for viewport search."""
        return ['VIEWPORT']



    def _write_entity_yaml(self):
        """Write viewport configurations back to YAML file."""
        # Use the implementation from parent class
        return super()._write_entity_yaml()

    # Abstract methods required by UnifiedSyncProcessor
    def _get_fallback_default_layer(self):
        """Get fallback default layer name for viewport entities."""
        fallbacks = {
            'viewport': 'VIEWPORTS',
            'text': 'Plantext',
            'block': 'BLOCKS'
        }
        return fallbacks.get(self.entity_type, 'DEFAULT_LAYER')

    def _resolve_entity_layer(self, config):
        """
        Resolve the layer for a viewport entity using unified layer logic.

        Args:
            config: Viewport entity configuration dictionary

        Returns:
            str: Layer name to use for this viewport entity
        """
        # Check for individual layer override first
        entity_layer = config.get('layer')
        if entity_layer:
            return entity_layer

        # Fall back to global default layer
        return self.default_layer

    def _calculate_entity_hash(self, config):
        """
        Calculate content hash for viewport entity configuration.
        Centralized implementation that works for all entity types.

        Args:
            config: Viewport entity configuration dictionary

        Returns:
            str: Content hash for the configuration
        """
        try:
            from src.sync_hash_utils import calculate_entity_content_hash
            return calculate_entity_content_hash(config, self.entity_type)
        except Exception as e:
            log_warning(f"Error calculating hash for {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
            return "error_hash"
