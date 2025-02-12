"""Module for handling style operations."""

from src.utils import log_warning

class StyleHandler:
    def __init__(self, layer_processor):
        self.layer_processor = layer_processor
        self.style_manager = layer_processor.style_manager

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
        if not layer_config.get('applyHatch'):
            return None

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

        # Add layer-specific hatch settings
        hatch_config.update({
            'pattern': layer_config.get('hatchPattern', 'SOLID'),
            'scale': layer_config.get('hatchScale', 1),
            'rotation': layer_config.get('hatchRotation', 0),
            'layers': layer_config.get('hatchLayers', [layer_name])
        })

        return hatch_config 