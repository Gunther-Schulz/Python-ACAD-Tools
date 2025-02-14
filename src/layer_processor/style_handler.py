"""Module for handling style operations."""

from src.core.utils import log_warning
from ..dxf_exporter.utils.style_defaults import DEFAULT_HATCH_STYLE

class StyleHandler:
    def __init__(self, layer_processor):
        self.layer_processor = layer_processor
        self.style_manager = layer_processor.style_manager
        self.default_hatch_style = DEFAULT_HATCH_STYLE.copy()

    def _process_style(self, layer_name, style_config):
        """Process style configuration for a layer."""
        if not style_config:
            return None

        if isinstance(style_config, str):
            # If style_config is a string, treat it as a style name
            style, warning = self.style_manager.get_style(style_config)
            if warning:
                log_warning(f"Warning processing style for layer {layer_name}: {warning}")
            return style

        # If style_config is a dict, process it directly
        return self.style_manager.get_style(style_config)

    def _process_hatch_config(self, layer_name, layer_config):
        """Process hatch configuration for a layer."""
        hatch_config = {}
        
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

        # If no hatch configuration found, return None
        if not hatch_config:
            return None

        # Add layer-specific hatch settings if they exist
        if 'pattern' in layer_config:
            hatch_config['pattern'] = layer_config['pattern']
        if 'scale' in layer_config:
            hatch_config['scale'] = layer_config['scale']
        if 'rotation' in layer_config:
            hatch_config['rotation'] = layer_config['rotation']
        if 'layers' in layer_config:
            hatch_config['layers'] = layer_config['layers']
        else:
            hatch_config['layers'] = [layer_name]

        return hatch_config

    def process_hatch_style(self, layer_config):
        """Process hatch style configuration."""
        if not layer_config.get('hatch'):
            return None

        hatch_style = self.default_hatch_style.copy()
        hatch_style.update(layer_config['hatch'])
        return hatch_style 