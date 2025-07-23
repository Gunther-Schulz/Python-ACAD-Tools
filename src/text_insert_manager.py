import traceback
from src.utils import log_info, log_warning, log_error, log_debug
from src.dxf_utils import add_mtext, remove_entities_by_layer, ensure_layer_exists, attach_custom_data
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
                # Attach custom data to identify this as our entity
                attach_custom_data(mtext, self.script_identifier, name)
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
        for space in [doc.modelspace(), doc.paperspace()]:
            for entity in space:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    try:
                        # Check if this entity has our custom data with the matching name
                        xdata = entity.get_xdata(self.script_identifier)
                        if xdata:
                            for code, value in xdata:
                                if code == 1000 and value == name:
                                    return entity
                    except:
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

            # Add global text sync setting if it exists
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
            log_error(f"Traceback: {traceback.format_exc()}")
            return False

    def process_text_inserts_legacy(self, msp):
        """
        Legacy method for backward compatibility with updateDxf flag.
        This method handles the old updateDxf-based processing.
        """
        text_inserts = self.project_settings.get('textInserts', [])
        if not text_inserts:
            log_debug("No text inserts found in project settings")
            return

        # Collect target layers that need cleaning for updateDxf=true configs
        target_layers = set()
        for text_config in text_inserts:
            # Handle legacy updateDxf flag
            if text_config.get('updateDxf', False):
                target_layers.add(text_config.get('targetLayer', 'Plantext'))

        # Remove all existing text entities from these layers
        for layer_name in target_layers:
            log_debug(f"Removing existing text entities from layer: {layer_name}")
            remove_entities_by_layer(msp, layer_name, self.script_identifier)

        # Process text inserts that use legacy updateDxf flag
        for text_config in text_inserts:
            if text_config.get('updateDxf', False):
                # Convert to sync format and process
                temp_config = text_config.copy()
                temp_config['sync'] = 'push'  # updateDxf=true means push
                result = self._sync_push(msp.doc, msp, temp_config)
                if result:
                    log_debug(f"Processed legacy text insert: {text_config.get('name', 'unnamed')}")

    def clean_target_layers(self, doc, configs_to_process):
        """Clean target layers for configs that will be processed."""
        target_layers = set()
        for config in configs_to_process:
            sync_direction = self._get_sync_direction(config)
            if sync_direction == 'push':
                target_layers.add(config.get('targetLayer', 'Plantext'))

        # Remove existing entities from layers that will be updated
        for layer_name in target_layers:
            log_debug(f"Cleaning text entities from layer: {layer_name}")
            for space in [doc.modelspace(), doc.paperspace()]:
                remove_entities_by_layer(space, layer_name, self.script_identifier)
