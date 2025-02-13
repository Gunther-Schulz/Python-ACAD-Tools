"""Module containing all default style settings for DXF entities."""

# Default text style properties
DEFAULT_TEXT_STYLE = {
    'height': 2.5,  # Default text height
    'font': 'Arial',  # Default font
    'color': 'white',  # Default color (ACI code 7)
    'attachmentPoint': 'MIDDLE_LEFT',  # Default attachment point
    'paragraph': {
        'align': 'LEFT'  # Default alignment
    }
}

# Default layer style properties
DEFAULT_LAYER_STYLE = {
    'color': 'white',  # Default color (ACI code 7)
    'linetype': 'CONTINUOUS',  # Default linetype
    'lineweight': 13,  # Default lineweight
    'plot': True,  # Default plot setting
    'locked': False,  # Default lock setting
    'frozen': False,  # Default freeze setting
    'is_on': True,  # Default visibility
    'transparency': 0,  # Default transparency
    'close': True,  # Default close setting
    'linetypeScale': 1.0  # Default linetype scale
}

# Default hatch style properties
DEFAULT_HATCH_STYLE = {
    'pattern': 'SOLID',  # Default hatch pattern
    'scale': 1,  # Default pattern scale
    'color': 'BYLAYER',  # Default color
    'transparency': 0,  # Default transparency
    'individual_hatches': True,  # Default individual hatches setting
    'lineweight': 13  # Default lineweight
}

# Default entity style properties (for non-specific entities)
DEFAULT_ENTITY_STYLE = {
    'color': 'BYLAYER',
    'linetype': 'BYLAYER',
    'lineweight': 'BYLAYER',
    'transparency': 0,
    'linetypeScale': 1.0
}

# Valid style properties and their allowed values
VALID_STYLE_PROPERTIES = {
    'text': {
        'color': str,  # Color name or RGB tuple
        'height': (int, float),
        'font': str,
        'maxWidth': (int, float),
        'attachmentPoint': {
            'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
            'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
            'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
        },
        'flowDirection': {'LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE'},
        'lineSpacingStyle': {'AT_LEAST', 'EXACT'},
        'lineSpacingFactor': (float, (0.25, 4.00)),  # (type, (min, max))
        'bgFill': bool,
        'bgFillColor': str,
        'bgFillScale': (float, (0.1, 5.0)),
        'underline': bool,
        'overline': bool,
        'strikeThrough': bool,
        'obliqueAngle': (float, (-85, 85)),
        'rotation': (float, (0, 360))
    },
    'layer': {
        'color': str,
        'linetype': str,
        'lineweight': (int, float),
        'plot': bool,
        'locked': bool,
        'frozen': bool,
        'is_on': bool,
        'transparency': (int, (0, 100)),
        'linetypeScale': (float, (0.01, 1000.0))
    },
    'hatch': {
        'pattern': str,
        'scale': (float, (0.01, 1000.0)),
        'color': str,
        'transparency': (int, (0, 100)),
        'individual_hatches': bool,
        'lineweight': (int, float)
    }
}

# Default paragraph properties for text
DEFAULT_PARAGRAPH_STYLE = {
    'align': 'LEFT',
    'indent': 0,
    'leftMargin': 0,
    'rightMargin': 0,
    'tabStops': []
}

# Mapping of color names to ACI codes (fallback if aci_colors.yaml is not found)
DEFAULT_COLOR_MAPPING = {
    'white': 7,
    'red': 1,
    'yellow': 2,
    'green': 3,
    'cyan': 4,
    'blue': 5,
    'magenta': 6
}

# Standard text styles to be loaded into DXF documents
STANDARD_TEXT_STYLES = [
    ('Standard', 'Arial', 0.0),
    ('Arial', 'Arial', 0.0),
    ('Arial Narrow', 'Arial Narrow', 0.0),
    ('Isocpeur', 'Isocpeur', 0.0),
    ('Isocp', 'Isocp', 0.0),
    ('Romantic', 'Romantic', 0.0),
    ('Romans', 'Romans', 0.0),
    ('Romand', 'Romand', 0.0),
    ('Romant', 'Romant', 0.0)
] 