import traceback
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_mtext, remove_entities_by_layer, XDATA_APP_ID, attach_custom_data, find_entity_by_xdata_name, detect_entity_paperspace
from src.unified_sync_processor import UnifiedSyncProcessor
from src.sync_hash_utils import clean_entity_config_for_yaml_output


class TextInsertManager(UnifiedSyncProcessor):
    """Manager for text insert synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_settings, script_identifier, style_manager, name_to_aci, project_loader=None):
        # Initialize base class (use 'text' as entity_type to match project_loader key 'text_sync')
        super().__init__(project_settings, script_identifier, 'text', project_loader)

        # Text insert specific dependencies
        self.style_manager = style_manager
        self.name_to_aci = name_to_aci

    def _get_entity_configs(self):
        """Get text insert configurations from project settings."""
        return self.project_settings.get(self._get_config_key(), []) or []

    def _sync_push(self, doc, space, config):
        """Create or update text insert in AutoCAD from YAML configuration."""
        name = config.get('name', 'unnamed')

        try:
            # Get target layer and ensure it exists (centralized)
            layer_name = self._ensure_entity_layer_exists(doc, config)

            # Get text properties
            text = config.get('text', '')
            position = config.get('position', {})

            # Handle different position types
            if position.get('type') == 'absolute':
                x = position.get('x', 0)
                y = position.get('y', 0)
            else:
                log_warning(f"Unsupported position type '{position.get('type')}' for text insert '{name}'. Using (0,0).")
                x, y = 0, 0

            # Get style configuration
            style_name = config.get('style')
            text_style = {}
            if style_name:
                style, warning_generated = self.style_manager.get_style(style_name)
                if not warning_generated and style and 'text' in style:
                    text_style = style['text']

            # Get the correct space (model or paper) - centralized
            target_space = self._get_target_space(doc, config)

            # Create MTEXT entity
            result = add_mtext(
                target_space,
                text,
                x,
                y,
                layer_name,
                text_style.get('font', 'Standard'),
                text_style=text_style,
                name_to_aci=self.name_to_aci,
                max_width=text_style.get('width')
            )

            if result and result[0]:
                mtext = result[0]

                # Set hyperlink to text name (explicit call like viewport manager)
                try:
                    mtext.set_hyperlink(name)
                    log_debug(f"Set hyperlink '{name}' for text insert")
                except Exception as e:
                    log_warning(f"Failed to set hyperlink for text insert '{name}': {str(e)}")

                # Attach custom data to identify this as our entity using consistent format
                self._attach_entity_metadata(mtext, config)
                log_debug(f"Added text insert '{name}': '{text}' at ({x}, {y})")
                return mtext
            else:
                log_warning(f"Failed to create text insert '{name}'")
                return None

        except Exception as e:
            log_error(f"Error creating text insert '{name}': {str(e)}")
            return None

    def _sync_pull(self, doc, space, config):
        """Extract text insert properties from AutoCAD and update YAML configuration."""
        name = config.get('name', 'unnamed')

        # Find existing text entity in AutoCAD
        existing_text = self._find_text_by_name(doc, name)
        if existing_text is None:
            log_warning(f"Cannot pull text insert '{name}' - not found in AutoCAD")
            return None

        try:
            # Extract ONLY the changeable properties from AutoCAD text entity
            extracted_props = self._extract_text_properties(existing_text, config)

            if not extracted_props:
                log_warning(f"No properties extracted from text '{name}' - keeping original config")
                return None

            # Update the configuration in project_settings with intelligent merging
            text_configs = self._get_entity_configs()
            for i, original_config in enumerate(text_configs):
                if original_config.get('name') == name:
                    # Start with complete original config to preserve ALL metadata
                    updated_config = original_config.copy()

                    # Update only the extracted properties (changeable from DXF)
                    updated_config.update(extracted_props)

                    # Replace the config in the list
                    text_configs[i] = updated_config
                    break

            return {'entity': existing_text, 'yaml_updated': True}

        except Exception as e:
            log_error(f"Error pulling text insert properties for '{name}': {str(e)}")
            return None

    def _find_text_by_name(self, doc, name):
        """Find a text entity by name using custom data."""
        # Search modelspace first (where most text entities are), then paperspace
        spaces = [doc.modelspace(), doc.paperspace()]

        for space in spaces:
            entity = find_entity_by_xdata_name(space, name, ['TEXT', 'MTEXT'])
            if entity and self._validate_entity_handle(entity, name):
                return entity

        return None

    def _find_entity_by_name_ignoring_handle_validation(self, doc, entity_name):
        """Find a text entity by name without handle validation for recovery purposes."""
        # Search modelspace first (where most text entities are), then paperspace
        spaces = [doc.modelspace(), doc.paperspace()]

        for space in spaces:
            entity = find_entity_by_xdata_name(space, entity_name, ['TEXT', 'MTEXT'])
            if entity:
                # Return entity without handle validation for recovery
                return entity

        return None

    def _extract_text_properties(self, text_entity, base_config):
        """
        Extract only the changeable properties from AutoCAD text entity.

        This is a PURE extraction function that only extracts DXF properties
        without touching metadata or other preserved fields.
        """
        extracted_props = {}

        try:
            # Extract position
            insert_point = text_entity.dxf.insert
            extracted_props['position'] = {
                'type': 'absolute',
                'x': float(insert_point[0]),
                'y': float(insert_point[1])
            }

            # Extract text content using ezdxf's built-in method
            if text_entity.dxftype() == 'MTEXT':
                # Use ezdxf's plain_text() method to properly handle MTEXT formatting codes
                plain_text = text_entity.plain_text()
                # Convert actual newlines back to literal \n for YAML consistency
                extracted_props['text'] = plain_text.replace('\n', '\\n')
            else:  # TEXT entity
                extracted_props['text'] = text_entity.dxf.text

            # Extract layer
            extracted_props['layer'] = text_entity.dxf.layer

            # Determine paperspace using shared reliable detection function
            paperspace = detect_entity_paperspace(text_entity)
            if paperspace is not None:
                extracted_props['paperspace'] = paperspace
            # If detection failed, don't include paperspace to preserve original value

            return extracted_props

        except Exception as e:
            log_error(f"Error extracting text properties: {str(e)}")
            return {}  # Return empty dict on error - let merge handle it

    # _write_entity_yaml is now implemented in UnifiedSyncProcessor

    def clean_target_layers(self, doc, configs_to_process):
        """Clean target layers for text configs (both spaces, prioritizing modelspace)."""
        target_layers = set()
        for config in configs_to_process:
            sync_direction = self._get_sync_direction(config)
            if sync_direction == 'push':
                layer_name = self._resolve_entity_layer(config)
                target_layers.add(layer_name)

        # Text entities can be in both spaces - clean both with modelspace priority
        for layer_name in target_layers:
            spaces = [doc.modelspace(), doc.paperspace()]
            for space in spaces:
                log_debug(f"Cleaning text entities from layer: {layer_name} in {space}")
                remove_entities_by_layer(space, layer_name, self.script_identifier)

    def _discover_unknown_entities(self, doc, space):
        """Discover text entities in AutoCAD that aren't managed by this script."""
        # Use centralized discovery logic from UnifiedSyncProcessor
        discovered = super()._discover_unknown_entities(doc, space)

        # Add hyperlinks for discovered text entities (text-specific behavior)
        for discovery in discovered:
            entity = discovery['entity']
            entity_name = discovery['name']
            try:
                entity.set_hyperlink(entity_name)
                log_debug(f"Set hyperlink '{entity_name}' for discovered text entity")
            except Exception as e:
                log_warning(f"Failed to set hyperlink for discovered text '{entity_name}': {str(e)}")

        return discovered

    def _handle_entity_deletions(self, doc, space):
        """Handle deletion of text inserts that exist in YAML but not in AutoCAD."""
        if self.deletion_policy == 'ignore':
            return []

        text_configs = self._get_entity_configs()
        missing_texts = []

        # Check each configured text to see if it still exists in AutoCAD
        for text_config in text_configs:
            text_name = text_config.get('name')
            if not text_name:
                continue

            # Only check texts that are in 'pull' mode
            # In pull mode, AutoCAD is the source of truth, so missing texts should be removed from YAML
            # In push mode, YAML is the source of truth, so missing texts should be created in AutoCAD
            sync_direction = self._get_sync_direction(text_config)
            if sync_direction != 'pull':
                continue

            # Check if text exists in AutoCAD
            existing_text = self._get_text_by_name(doc, text_name)
            if existing_text is None:
                missing_texts.append(text_config)
                log_info(f"Text '{text_name}' configured in YAML but not found in AutoCAD")

        if not missing_texts:
            return []

        # Handle deletions according to deletion policy
        if self.deletion_policy == 'auto':
            return self._auto_delete_missing_entities(missing_texts)
        elif self.deletion_policy == 'confirm':
            return self._confirm_delete_missing_entities(missing_texts)
        else:
            log_warning(f"Unknown deletion policy '{self.deletion_policy}' - skipping deletions")
            return []

    def _extract_entity_properties(self, entity, base_config):
        """Extract text properties from AutoCAD text entity."""
        config = {'name': base_config['name']}

        try:
            # Extract text content using ezdxf's built-in method
            if entity.dxftype() == 'MTEXT':
                # Use ezdxf's plain_text() method to properly handle MTEXT formatting codes
                plain_text = entity.plain_text()
                # Convert actual newlines back to literal \n for YAML consistency
                config['text'] = plain_text.replace('\n', '\\n')
            else:  # TEXT entity
                config['text'] = entity.dxf.text

            # Extract position
            if hasattr(entity.dxf, 'insert'):
                insert_point = entity.dxf.insert
                config['x'] = float(insert_point[0])
                config['y'] = float(insert_point[1])
            elif hasattr(entity.dxf, 'location'):
                location = entity.dxf.location
                config['x'] = float(location[0])
                config['y'] = float(location[1])

            # Extract layer
            if hasattr(entity.dxf, 'layer'):
                config['layer'] = entity.dxf.layer

            # Extract text height
            if hasattr(entity.dxf, 'height'):
                config['height'] = float(entity.dxf.height)

            # Extract color if it's not default
            if hasattr(entity.dxf, 'color') and entity.dxf.color != 256:  # 256 = BYLAYER
                color_code = entity.dxf.color
                for name, aci in self.name_to_aci.items():
                    if aci == color_code:
                        config['color'] = name
                        break
                else:
                    config['color'] = str(color_code)

            # Extract text style if available
            if hasattr(entity.dxf, 'style') and entity.dxf.style != 'Standard':
                config['style'] = entity.dxf.style

            # Extract rotation if not zero
            if hasattr(entity.dxf, 'rotation') and entity.dxf.rotation != 0:
                config['rotation'] = float(entity.dxf.rotation)

            return config

        except Exception as e:
            log_error(f"Error extracting text properties: {str(e)}")
            # Return minimal config on error
            minimal_config = {'name': base_config['name'], 'text': 'ERROR_EXTRACTING_TEXT'}
            # Don't add explicit sync settings - let entity inherit global default
            return minimal_config

    # _attach_entity_metadata and _calculate_entity_hash are now implemented in UnifiedSyncProcessor

    def _find_entity_by_name(self, doc, entity_name):
        """Find a text entity by name."""
        return self._find_text_by_name(doc, entity_name)

    def _find_entity_by_name_ignoring_handle_validation(self, doc, entity_name):
        """Find a text entity by name without handle validation for recovery purposes."""
        # Search modelspace first (where most text entities are), then paperspace
        spaces = [doc.modelspace(), doc.paperspace()]

        for space in spaces:
            entity = find_entity_by_xdata_name(space, entity_name, ['TEXT', 'MTEXT'])
            if entity:
                # Return entity without handle validation for recovery
                return entity

        return None

    def _extract_dxf_entity_properties_for_hash(self, entity):
        """
        Extract text properties from DXF entity for hash calculation.

        This method extracts ALL available properties, which will then be filtered
        to canonical properties by the sync schema system.
        """
        if entity is None:
            log_debug("DXF entity is None for hash extraction")
            return {}

        config = {}

        try:
            # Always include the name for hash consistency
            config['name'] = self._get_entity_name_from_xdata(entity)
            log_debug(f"Extracted name from XDATA: {config['name']}")

            # Extract text content using ezdxf's built-in method
            log_debug(f"DXF entity type: {entity.dxftype()}")
            if entity.dxftype() == 'MTEXT':
                # Use ezdxf's plain_text() method to properly handle MTEXT formatting codes
                try:
                    plain_text = entity.plain_text()
                    log_debug(f"MTEXT plain_text() result: '{plain_text[:50]}...' (length: {len(plain_text)})")
                    # Convert actual newlines back to literal \n for YAML consistency
                    config['text'] = plain_text.replace('\n', '\\n')
                    log_debug(f"Processed text for hash: '{config['text'][:50]}...'")
                except Exception as e:
                    log_error(f"Error extracting MTEXT plain_text: {str(e)}")
                    # Fallback to raw text attribute
                    if hasattr(entity.dxf, 'text'):
                        config['text'] = entity.dxf.text
                        log_debug(f"Fallback to dxf.text: '{config['text'][:50]}...'")
            else:  # TEXT entity
                if hasattr(entity.dxf, 'text'):
                    config['text'] = entity.dxf.text
                    log_debug(f"TEXT entity text: '{config['text'][:50]}...'")
                else:
                    log_warning(f"TEXT entity has no text attribute!")

            # Extract position
            position = {}
            if hasattr(entity.dxf, 'insert'):
                insert_point = entity.dxf.insert
                position['x'] = float(insert_point[0])
                position['y'] = float(insert_point[1])
                position['type'] = 'absolute'
                log_debug(f"Extracted insert position: {position}")
            elif hasattr(entity.dxf, 'location'):
                location = entity.dxf.location
                position['x'] = float(location[0])
                position['y'] = float(location[1])
                position['type'] = 'absolute'
                log_debug(f"Extracted location position: {position}")

            if position:
                config['position'] = position

            # Extract layer
            if hasattr(entity.dxf, 'layer'):
                config['layer'] = entity.dxf.layer
                log_debug(f"Extracted layer: {config['layer']}")

            # Extract text style if available
            if hasattr(entity.dxf, 'style') and entity.dxf.style != 'Standard':
                config['style'] = entity.dxf.style
                log_debug(f"Extracted style: {config['style']}")

            # Extract justification if available
            if hasattr(entity.dxf, 'attach_point'):
                # Map MTEXT attachment points to justification names
                attach_point_map = {
                    1: 'TOP_LEFT', 2: 'TOP_CENTER', 3: 'TOP_RIGHT',
                    4: 'MIDDLE_LEFT', 5: 'MIDDLE_CENTER', 6: 'MIDDLE_RIGHT',
                    7: 'BOTTOM_LEFT', 8: 'BOTTOM_CENTER', 9: 'BOTTOM_RIGHT'
                }
                if entity.dxf.attach_point in attach_point_map:
                    config['justification'] = attach_point_map[entity.dxf.attach_point]
                    log_debug(f"Extracted justification: {config['justification']}")

            # Extract paperspace flag using shared reliable detection
            paperspace = detect_entity_paperspace(entity)
            if paperspace is not None:
                config['paperspace'] = paperspace
                log_debug(f"Extracted paperspace: {config['paperspace']}")
            else:
                config['paperspace'] = False  # Fallback for hash consistency

            # The following properties are intentionally NOT included in canonical properties:
            # - height: DXF implementation detail, varies by style
            # - color: DXF implementation detail, should use style
            # - rotation: Not part of core content (positioning detail)

            # Note: The sync schema system will filter this down to only canonical properties

            log_debug(f"Final extracted properties for hash: {list(config.keys())}")
            return config

        except Exception as e:
            log_error(f"Error extracting text properties for hash: {str(e)}")
            return {}



    def _get_text_by_name(self, doc, name):
        """Retrieve a text entity by its name using xdata."""
        # Search modelspace first (where most text entities are), then paperspace
        spaces = [doc.modelspace(), doc.paperspace()]

        for space in spaces:
            entity = find_entity_by_xdata_name(space, name, ['TEXT', 'MTEXT'])
            if entity:
                return entity

        return None

    def _find_all_entities_with_xdata_name(self, doc, entity_name):
        """Find all text entities with matching XDATA name. Text-specific implementation."""
        matching_entities = []
        from src.dxf_utils import XDATA_APP_ID

        # Search in both model space and all paper spaces
        spaces_to_search = [doc.modelspace()]
        spaces_to_search.extend(layout for layout in doc.layouts if layout.name != 'Model')

        for space in spaces_to_search:
            for text_entity in space.query('TEXT MTEXT'):
                # Skip entities based on manager-specific skip logic
                if self._should_skip_entity(text_entity):
                    continue

                # Check if this text entity has our XDATA with matching name
                try:
                    xdata_name = self._get_entity_name_from_xdata(text_entity)
                    if xdata_name == entity_name:
                        matching_entities.append(text_entity)
                except:
                    continue

        return matching_entities

    # Abstract method implementations for centralized discovery
    # ========================================================

    def _get_entity_types(self):
        """Text entities: TEXT and MTEXT."""
        return ['TEXT', 'MTEXT']

    def _get_discovery_spaces(self, doc):
        """Text entities can be in both spaces - prioritize modelspace for efficiency since most text is in modelspace."""
        return [doc.modelspace(), doc.paperspace()]

    def _generate_entity_name(self, entity, counter):
        """Generate name based on text content or handle."""
        # Generate a name based on text content or position
        text_content = getattr(entity.dxf, 'text', '') or getattr(entity, 'text', '')
        if text_content:
            # Use first few words of text content for name
            clean_text = text_content.replace('\n', ' ').replace('\r', ' ').strip()
            words = clean_text.split()[:3]  # First 3 words
            if words:
                text_name = f"Text_{'_'.join(words)}"
                # Clean invalid characters
                text_name = ''.join(c for c in text_name if c.isalnum() or c in '_-')
                return text_name

        # Fallback to handle-based name
        return f"Text_{str(entity.dxf.handle).zfill(3)}"



    def _get_entity_types_for_search(self):
        """Get DXF entity types for text search."""
        return ['TEXT', 'MTEXT']



    def _process_text_config_line(self, config, line_number):
        """Process a single text configuration line for SkipSync functionality."""
        entity_name = config.get('name', f'text_line_{line_number}')
        log_debug(f"Processing text config line {line_number}: {entity_name}")
        return True

    # Abstract methods required by UnifiedSyncProcessor
    def _get_fallback_default_layer(self):
        """Get fallback default layer name for text entities."""
        fallbacks = {
            'viewport': 'VIEWPORTS',
            'text': 'Plantext',
            'block': 'BLOCKS'
        }
        return fallbacks.get(self.entity_type, 'DEFAULT_LAYER')

    def _resolve_entity_layer(self, config):
        """
        Resolve the layer for a text entity using unified layer logic.

        Args:
            config: Text entity configuration dictionary

        Returns:
            str: Layer name to use for this text entity
        """
        # Check for individual layer override first
        entity_layer = config.get('layer')
        if entity_layer:
            return entity_layer

        # Fall back to global default layer
        return self.default_layer

    def _calculate_entity_hash(self, config):
        """
        Calculate content hash for text entity configuration.
        Centralized implementation that works for all entity types.

        Args:
            config: Text entity configuration dictionary

        Returns:
            str: Content hash for the configuration
        """
        try:
            from src.sync_hash_utils import calculate_entity_content_hash
            return calculate_entity_content_hash(config, self.entity_type)
        except Exception as e:
            log_warning(f"Error calculating hash for {self.entity_type} '{config.get('name', 'unnamed')}': {str(e)}")
            return "error_hash"
