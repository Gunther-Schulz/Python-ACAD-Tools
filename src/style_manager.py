from src.utils import log_info, log_warning
from src.dfx_utils import get_color_code

class StyleManager:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.styles = project_loader.styles  # Load all styles from project_loader
        self.default_hatch_settings = {
            'pattern': 'SOLID',
            'scale': 1,
            'color': 'BYLAYER',
            'transparency': 0
        }

    def get_style(self, style_name_or_config):
        if isinstance(style_name_or_config, str):
            style = self.styles.get(style_name_or_config)
            if style is None:
                log_warning(f"Style preset '{style_name_or_config}' not found.")
                return None, True  # Return None and True to indicate a warning was logged
            return style, False  # Return the style and False to indicate no warning
        return style_name_or_config, False

    def validate_style(self, layer_name, style_config):
        style, warning_generated = self.get_style(style_config)
        if warning_generated:
            return
        
        if style is None:
            log_warning(f"Style for layer '{layer_name}' not found.")
            return
        
        known_style_keys = {'layer', 'hatch', 'text'}
        unknown_style_keys = set(style.keys()) - known_style_keys
        if unknown_style_keys:
            log_warning(f"Unknown style keys in layer {layer_name}: {', '.join(unknown_style_keys)}")

        if 'layer' in style:
            self._validate_layer_style(layer_name, style['layer'])
        if 'hatch' in style:
            self._validate_hatch_style(layer_name, style['hatch'])
        if 'text' in style:
            self._validate_text_style(layer_name, style['text'])

    def _validate_layer_style(self, layer_name, layer_style):
        known_style_keys = {'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'transparency'}
        self._validate_style_keys(layer_name, 'layer', layer_style, known_style_keys)

    def _validate_hatch_style(self, layer_name, hatch_style):
        known_style_keys = {'pattern', 'scale', 'color', 'transparency'}
        self._validate_style_keys(layer_name, 'hatch', hatch_style, known_style_keys)

    def _validate_text_style(self, layer_name, text_style):
        known_style_keys = {'color', 'height', 'font', 'style', 'alignment'}
        self._validate_style_keys(layer_name, 'text', text_style, known_style_keys)

    def _validate_style_keys(self, layer_name, style_type, style_dict, known_keys):
        unknown_keys = set(style_dict.keys()) - known_keys
        if unknown_keys:
            log_warning(f"Unknown {style_type} style keys in layer {layer_name}: {', '.join(unknown_keys)}")

        for key in style_dict.keys():
            closest_match = min(known_keys, key=lambda x: self._levenshtein_distance(key, x))
            if key != closest_match and self._levenshtein_distance(key, closest_match) <= 2:
                log_warning(f"Possible typo in {style_type} style key for layer {layer_name}: '{key}'. Did you mean '{closest_match}'?")

    def _levenshtein_distance(self, s1, s2):
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def get_hatch_config(self, layer_info):
        hatch_config = self.default_hatch_settings.copy()
        
        layer_style = layer_info.get('style', {})
        if isinstance(layer_style, str):
            style_preset, _ = self.get_style(layer_style)
            if style_preset and 'hatch' in style_preset:
                hatch_config.update(style_preset['hatch'])
        elif isinstance(layer_style, dict) and 'hatch' in layer_style:
            hatch_config.update(layer_style['hatch'])
        
        apply_hatch = layer_info.get('applyHatch', False)
        if isinstance(apply_hatch, dict):
            if 'layers' in apply_hatch:
                hatch_config['layers'] = apply_hatch['layers']
        
        return hatch_config

    def process_layer_style(self, layer_name, layer_config):
        style = layer_config.get('style', {})
        
        if isinstance(style, str):
            style, warning_generated = self.get_style(style)
            if warning_generated:
                return {}
        
        layer_style = style.get('layer', {}) if isinstance(style, dict) else {}
        
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
        style, warning_generated = self.get_style(layer_config.get('style', {}))
        if warning_generated:
            return {}
        return style.get('text', {}) if style else {}

    def deep_merge(self, dict1, dict2):
        result = dict1.copy()
        for key, value in dict2.items():
            if isinstance(value, dict):
                result[key] = self.deep_merge(result.get(key, {}), value)
            else:
                result[key] = value
        return result

    def _process_layer_style(self, layer_name, layer_style):
        known_style_keys = {'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'vp_freeze', 'transparency'}
        self._process_style_keys(layer_name, 'layer', layer_style, known_style_keys)

    def _process_hatch_style(self, layer_name, hatch_style):
        known_style_keys = {'pattern', 'scale', 'color', 'transparency'}
        self._process_style_keys(layer_name, 'hatch', hatch_style, known_style_keys)

    def _process_text_style(self, layer_name, text_style):
        known_style_keys = {'color', 'height', 'font', 'style', 'alignment'}
        self._process_style_keys(layer_name, 'text', text_style, known_style_keys)

    def _process_style_keys(self, layer_name, style_type, style_dict, known_keys):
        unknown_keys = set(style_dict.keys()) - known_keys
        if unknown_keys:
            log_warning(f"Unknown {style_type} style keys in layer {layer_name}: {', '.join(unknown_keys)}")

        for key in style_dict.keys():
            closest_match = min(known_keys, key=lambda x: self._levenshtein_distance(key, x))
            if key != closest_match and self._levenshtein_distance(key, closest_match) <= 2:
                log_warning(f"Possible typo in {style_type} style key for layer {layer_name}: '{key}'. Did you mean '{closest_match}'?")

