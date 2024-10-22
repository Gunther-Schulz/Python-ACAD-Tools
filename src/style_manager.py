from src.utils import log_info, log_warning
from src.dfx_utils import get_color_code

class StyleManager:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.default_hatch_settings = {
            'pattern': 'SOLID',
            'scale': 1,
            'color': 'BYLAYER',
            'transparency': 0
        }

    def get_style(self, style_name_or_config):
        if isinstance(style_name_or_config, str):
            return self.project_loader.get_style(style_name_or_config)
        return style_name_or_config

    def get_hatch_config(self, layer_config):
        hatch_config = self.default_hatch_settings.copy()
        
        if 'style' in layer_config:
            style = self.get_style(layer_config['style'])
            if isinstance(style, dict) and 'hatch' in style:
                hatch_config.update(style['hatch'])
        
        if 'applyHatch' in layer_config:
            apply_hatch = layer_config['applyHatch']
            if isinstance(apply_hatch, dict):
                hatch_config.update(apply_hatch)
            else:
                hatch_config['apply'] = apply_hatch
        
        hatch_config['apply'] = hatch_config.get('apply', True)
        
        return hatch_config

    def process_layer_style(self, layer_name, layer_config):
        style = self.get_style(layer_config.get('style', {}))
        layer_style = style.get('layer', {})
        
        properties = {
            'color': get_color_code(layer_style.get('color'), self.project_loader.name_to_aci),
            'linetype': layer_style.get('linetype', 'Continuous'),
            'lineweight': layer_style.get('lineweight', 0),
            'plot': layer_style.get('plot', True),
            'locked': layer_style.get('locked', False),
            'frozen': layer_style.get('frozen', False),
            'is_on': layer_style.get('is_on', True),
            'transparency': layer_style.get('transparency', 0),
            'close': layer_style.get('close', True),
            'linetypeScale': layer_style.get('linetypeScale', 1.0),
        }
        
        return properties

    def process_text_style(self, layer_name, layer_config):
        style = self.get_style(layer_config.get('style', {}))
        return style.get('text', {})

    def deep_merge(self, dict1, dict2):
        result = dict1.copy()
        for key, value in dict2.items():
            if isinstance(value, dict):
                result[key] = self.deep_merge(result.get(key, {}), value)
            else:
                result[key] = value
        return result
