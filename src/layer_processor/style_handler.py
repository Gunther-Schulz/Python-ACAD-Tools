"""Module for handling style operations."""

from src.core.utils import log_warning, log_error, log_debug
from ..dxf_exporter.utils.style_defaults import DEFAULT_HATCH_STYLE

class StyleHandler:
    def __init__(self, layer_processor):
        try:
            self.layer_processor = layer_processor
            self.style_manager = layer_processor.style_manager
            self.default_hatch_style = DEFAULT_HATCH_STYLE.copy()
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
            
            if isinstance(style_config, str):
                style, warning = self.style_manager.get_style(style_config)
                if warning:
                    log_warning(f"Warning processing style for layer {layer_name}: {warning}")
                return style

            return self.style_manager.get_style(style_config)
            
        except Exception as e:
            log_error(f"Error processing style for layer {layer_name}: {str(e)}")
            return None

    def _process_hatch_config(self, layer_name, layer_config):
        """Process hatch configuration for a layer."""
        try:
            if not layer_config.get('applyHatch'):
                log_debug(f"No hatch configuration for layer {layer_name}")
                return None

            hatch_config = {}
            log_debug(f"Processing hatch configuration for layer {layer_name}")
            
            # Get style configuration
            style_config = layer_config.get('style', {})
            if isinstance(style_config, str):
                style, warning = self.style_manager.get_style(style_config)
                if warning:
                    log_warning(f"Warning processing hatch style for layer {layer_name}: {warning}")
                if style and 'hatch' in style:
                    hatch_config.update(style['hatch'])
            elif isinstance(style_config, dict) and 'hatch' in style_config:
                hatch_config.update(style_config['hatch'])

            # Add layer-specific hatch settings
            hatch_settings = {
                'pattern': layer_config.get('hatchPattern', 'SOLID'),
                'scale': layer_config.get('hatchScale', 1),
                'rotation': layer_config.get('hatchRotation', 0),
                'layers': layer_config.get('hatchLayers', [layer_name])
            }
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
            
            hatch_style = {
                'pattern': layer_config.get('hatchPattern', self.default_hatch_style['pattern']),
                'scale': layer_config.get('hatchScale', self.default_hatch_style['scale']),
                'color': layer_config.get('hatchColor', self.default_hatch_style['color']),
                'transparency': layer_config.get('hatchTransparency', self.default_hatch_style['transparency'])
            }
            
            log_debug(f"Processed hatch style for layer {layer_name}: {hatch_style}")
            return hatch_style
            
        except Exception as e:
            log_error(f"Error processing hatch style: {str(e)}")
            return self.default_hatch_style.copy() 