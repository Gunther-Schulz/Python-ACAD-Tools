"""Module for handling style operations."""

from src.core.utils import log_warning, log_error, log_debug
from ..dxf_exporter.utils.style_defaults import (
    DEFAULT_HATCH_STYLE,
    DEFAULT_TEXT_STYLE,
    DEFAULT_LAYER_STYLE,
    DEFAULT_ENTITY_STYLE,
    VALID_STYLE_PROPERTIES
)

class StyleHandler:
    def __init__(self, layer_processor):
        try:
            self.layer_processor = layer_processor
            self.style_manager = layer_processor.style_manager
            self.default_hatch_style = DEFAULT_HATCH_STYLE.copy()
            self.default_text_style = DEFAULT_TEXT_STYLE.copy()
            self.default_layer_style = DEFAULT_LAYER_STYLE.copy()
            self.default_entity_style = DEFAULT_ENTITY_STYLE.copy()
            log_debug("Style handler initialized successfully")
        except Exception as e:
            log_error(f"Error initializing style handler: {str(e)}")
            raise

    def _process_style(self, layer_name, style_config):
        """Process style configuration for a layer."""
        try:
            if not style_config:
                log_debug(f"No style configuration for layer {layer_name}")
                return None

            log_debug(f"Processing style for layer {layer_name}: {style_config}")
            
            # Handle string-based style references
            if isinstance(style_config, str):
                style, warning = self.style_manager.get_style(style_config)
                if warning:
                    log_warning(f"Warning processing style for layer {layer_name}: {warning}")
                return style

            # Handle style with overrides
            if isinstance(style_config, dict):
                processed_style = {}
                
                # Process base style if specified
                if 'style' in style_config:
                    base_style, warning = self.style_manager.get_style(style_config['style'])
                    if not warning and base_style:
                        processed_style = base_style.copy()

                # Apply overrides
                if 'styleOverride' in style_config:
                    self._validate_style_overrides(layer_name, style_config['styleOverride'])
                    processed_style = self.style_manager.deep_merge(processed_style, style_config['styleOverride'])

                # Process direct style configuration
                for style_type in ['layer', 'entity', 'text', 'hatch']:
                    if style_type in style_config:
                        if style_type not in processed_style:
                            processed_style[style_type] = {}
                        self._validate_style_section(layer_name, style_type, style_config[style_type])
                        processed_style[style_type].update(style_config[style_type])

                return processed_style

            return None
            
        except Exception as e:
            log_error(f"Error processing style for layer {layer_name}: {str(e)}")
            return None

    def _process_hatch_config(self, layer_name, layer_config):
        """Process hatch configuration for a layer."""
        try:
            if not layer_config.get('applyHatch'):
                log_debug(f"No hatch configuration for layer {layer_name}")
                return None

            hatch_config = self.default_hatch_style.copy()
            log_debug(f"Processing hatch configuration for layer {layer_name}")
            
            # Get style configuration
            style_config = layer_config.get('style', {})
            if isinstance(style_config, str):
                style, warning = self.style_manager.get_style(style_config)
                if warning:
                    log_warning(f"Warning processing hatch style for layer {layer_name}: {warning}")
                if style and 'hatch' in style:
                    self._validate_style_section(layer_name, 'hatch', style['hatch'])
                    hatch_config.update(style['hatch'])
            elif isinstance(style_config, dict) and 'hatch' in style_config:
                self._validate_style_section(layer_name, 'hatch', style_config['hatch'])
                hatch_config.update(style_config['hatch'])

            # Add layer-specific hatch settings
            hatch_settings = {
                'pattern': layer_config.get('hatchPattern', hatch_config['pattern']),
                'scale': layer_config.get('hatchScale', hatch_config['scale']),
                'rotation': layer_config.get('hatchRotation', 0),
                'layers': layer_config.get('hatchLayers', [layer_name]),
                'individual_hatches': layer_config.get('individualHatches', hatch_config['individual_hatches'])
            }
            
            # Validate and merge settings
            self._validate_style_section(layer_name, 'hatch', hatch_settings)
            hatch_config.update(hatch_settings)
            
            log_debug(f"Final hatch configuration for layer {layer_name}: {hatch_config}")
            return hatch_config
            
        except Exception as e:
            log_error(f"Error processing hatch configuration for layer {layer_name}: {str(e)}")
            return None

    def process_hatch_style(self, layer_config):
        """Process hatch style configuration."""
        try:
            layer_name = layer_config.get('name', 'unnamed')
            log_debug(f"Processing hatch style for layer {layer_name}")
            
            hatch_style = self.default_hatch_style.copy()
            
            # Get style configuration
            style_config = layer_config.get('style', {})
            if isinstance(style_config, str):
                style, warning = self.style_manager.get_style(style_config)
                if not warning and style and 'hatch' in style:
                    self._validate_style_section(layer_name, 'hatch', style['hatch'])
                    hatch_style.update(style['hatch'])
            elif isinstance(style_config, dict) and 'hatch' in style_config:
                self._validate_style_section(layer_name, 'hatch', style_config['hatch'])
                hatch_style.update(style_config['hatch'])

            # Update with layer-specific settings
            layer_settings = {
                'pattern': layer_config.get('hatchPattern', hatch_style['pattern']),
                'scale': layer_config.get('hatchScale', hatch_style['scale']),
                'color': layer_config.get('hatchColor', hatch_style['color']),
                'transparency': layer_config.get('hatchTransparency', hatch_style['transparency']),
                'lineweight': layer_config.get('hatchLineweight', hatch_style['lineweight'])
            }
            
            # Validate and merge settings
            self._validate_style_section(layer_name, 'hatch', layer_settings)
            hatch_style.update(layer_settings)
            
            log_debug(f"Processed hatch style for layer {layer_name}: {hatch_style}")
            return hatch_style
            
        except Exception as e:
            log_error(f"Error processing hatch style: {str(e)}")
            return self.default_hatch_style.copy()

    def _validate_style_section(self, layer_name, section_type, style_dict):
        """Validate a style section against known valid properties."""
        try:
            if section_type not in VALID_STYLE_PROPERTIES:
                log_warning(f"Unknown style section type '{section_type}' for layer {layer_name}")
                return

            valid_props = VALID_STYLE_PROPERTIES[section_type]
            for prop, value in style_dict.items():
                if prop in valid_props:
                    constraints = valid_props[prop]
                    if isinstance(value, (int, float)):
                        if value < constraints.get('min', float('-inf')) or value > constraints.get('max', float('inf')):
                            log_warning(f"Value {value} for property '{prop}' in {section_type} style of layer {layer_name} "
                                      f"is outside valid range [{constraints['min']}, {constraints['max']}]")
                else:
                    log_warning(f"Unknown property '{prop}' in {section_type} style of layer {layer_name}")
        except Exception as e:
            log_error(f"Error validating style section: {str(e)}")

    def _validate_style_overrides(self, layer_name, overrides):
        """Validate style overrides."""
        try:
            for section_type, section_dict in overrides.items():
                if section_type in ['layer', 'entity', 'text', 'hatch']:
                    self._validate_style_section(layer_name, section_type, section_dict)
                else:
                    log_warning(f"Unknown style override section '{section_type}' for layer {layer_name}")
        except Exception as e:
            log_error(f"Error validating style overrides: {str(e)}") 