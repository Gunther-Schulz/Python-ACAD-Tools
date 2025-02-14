"""Module for managing styles in DXF files."""

from src.core.utils import log_warning, log_info, log_error, log_debug
from .utils import get_color_code, convert_transparency, deep_merge
from .utils.style_defaults import (
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
    """Manages styles for DXF entities and layers."""
    
    def __init__(self, project_loader):
        self.name_to_aci = project_loader.name_to_aci if hasattr(project_loader, 'name_to_aci') else {}
        self.styles = project_loader.styles if hasattr(project_loader, 'styles') else {}
        
        # Store defaults
        self.default_layer_style = DEFAULT_LAYER_STYLE.copy()
        self.default_entity_style = DEFAULT_ENTITY_STYLE.copy()
        self.default_text_style = DEFAULT_TEXT_STYLE.copy()
        self.default_hatch_style = DEFAULT_HATCH_STYLE.copy()

    def process_layer_style(self, layer_name, layer_config):
        """Process layer style configuration."""
        log_debug(f"Processing style for layer: {layer_name}")
        
        # Initialize with defaults
        style = {
            'layer': self.default_layer_style.copy(),
            'entity': self.default_entity_style.copy(),
            'text': self.default_text_style.copy(),
            'hatch': self.default_hatch_style.copy()
        }
        
        # Get style configuration
        style_config = layer_config.get('style', {})
        if not style_config:
            log_debug(f"No style configuration found for layer {layer_name}, using defaults")
            return style
            
        log_debug(f"Raw style configuration: {style_config}")
        
        # Handle string style references (presets)
        if isinstance(style_config, str):
            preset_style, warning_generated = self.get_style(style_config)
            if not warning_generated and preset_style:
                style = self.deep_merge(style, preset_style)
            return style
            
        # Handle style with overrides
        if 'styleOverride' in style_config:
            base_style = style_config.get('style', '')
            if base_style:
                preset_style, warning_generated = self.get_style(base_style)
                if not warning_generated and preset_style:
                    style = self.deep_merge(style, preset_style)
            # Apply overrides
            style = self.deep_merge(style, style_config['styleOverride'])
            return style
            
        # Process direct style configuration
        if 'layer' in style_config:
            self._process_layer_properties(style, style_config['layer'])
        if 'entity' in style_config:
            self._process_entity_properties(style, style_config['entity'])
        if 'text' in style_config:
            self._process_text_properties(style, style_config['text'])
        if 'hatch' in style_config:
            self._process_hatch_properties(style, style_config['hatch'])
        
        log_debug(f"Processed style: {style}")
        return style

    def _process_layer_properties(self, style, layer_props):
        """Process layer-specific properties."""
        valid_props = {
            'color', 'linetype', 'lineweight', 'plot', 
            'locked', 'frozen', 'is_on', 'transparency'
        }
        
        for key, value in layer_props.items():
            if key not in valid_props:
                log_warning(f"Unknown layer property: {key}")
                continue
                
            if key == 'color':
                style['layer'][key] = get_color_code(value, self.name_to_aci)
            elif key == 'transparency':
                style['layer'][key] = convert_transparency(value)
            else:
                style['layer'][key] = value

    def _process_entity_properties(self, style, entity_props):
        """Process entity-specific properties."""
        valid_props = {
            'color', 'linetype', 'lineweight', 'transparency',
            'linetypeScale', 'close', 'linetypeGeneration'
        }
        
        for key, value in entity_props.items():
            if key not in valid_props:
                log_warning(f"Unknown entity property: {key}")
                continue
                
            if key == 'color':
                style['entity'][key] = get_color_code(value, self.name_to_aci)
            elif key == 'linetypeScale':
                style['entity'][key] = float(value)
            elif key == 'transparency':
                style['entity'][key] = convert_transparency(value)
            else:
                style['entity'][key] = value

    def _process_text_properties(self, style, text_props):
        """Process text-specific properties."""
        if 'color' in text_props:
            style['text']['color'] = get_color_code(text_props['color'], self.name_to_aci)
        
        # Process other text properties
        for key, value in text_props.items():
            if key != 'color':  # Already handled
                style['text'][key] = value

    def _process_hatch_properties(self, style, hatch_props):
        """Process hatch-specific properties."""
        if 'color' in hatch_props:
            style['hatch']['color'] = get_color_code(hatch_props['color'], self.name_to_aci)
            
        # Process other hatch properties
        for key, value in hatch_props.items():
            if key != 'color':  # Already handled
                style['hatch'][key] = value

    def get_style(self, style_name_or_config):
        """Get style configuration with support for presets and inline styles."""
        if isinstance(style_name_or_config, str):
            style = self.styles.get(style_name_or_config)
            if style is None:
                log_warning(f"Style preset '{style_name_or_config}' not found.")
                return None, True
            return style, False
        elif isinstance(style_name_or_config, dict):
            return style_name_or_config, False
        return None, True

    def deep_merge(self, dict1, dict2):
        """Deep merge two dictionaries."""
        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            return dict2
            
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def validate_style(self, layer_name, style_config):
        """Validate style configuration.
        
        This is a simpler validation that just ensures the basic structure is correct.
        Detailed property validation happens during processing.
        """
        if not isinstance(style_config, dict):
            log_warning(f"Invalid style configuration for layer {layer_name}. Expected dict, got {type(style_config)}")
            return False
            
        valid_sections = {'layer', 'entity', 'text', 'hatch'}
        for section in style_config:
            if section not in valid_sections:
                log_warning(f"Unknown style section '{section}' in layer {layer_name}")
                return False
                
            if not isinstance(style_config[section], dict):
                log_warning(f"Invalid {section} style for layer {layer_name}. Expected dict, got {type(style_config[section])}")
                return False
                
        return True

    def _validate_layer_style(self, layer_name, style_config):
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
        hatch_config = self.default_hatch_style.copy()
        
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

    def process_text_style(self, layer_name, layer_config):
        style, warning_generated = self.get_style(layer_config.get('style', {}))
        if warning_generated:
            return {}
        return style.get('text', {}) if style else {}

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