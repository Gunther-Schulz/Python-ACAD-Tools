"""Module for managing styles in DXF files."""

from src.core.utils import log_warning, log_info, log_error, log_debug
from src.dxf_utils import get_color_code, convert_transparency, deep_merge
from src.dxf_utils.style_defaults import (
    DEFAULT_TEXT_STYLE,
    DEFAULT_LAYER_STYLE,
    DEFAULT_HATCH_STYLE,
    DEFAULT_ENTITY_STYLE,
    VALID_STYLE_PROPERTIES,
    DEFAULT_COLOR_MAPPING,
    VALID_ATTACHMENT_POINTS,
    VALID_TEXT_ALIGNMENTS,
    TEXT_LINE_SPACING_STYLES
)
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
            self.name_to_aci = DEFAULT_COLOR_MAPPING
            self.project_loader = None

        # Initialize with defaults from style_defaults
        self.default_hatch_settings = DEFAULT_HATCH_STYLE.copy()
        self.default_layer_settings = DEFAULT_LAYER_STYLE.copy()
        self.default_text_settings = DEFAULT_TEXT_STYLE.copy()
        self.default_entity_style = DEFAULT_ENTITY_STYLE.copy()

    def get_style(self, style_name_or_config):
        """Get style configuration with support for presets and inline styles."""
        if isinstance(style_name_or_config, str):
            # Handle preset style
            style = self.styles.get(style_name_or_config)
            if style is None:
                log_warning(f"Style preset '{style_name_or_config}' not found.")
                return None, True
            return style, False
        elif isinstance(style_name_or_config, dict):
            if 'styleOverride' in style_name_or_config:
                # Handle style override system
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

    def _validate_layer_style(self, layer_name, style_config):
        """Validate layer style configuration."""
        if not isinstance(style_config, dict):
            log_warning(f"Invalid style configuration for layer '{layer_name}'. Expected dictionary, got {type(style_config)}")
            return False

        # Validate layer properties
        if 'layer' in style_config:
            layer_style = style_config['layer']
            if not isinstance(layer_style, dict):
                log_warning(f"Invalid layer style for layer '{layer_name}'. Expected dictionary, got {type(layer_style)}")
                return False

            # Known layer properties
            layer_style_keys = {'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'transparency'}
            unknown_keys = set(layer_style.keys()) - layer_style_keys
            if unknown_keys:
                log_warning(f"Unknown layer style keys in layer '{layer_name}': {', '.join(unknown_keys)}")

            # Validate linetype
            if 'linetype' in layer_style:
                linetype = layer_style['linetype']
                if linetype.startswith('ACAD_'):
                    acad_pattern = r'^ACAD_ISO\d{2}W100$'
                    if not re.match(acad_pattern, linetype):
                        log_warning(f"Invalid ACAD linetype format '{linetype}' in layer '{layer_name}'. "
                                  f"ACAD ISO linetypes should follow the pattern 'ACAD_ISOxxW100' where xx is a two-digit number.")

            # Validate numeric constraints
            if 'lineweight' in layer_style:
                lineweight = layer_style['lineweight']
                if not isinstance(lineweight, (int, float)) or lineweight < -3 or lineweight > 211:
                    log_warning(f"Invalid lineweight value {lineweight} in layer '{layer_name}'. Must be between -3 and 211.")

            if 'transparency' in layer_style:
                transparency = layer_style['transparency']
                if not isinstance(transparency, (int, float)) or transparency < 0 or transparency > 255:
                    log_warning(f"Invalid transparency value {transparency} in layer '{layer_name}'. Must be between 0 and 255.")

        # Validate entity properties
        if 'entity' in style_config:
            entity_style = style_config['entity']
            if not isinstance(entity_style, dict):
                log_warning(f"Invalid entity style for layer '{layer_name}'. Expected dictionary, got {type(entity_style)}")
                return False

            # Known entity properties
            entity_style_keys = {'close', 'linetypeScale', 'linetypeGeneration'}
            unknown_keys = set(entity_style.keys()) - entity_style_keys
            if unknown_keys:
                log_warning(f"Unknown entity style keys in layer '{layer_name}': {', '.join(unknown_keys)}")

            if 'linetypeScale' in entity_style:
                scale = entity_style['linetypeScale']
                if not isinstance(scale, (int, float)) or scale < 0.01 or scale > 1000.0:
                    log_warning(f"Invalid linetypeScale value {scale} in layer '{layer_name}'. Must be between 0.01 and 1000.0.")

        # Check for possible typos in property names
        for section in ['layer', 'entity']:
            if section in style_config:
                style_dict = style_config[section]
                known_keys = layer_style_keys if section == 'layer' else entity_style_keys
                for key in style_dict.keys():
                    closest_match = min(known_keys, key=lambda x: self._levenshtein_distance(key, x))
                    if key != closest_match and self._levenshtein_distance(key, closest_match) <= 2:
                        log_warning(f"Possible typo in {section} style key for layer {layer_name}: '{key}'. Did you mean '{closest_match}'?")

        return True

    def _validate_hatch_style(self, layer_name, hatch_style):
        known_style_keys = {'pattern', 'scale', 'color', 'transparency', 'individual_hatches', 'layers', 'lineweight'}
        self._validate_style_keys(layer_name, 'hatch', hatch_style, known_style_keys)

    def _validate_text_style(self, layer_name, text_style):
        """Validate text style properties."""
        known_style_keys = {
            'color',
            'height',
            'font',
            'maxWidth',
            'attachmentPoint',
            'flowDirection',
            'lineSpacingStyle',
            'lineSpacingFactor',
            'bgFill',
            'bgFillColor', 
            'bgFillScale',
            'underline',
            'overline',
            'strikeThrough',
            'obliqueAngle',
            'rotation',
            'paragraph'
        }

        # Validate main text style keys
        self._validate_style_keys(layer_name, 'text', text_style, known_style_keys)

        # Validate paragraph properties if present
        if 'paragraph' in text_style:
            known_paragraph_keys = {
                'align',
                'indent',
                'leftMargin',
                'rightMargin',
                'tabStops'
            }
            self._validate_style_keys(
                layer_name,
                'text.paragraph',
                text_style['paragraph'],
                known_paragraph_keys
            )

            # Validate alignment value
            if 'align' in text_style['paragraph']:
                alignment = text_style['paragraph']['align'].upper()
                if alignment not in VALID_TEXT_ALIGNMENTS:
                    log_warning(f"Invalid paragraph alignment '{alignment}' in layer {layer_name}. "
                              f"Valid values are: {', '.join(VALID_TEXT_ALIGNMENTS)}")

        # Validate attachment point value
        if 'attachmentPoint' in text_style:
            attachment_point = text_style['attachmentPoint'].upper()
            if attachment_point not in VALID_ATTACHMENT_POINTS:
                log_warning(f"Invalid attachment point '{attachment_point}' in layer {layer_name}. "
                          f"Valid values are: {', '.join(VALID_ATTACHMENT_POINTS)}")

        # Validate flow direction
        if 'flowDirection' in text_style:
            valid_flow_directions = {'LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE'}
            flow_direction = text_style['flowDirection'].upper()
            if flow_direction not in valid_flow_directions:
                log_warning(f"Invalid flow direction '{flow_direction}' in layer {layer_name}. "
                          f"Valid values are: {', '.join(valid_flow_directions)}")

        # Validate line spacing style
        if 'lineSpacingStyle' in text_style:
            spacing_style = text_style['lineSpacingStyle'].upper()
            if spacing_style not in TEXT_LINE_SPACING_STYLES:
                log_warning(f"Invalid line spacing style '{spacing_style}' in layer {layer_name}. "
                          f"Valid values are: {', '.join(TEXT_LINE_SPACING_STYLES.keys())}")

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
        """Get hatch configuration from layer info."""
        style_config = layer_info.get('style')
        if not style_config:
            return None

        hatch_config = {}
        
        # Get style configuration
        if isinstance(style_config, str):
            style, warning = self.get_style(style_config)
            if warning or not style:
                return None
            if 'hatch' in style:
                hatch_config.update(style['hatch'])
        elif isinstance(style_config, dict):
            if 'hatch' in style_config:
                hatch_config.update(style_config['hatch'])
            elif 'styleOverride' in style_config and 'hatch' in style_config['styleOverride']:
                preset_name = style_config.get('style')
                if preset_name:
                    preset = self.styles.get(preset_name)
                    if preset and 'hatch' in preset:
                        hatch_config.update(preset['hatch'])
                hatch_config.update(style_config['styleOverride']['hatch'])

        # If no hatch configuration found, return None
        if not hatch_config:
            return None

        # Add layer-specific hatch settings if they exist
        if 'hatch' in layer_info:
            hatch_config.update(layer_info['hatch'])

        return hatch_config

    def process_layer_style(self, layer_name, layer_config):
        """Process layer style with support for presets and inline styles.
        
        Returns:
            tuple: (layer_properties, entity_properties) where:
                - layer_properties: dict of properties to be set on the layer
                - entity_properties: dict of properties to be set on individual entities
        """
        # Initialize with default settings
        layer_properties = self.default_layer_settings.copy()
        entity_properties = self.default_entity_style.copy()
        
        if 'style' in layer_config:
            style_config = layer_config['style']
            
            # Process layer properties
            if 'layer' in style_config:
                layer_style = style_config['layer']
                for key in ['color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 
                           'is_on', 'transparency']:
                    if key in layer_style:
                        if key == 'color':
                            layer_properties[key] = get_color_code(layer_style[key], self.name_to_aci)
                        else:
                            layer_properties[key] = layer_style[key]
            
            # Process entity properties
            if 'entity' in style_config:
                entity_style = style_config['entity']
                for key in ['close', 'linetypeScale', 'linetypeGeneration']:
                    if key in entity_style:
                        entity_properties[key] = entity_style[key]
        
        log_debug(f"Processed style for layer {layer_name}:")
        log_debug(f"Layer properties: {layer_properties}")
        log_debug(f"Entity properties: {entity_properties}")
        
        return layer_properties, entity_properties

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