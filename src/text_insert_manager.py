import traceback
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_mtext, remove_entities_by_layer, ensure_layer_exists
from src.sync_manager_base import SyncManagerBase


class TextInsertManager(SyncManagerBase):
    """Manager for text insert synchronization between YAML configs and AutoCAD."""

    def __init__(self, project_settings, script_identifier, style_manager, name_to_aci, project_loader=None):
        # Initialize base class (use 'text' as entity_type to match project_loader key 'text_sync')
        super().__init__(project_settings, script_identifier, 'text', project_loader)

        # Text insert specific dependencies
        self.style_manager = style_manager
        self.name_to_aci = name_to_aci

    def _get_entity_configs(self):
        """Get text insert configurations from project settings."""
        return self.project_settings.get('textInserts', []) or []

    def _sync_push(self, doc, space, config):
        """Create or update text insert in AutoCAD from YAML configuration."""
        name = config.get('name', 'unnamed')

        try:
            # Get target layer
            layer_name = config.get('targetLayer', 'Plantext')

            # Ensure layer exists
            ensure_layer_exists(doc, layer_name)

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

            # Get the correct space (model or paper)
            target_space = doc.paperspace() if config.get('paperspace', False) else doc.modelspace()

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
            # Extract properties from AutoCAD text entity
            updated_config = self._extract_text_properties(existing_text, config)

            # Update the configuration in project_settings
            text_configs = self.project_settings.get('textInserts', []) or []
            for i, original_config in enumerate(text_configs):
                if original_config.get('name') == name:
                    # Preserve sync direction and other non-geometric properties
                    if 'sync' in original_config:
                        updated_config['sync'] = original_config['sync']
                    elif self.default_sync != 'pull':
                        updated_config['sync'] = 'pull'

                    # Preserve other configuration properties
                    for key in ['style', 'targetLayer', 'paperspace', 'justification']:
                        if key in original_config:
                            updated_config[key] = original_config[key]

                    text_configs[i] = updated_config
                    break

            return {'entity': existing_text, 'yaml_updated': True}

        except Exception as e:
            log_error(f"Error pulling text insert properties for '{name}': {str(e)}")
            return None

    def _find_text_by_name(self, doc, name):
        """Find a text entity by name using custom data."""
        # Text inserts work only in paperspace, not modelspace
        paper_space = doc.paperspace()
        for entity in paper_space:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                try:
                    xdata = entity.get_xdata('DXFEXPORTER')
                    if xdata:
                        in_text_section = False
                        text_name = None

                        for code, value in xdata:
                            if code == 1000 and value == 'TEXT_NAME':
                                in_text_section = True
                            elif in_text_section and code == 1000:
                                text_name = value
                                break

                        if text_name == name:
                            return entity
                except Exception as e:
                    # Only log if there's an actual error (not just missing XDATA)
                    if "DXFEXPORTER" not in str(e):
                        log_debug(f"Error checking text {entity.dxf.handle}: {str(e)}")
                    continue
        return None

    def _extract_text_properties(self, text_entity, base_config):
        """Extract text properties from AutoCAD text entity."""
        config = {'name': base_config['name']}

        try:
            # Extract position
            insert_point = text_entity.dxf.insert
            config['position'] = {
                'type': 'absolute',
                'x': float(insert_point[0]),
                'y': float(insert_point[1])
            }

            # Extract text content
            if text_entity.dxftype() == 'MTEXT':
                config['text'] = text_entity.text
            else:  # TEXT entity
                config['text'] = text_entity.dxf.text

            # Extract layer
            config['targetLayer'] = text_entity.dxf.layer

            # Determine if it's in paperspace
            # This is a simple heuristic - could be improved
            for layout in text_entity.doc.layouts:
                if layout.name.startswith('*Paper') and text_entity in layout:
                    config['paperspace'] = True
                    break
            else:
                config['paperspace'] = False

            return config

        except Exception as e:
            log_error(f"Error extracting text properties: {str(e)}")
            return {'name': base_config['name']}

    def _write_entity_yaml(self):
        """Write updated text insert configuration back to YAML file."""
        if not self.project_loader:
            log_warning("Cannot write text insert YAML - no project_loader available")
            return False

        try:
            # Prepare text insert data structure
            text_data = {
                'textInserts': self.project_settings.get('textInserts', [])
            }

            # Add global text insert settings using new generalized structure
            if 'text_discovery' in self.project_settings:
                text_data['discovery'] = self.project_settings['text_discovery']
            if 'text_deletion_policy' in self.project_settings:
                text_data['deletion_policy'] = self.project_settings['text_deletion_policy']
            if 'text_sync' in self.project_settings:
                text_data['sync'] = self.project_settings['text_sync']

            # Write back to text_inserts.yaml
            success = self.project_loader.write_yaml_file('text_inserts.yaml', text_data)
            if success:
                log_info("Successfully updated text_inserts.yaml with sync changes")
            else:
                log_error("Failed to write text insert configuration back to YAML")
            return success

        except Exception as e:
            log_error(f"Error writing text insert YAML: {str(e)}")
            return False

    def clean_target_layers(self, doc, configs_to_process):
        """Clean target layers for configs that will be processed."""
        target_layers = set()
        for config in configs_to_process:
            sync_direction = self._get_sync_direction(config)
            if sync_direction == 'push':
                target_layers.add(config.get('targetLayer', 'Plantext'))

        # Remove existing entities from layers that will be updated
        # Text inserts work only in paperspace, not modelspace
        for layer_name in target_layers:
            log_debug(f"Cleaning text entities from layer: {layer_name}")
            remove_entities_by_layer(doc.paperspace(), layer_name, self.script_identifier)

    def _discover_unknown_entities(self, doc, space):
        """Discover text entities in AutoCAD that aren't managed by this script."""
        discovered = []
        text_counter = 1

        # Text inserts work only in paperspace, not modelspace
        paper_space = doc.paperspace()

        for entity in paper_space:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                try:
                    # Check if this text has our script metadata
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
                        else:
                            text_name = f"Text_{str(entity.dxf.handle).zfill(3)}"
                    else:
                        text_name = f"Text_{str(entity.dxf.handle).zfill(3)}"

                    log_info(f"Discovered manual text in PaperSpace, assigned name: {text_name}")

                    # Attach metadata to mark it as ours
                    entity.set_xdata(
                        'DXFEXPORTER',
                        [
                            (1000, self.script_identifier),
                            (1002, '{'),
                            (1000, 'TEXT_NAME'),
                            (1000, text_name),
                            (1002, '}')
                        ]
                    )

                    discovered.append({
                        'entity': entity,
                        'name': text_name,
                        'space': 'PaperSpace'
                    })
                    text_counter += 1

                except Exception as e:
                    log_error(f"Error checking text metadata: {str(e)}")
                    continue

        # Simple summary
        total_texts = sum(1 for entity in paper_space if entity.dxftype() in ['TEXT', 'MTEXT'])
        log_info(f"Discovery completed: Found {len(discovered)} unknown texts out of {total_texts} total text entities in PaperSpace")

        return discovered

    def _handle_entity_deletions(self, doc, space):
        """Handle deletion of text inserts that exist in YAML but not in AutoCAD."""
        if self.deletion_policy == 'ignore':
            return []

        text_configs = self.project_settings.get('textInserts', []) or []
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
            # Extract text content
            text_content = getattr(entity.dxf, 'text', '') or getattr(entity, 'text', '')
            config['text'] = text_content

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
                config['targetLayer'] = entity.dxf.layer

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
            # Only set explicit sync if it differs from global default
            if self.default_sync != 'pull':
                minimal_config['sync'] = 'pull'
            return minimal_config

    def _attach_entity_metadata(self, entity, config):
        """Attach custom metadata to a text entity to mark it as managed by this script."""
        entity.set_xdata(
            'DXFEXPORTER',
            [
                (1000, self.script_identifier),
                (1002, '{'),
                (1000, 'TEXT_NAME'),
                (1000, config['name']),
                (1002, '}')
            ]
        )

    def _get_text_by_name(self, doc, name):
        """Retrieve a text entity by its name using xdata."""
        # Text inserts work only in paperspace, not modelspace
        paper_space = doc.paperspace()
        for entity in paper_space:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                try:
                    xdata = entity.get_xdata('DXFEXPORTER')
                    if xdata:
                        in_text_section = False
                        text_name = None

                        for code, value in xdata:
                            if code == 1000 and value == 'TEXT_NAME':
                                in_text_section = True
                            elif in_text_section and code == 1000:
                                text_name = value
                                break

                        if text_name == name:
                            return entity
                except Exception as e:
                    # Only log if there's an actual error (not just missing XDATA)
                    if "DXFEXPORTER" not in str(e):
                        log_debug(f"Error checking text {entity.dxf.handle}: {str(e)}")
                    continue
        return None
