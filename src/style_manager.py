from src.utils import log_info, log_warning, log_debug, log_error
from src.dxf_utils import get_color_code
import re

class StyleManager:
    def __init__(self, project_loader):
        """Initialize StyleManager with either a ProjectLoader instance or project settings dict."""
        if hasattr(project_loader, 'styles'):
            # If given a ProjectLoader instance
            self.styles = project_loader.styles
            self.name_to_aci = project_loader.name_to_aci
            self.project_loader = project_loader
        else:
            # If given project settings dictionary directly
            self.styles = project_loader.get('styles', {})
            # For direct dictionary usage, we need a default color mapping
            self.name_to_aci = {
                'white': 7, 'red': 1, 'yellow': 2, 'green': 3, 
                'cyan': 4, 'blue': 5, 'magenta': 6
            }
            self.project_loader = None

        self.default_hatch_settings = {
            'pattern': 'SOLID',
            'scale': 1,
            'color': 'BYLAYER',
            'individual_hatches': True
        }

    def get_style(self, style_name_or_config):
        if isinstance(style_name_or_config, str):
            # Handle preset style
            style = self.styles.get(style_name_or_config)
            if style is None:
                log_warning(f"Style preset '{style_name_or_config}' not found.")
                return None, True
            return style, False
        elif isinstance(style_name_or_config, dict):
            if 'preset' in style_name_or_config:
                # Handle preset with overrides (old way - kept for backward compatibility)
                preset_name = style_name_or_config['preset']
                preset = self.styles.get(preset_name)
                if preset is None:
                    log_warning(f"Style preset '{preset_name}' not found.")
                    return style_name_or_config, True
                
                # Remove the preset key from overrides
                overrides = dict(style_name_or_config)
                del overrides['preset']
                
                # Deep merge the preset with overrides
                merged_style = self.deep_merge(preset, overrides)
                return merged_style, False
            elif 'styleOverride' in style_name_or_config:
                # Handle new style override system
                preset_name = style_name_or_config.get('style')
                if not preset_name or not isinstance(preset_name, str):
                    log_warning("styleOverride requires a valid preset name in 'style' key")
                    return style_name_or_config, True
                
                preset = self.styles.get(preset_name)
                if preset is None:
                    log_warning(f"Style preset '{preset_name}' not found.")
                    return style_name_or_config, True
                
                # Deep merge the preset with overrides
                merged_style = self.deep_merge(preset, style_name_or_config['styleOverride'])
                return merged_style, False
            else:
                # Handle pure inline style
                return style_name_or_config, False
        
        return style_name_or_config, False

    def validate_style(self, layer_name, style_config):
        """Validates the complete style configuration for a layer"""
        if isinstance(style_config, str):
            # Validate preset style
            style, warning_generated = self.get_style(style_config)
            if warning_generated:
                return False
        elif isinstance(style_config, dict):
            # Validate inline style or style with overrides
            if 'preset' in style_config:
                # Handle old-style preset with overrides
                preset_style, warning_generated = self.get_style(style_config['preset'])
                if warning_generated:
                    return False
                # Validate overrides
                self._validate_style_overrides(layer_name, style_config)
            elif 'styleOverride' in style_config:
                # Handle new-style overrides
                if 'style' not in style_config or not isinstance(style_config['style'], str):
                    log_warning(f"Layer '{layer_name}' has styleOverride but no valid preset name in 'style' key")
                    return False
                preset_style, warning_generated = self.get_style(style_config['style'])
                if warning_generated:
                    return False
                # Validate overrides
                self._validate_style_overrides(layer_name, style_config['styleOverride'])
            else:
                # Handle pure inline style
                for style_type, style_dict in style_config.items():
                    if style_type == 'layer':
                        self._validate_layer_style(layer_name, style_dict)
                    elif style_type == 'hatch':
                        self._validate_hatch_style(layer_name, style_dict)
                    elif style_type == 'text':
                        self._validate_text_style(layer_name, style_dict)
                    else:
                        log_warning(f"Unknown style type '{style_type}' in layer '{layer_name}'")
            # Validate inline style
            if 'preset' in style_config:
                # Handle preset with overrides
                preset_style, warning_generated = self.get_style(style_config['preset'])
                if warning_generated:
                    return False
                # Validate overrides
                self._validate_style_overrides(layer_name, style_config)
            else:
                # Handle pure inline style
                for style_type, style_dict in style_config.items():
                    if style_type == 'layer':
                        self._validate_layer_style(layer_name, style_dict)
                    elif style_type == 'hatch':
                        self._validate_hatch_style(layer_name, style_dict)
                    elif style_type == 'text':
                        self._validate_text_style(layer_name, style_dict)
                    else:
                        log_warning(f"Unknown style type '{style_type}' in layer '{layer_name}'")
        
        return True

    def _validate_layer_style(self, layer_name, layer_style):
        known_style_keys = {'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'transparency', 'linetypeScale'}
        self._validate_style_keys(layer_name, 'layer', layer_style, known_style_keys)
        
        # Add linetype validation
        if 'linetype' in layer_style:
            linetype = layer_style['linetype']
            if linetype.startswith('ACAD_'):
                # Regular expression pattern for valid ACAD linetypes
                acad_pattern = r'^ACAD_ISO\d{2}W100$'
                if not re.match(acad_pattern, linetype):
                    log_warning(f"Invalid ACAD linetype format '{linetype}' in layer '{layer_name}'. "
                              f"ACAD ISO linetypes should follow the pattern 'ACAD_ISOxxW100' where xx is a two-digit number.")

    def _validate_hatch_style(self, layer_name, hatch_style):
        known_style_keys = {'pattern', 'scale', 'color', 'transparency', 'individual_hatches', 'layers'}
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
        elif isinstance(layer_style, dict):
            if 'preset' in layer_style:
                # Get the preset first
                preset_style, _ = self.get_style(layer_style)
                if preset_style and 'hatch' in preset_style:
                    # Merge preset with any hatch overrides
                    if 'hatch' in layer_style:
                        hatch_config = self.deep_merge(preset_style['hatch'], layer_style['hatch'])
                    else:
                        hatch_config.update(preset_style['hatch'])
            elif 'hatch' in layer_style:
                hatch_config.update(layer_style['hatch'])
            elif 'layer' in layer_style:
                # Use layer settings for hatch if no specific hatch settings are provided
                layer_settings = layer_style['layer']
                if 'transparency' in layer_settings:
                    hatch_config['transparency'] = layer_settings['transparency']
                if 'color' in layer_settings:
                    hatch_config['color'] = layer_settings['color']
                if 'lineweight' in layer_settings:
                    hatch_config['lineweight'] = layer_settings['lineweight']
        
        apply_hatch = layer_info.get('applyHatch', False)
        if isinstance(apply_hatch, dict):
            if 'layers' in apply_hatch:
                hatch_config['layers'] = apply_hatch['layers']
        
        return hatch_config

    def process_layer_style(self, layer_name, layer_config):
        """Process layer style with support for presets, inline styles, and overrides"""
        style = layer_config.get('style', {})
        style_override = layer_config.get('styleOverride', {})
        
        # Validate style before processing
        self.validate_style(layer_name, style)
        
        final_style = {}
        
        # Process base style (either preset or inline)
        if isinstance(style, str):
            # Handle preset style
            preset_style, warning_generated = self.get_style(style)
            if not warning_generated and preset_style:
                final_style = preset_style
        elif isinstance(style, dict):
            # Handle inline style
            final_style = style
        
        # Apply style overrides if they exist
        if style_override:
            final_style = self.deep_merge(final_style, style_override)
        
        # Extract layer properties from the processed style
        layer_style = final_style.get('layer', {})
        
        properties = {
            'color': get_color_code(layer_style.get('color'), self.name_to_aci),
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
        """
        Deep merge two dictionaries, merging at all levels instead of replacing.
        dict1 is the base (preset), dict2 contains the overrides
        """
        result = dict1.copy()
        
        for key, value in dict2.items():
            if (key in result and 
                isinstance(result[key], dict) and 
                isinstance(value, dict)):
                # Recursively merge nested dictionaries
                result[key] = self.deep_merge(result[key], value)
            else:
                # For non-dict values or new keys, just update/add the value
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

    def _validate_style_overrides(self, layer_name, style_config):
        """Validates style overrides when using a preset"""
        for key, value in style_config.items():
            if key != 'preset':
                if key in ['layer', 'hatch', 'text']:
                    if key == 'layer':
                        self._validate_layer_style(layer_name, value)
                    elif key == 'hatch':
                        self._validate_hatch_style(layer_name, value)
                    elif key == 'text':
                        self._validate_text_style(layer_name, value)
                else:
                    log_warning(f"Unknown style override key '{key}' in layer '{layer_name}'")




