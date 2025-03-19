"""
Style management for OLADPP.
Handles layer styles, hatch styles, and text styles.
"""
from typing import Dict, Any, Tuple, Optional
import re
from ..core.exceptions import StyleError
from ..utils.logging import log_info, log_warning, log_debug, log_error


class StyleManager:
    """Manages styles for layers, hatches, and text in OLADPP."""

    def __init__(self, project_settings: Dict[str, Any]):
        """Initialize StyleManager with project settings.

        Args:
            project_settings: Dictionary containing project settings including styles
        """
        self.styles = project_settings.get('styles', {})
        self.name_to_aci = project_settings.get('name_to_aci', {
            'white': 7, 'red': 1, 'yellow': 2, 'green': 3,
            'cyan': 4, 'blue': 5, 'magenta': 6
        })

        # Default settings
        self.default_hatch_settings = {
            'pattern': 'SOLID',
            'scale': 1,
            'color': 'BYLAYER',
            'individual_hatches': True
        }

        self.default_layer_settings = {
            'color': 'White',
            'linetype': 'CONTINUOUS',
            'lineweight': 13,
            'plot': True,
            'locked': False,
            'frozen': False,
            'is_on': True,
            'transparency': 0,
            'close': True,
            'linetypeScale': 1.0
        }

    def get_style(self, style_name_or_config: Any) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Get a style configuration by name or handle inline style config.

        Args:
            style_name_or_config: Either a style name string or a style configuration dict

        Returns:
            Tuple of (style configuration, warning flag)
        """
        if isinstance(style_name_or_config, str):
            # Handle preset style
            style = self.styles.get(style_name_or_config)
            if style is None:
                log_warning(f"Style preset '{style_name_or_config}' not found.")
                return None, True
            return style, False
        elif isinstance(style_name_or_config, dict):
            if 'preset' in style_name_or_config:
                # Handle preset with overrides (backward compatibility)
                preset_name = style_name_or_config['preset']
                preset = self.styles.get(preset_name)
                if preset is None:
                    log_warning(f"Style preset '{preset_name}' not found.")
                    return style_name_or_config, True

                # Remove preset key and merge with overrides
                overrides = dict(style_name_or_config)
                del overrides['preset']
                return self.deep_merge(preset, overrides), False
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

                return self.deep_merge(preset, style_name_or_config['styleOverride']), False
            else:
                # Handle pure inline style
                return style_name_or_config, False

        return style_name_or_config, False

    def validate_style(self, layer_name: str, style_config: Any) -> bool:
        """Validate the complete style configuration for a layer.

        Args:
            layer_name: Name of the layer
            style_config: Style configuration to validate

        Returns:
            bool: True if valid, False otherwise
        """
        if isinstance(style_config, str):
            # Validate preset style
            style, warning_generated = self.get_style(style_config)
            if warning_generated:
                return False
        elif isinstance(style_config, dict):
            # Validate inline style or style with overrides
            if 'preset' in style_config:
                preset_style, warning_generated = self.get_style(style_config['preset'])
                if warning_generated:
                    return False
                self._validate_style_overrides(layer_name, style_config)
            elif 'styleOverride' in style_config:
                if 'style' not in style_config or not isinstance(style_config['style'], str):
                    log_warning(f"Layer '{layer_name}' has styleOverride but no valid preset name in 'style' key")
                    return False
                preset_style, warning_generated = self.get_style(style_config['style'])
                if warning_generated:
                    return False
                self._validate_style_overrides(layer_name, style_config['styleOverride'])
            else:
                # Handle pure inline style
                for style_type, style_dict in style_config.items():
                    self._validate_style_type(layer_name, style_type, style_dict)

        return True

    def _validate_style_type(self, layer_name: str, style_type: str, style_dict: Dict[str, Any]) -> None:
        """
        Validate a specific style type.

        Args:
            layer_name: Name of the layer
            style_type: Type of style to validate
            style_dict: Style dictionary to validate
        """
        if style_type == 'layer':
            self._validate_layer_style(layer_name, style_dict)
        elif style_type == 'hatch':
            self._validate_hatch_style(layer_name, style_dict)
        elif style_type == 'text':
            self._validate_text_style(layer_name, style_dict)
        else:
            log_warning(f"Unknown style type '{style_type}' in layer '{layer_name}'")

    def _validate_enum_value(
        self,
        layer_name: str,
        style_type: str,
        field: str,
        value: str,
        valid_values: set,
        case_sensitive: bool = False
    ) -> None:
        """
        Validate an enum-style value against a set of valid values.

        Args:
            layer_name: Name of the layer
            style_type: Type of style being validated
            field: Field name being validated
            value: Value to validate
            valid_values: Set of valid values
            case_sensitive: Whether to do case-sensitive comparison
        """
        if not case_sensitive:
            value = value.upper()
            valid_values = {v.upper() for v in valid_values}

        if value not in valid_values:
            log_warning(
                f"Invalid {style_type} {field} '{value}' in layer {layer_name}. "
                f"Valid values are: {', '.join(valid_values)}"
            )

    def _validate_layer_style(self, layer_name: str, layer_style: Dict[str, Any]) -> None:
        """Validate layer style configuration."""
        known_style_keys = {
            'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen',
            'is_on', 'transparency', 'linetypeScale'
        }
        self._validate_style_keys(layer_name, 'layer', layer_style, known_style_keys)

        # Validate linetype
        if 'linetype' in layer_style:
            linetype = layer_style['linetype']
            if linetype.startswith('ACAD_'):
                acad_pattern = r'^ACAD_ISO\d{2}W100$'
                if not re.match(acad_pattern, linetype):
                    log_warning(
                        f"Invalid ACAD linetype format '{linetype}' in layer '{layer_name}'. "
                        "ACAD ISO linetypes should follow the pattern 'ACAD_ISOxxW100' "
                        "where xx is a two-digit number."
                    )

    def _validate_hatch_style(self, layer_name: str, hatch_style: Dict[str, Any]) -> None:
        """Validate hatch style configuration."""
        known_style_keys = {
            'pattern', 'scale', 'color', 'transparency',
            'individual_hatches', 'layers', 'lineweight'
        }
        self._validate_style_keys(layer_name, 'hatch', hatch_style, known_style_keys)

    def _validate_text_style(self, layer_name: str, text_style: Dict[str, Any]) -> None:
        """Validate text style configuration."""
        known_style_keys = {
            'color', 'height', 'font', 'maxWidth', 'attachmentPoint',
            'flowDirection', 'lineSpacingStyle', 'lineSpacingFactor',
            'bgFill', 'bgFillColor', 'bgFillScale', 'underline',
            'overline', 'strikeThrough', 'obliqueAngle', 'rotation',
            'paragraph'
        }

        self._validate_style_keys(layer_name, 'text', text_style, known_style_keys)

        # Validate paragraph properties
        if 'paragraph' in text_style:
            known_paragraph_keys = {
                'align', 'indent', 'leftMargin', 'rightMargin', 'tabStops'
            }
            self._validate_style_keys(
                layer_name,
                'text.paragraph',
                text_style['paragraph'],
                known_paragraph_keys
            )

            # Validate alignment
            if 'align' in text_style['paragraph']:
                self._validate_enum_value(
                    layer_name,
                    'text.paragraph',
                    'align',
                    text_style['paragraph']['align'],
                    {'LEFT', 'RIGHT', 'CENTER', 'JUSTIFIED', 'DISTRIBUTED'}
                )

        # Validate attachment point
        if 'attachmentPoint' in text_style:
            self._validate_enum_value(
                layer_name,
                'text',
                'attachmentPoint',
                text_style['attachmentPoint'],
                {
                    'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
                    'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
                    'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
                }
            )

        # Validate flow direction
        if 'flowDirection' in text_style:
            self._validate_enum_value(
                layer_name,
                'text',
                'flowDirection',
                text_style['flowDirection'],
                {'LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE'}
            )

        # Validate line spacing style
        if 'lineSpacingStyle' in text_style:
            self._validate_enum_value(
                layer_name,
                'text',
                'lineSpacingStyle',
                text_style['lineSpacingStyle'],
                {'AT_LEAST', 'EXACT'}
            )

    def _validate_style_keys(self, layer_name: str, style_type: str,
                           style_dict: Dict[str, Any], known_keys: set) -> None:
        """Validate style keys against known keys."""
        unknown_keys = set(style_dict.keys()) - known_keys
        if unknown_keys:
            log_warning(
                f"Unknown {style_type} style keys in layer {layer_name}: "
                f"{', '.join(unknown_keys)}"
            )

        for key in style_dict.keys():
            closest_match = min(known_keys, key=lambda x: self._levenshtein_distance(key, x))
            if key != closest_match and self._levenshtein_distance(key, closest_match) <= 2:
                log_warning(
                    f"Possible typo in {style_type} style key for layer {layer_name}: "
                    f"'{key}'. Did you mean '{closest_match}'?"
                )

    def _validate_style_overrides(self, layer_name: str, style_config: Dict[str, Any]) -> None:
        """Validate style override configuration."""
        for style_type, style_dict in style_config.items():
            self._validate_style_type(layer_name, style_type, style_dict)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
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

    def deep_merge(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = value
        return result
