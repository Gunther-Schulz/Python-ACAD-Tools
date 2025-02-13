"""Module containing all default style settings for DXF entities."""

# Text attachment point mappings
TEXT_ATTACHMENT_POINTS = {
    'TOP_LEFT': 1, 'TOP_CENTER': 2, 'TOP_RIGHT': 3,
    'MIDDLE_LEFT': 4, 'MIDDLE_CENTER': 5, 'MIDDLE_RIGHT': 6,
    'BOTTOM_LEFT': 7, 'BOTTOM_CENTER': 8, 'BOTTOM_RIGHT': 9
}

# Valid text attachment points
VALID_ATTACHMENT_POINTS = {
    'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
    'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
    'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
}

# Text flow direction mappings
TEXT_FLOW_DIRECTIONS = {
    'LEFT_TO_RIGHT': 1,
    'TOP_TO_BOTTOM': 3,
    'BY_STYLE': 5
}

# Text line spacing style mappings
TEXT_LINE_SPACING_STYLES = {
    'AT_LEAST': 1,
    'EXACT': 2,
    'MULTIPLE': 3,
    'DEFAULT': 4
}

# Default text style properties
DEFAULT_TEXT_STYLE = {
    'height': 2.5,  # Default text height
    'font': 'Arial',  # Default font
    'color': 'white',  # Default color (ACI code 7)
    'attachmentPoint': 'MIDDLE_LEFT',  # Default attachment point
    'flowDirection': 'LEFT_TO_RIGHT',  # Default flow direction
    'lineSpacingStyle': 'AT_LEAST',  # Default line spacing style
    'lineSpacingFactor': 1.0,  # Default line spacing factor
    'bgFill': False,  # Default background fill setting
    'bgFillColor': None,  # Default background fill color
    'bgFillScale': 1.5,  # Default background fill scale
    'underline': False,  # Default underline setting
    'overline': False,  # Default overline setting
    'strikeThrough': False,  # Default strikethrough setting
    'obliqueAngle': 0,  # Default oblique angle
    'rotation': 0,  # Default rotation angle
    'paragraph': {
        'align': 'LEFT',  # Default alignment
        'indent': 0,  # Default indentation
        'leftMargin': 0,  # Default left margin
        'rightMargin': 0,  # Default right margin
        'tabStops': []  # Default tab stops
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
    'color': 'BYLAYER',  # Default color
    'linetype': 'BYLAYER',  # Default linetype
    'lineweight': 'BYLAYER',  # Default lineweight
    'transparency': 0,  # Default transparency
    'linetypeScale': 1.0  # Default linetype scale
}

# Default block reference properties
DEFAULT_BLOCK_STYLE = {
    'scale': 1.0,  # Default scale factor
    'rotation': 0.0,  # Default rotation angle
    'color': 'BYLAYER',  # Default color
    'linetype': 'BYLAYER',  # Default linetype
    'lineweight': 'BYLAYER'  # Default lineweight
}

# Default path array properties
DEFAULT_PATH_ARRAY_STYLE = {
    'scale': 1.0,  # Default scale factor
    'rotation': 0.0,  # Default rotation angle
    'spacing': 1.0,  # Default spacing between elements
    'align': True,  # Default alignment setting
    'tangent': True,  # Default tangent setting
    'adjustForVertices': False,  # Default vertex adjustment setting
    'pathOffset': 0.0,  # Default path offset
    'bufferDistance': 0.0  # Default buffer distance
}

# Valid style properties and their constraints
VALID_STYLE_PROPERTIES = {
    'text': {
        'height': {'min': 0.1, 'max': 1000.0},
        'lineSpacingFactor': {'min': 0.25, 'max': 4.0},
        'bgFillScale': {'min': 1.1, 'max': 5.0},
        'obliqueAngle': {'min': -85, 'max': 85},
        'rotation': {'min': -360, 'max': 360}
    },
    'layer': {
        'lineweight': {'min': -3, 'max': 211},
        'transparency': {'min': 0, 'max': 255},
        'linetypeScale': {'min': 0.01, 'max': 1000.0}
    },
    'hatch': {
        'scale': {'min': 0.01, 'max': 1000.0},
        'transparency': {'min': 0, 'max': 255},
        'lineweight': {'min': -3, 'max': 211}
    },
    'block': {
        'scale': {'min': 0.01, 'max': 1000.0},
        'rotation': {'min': -360, 'max': 360}
    },
    'path_array': {
        'scale': {'min': 0.01, 'max': 1000.0},
        'rotation': {'min': -360, 'max': 360},
        'spacing': {'min': 0.1, 'max': 1000.0},
        'pathOffset': {'min': -1000.0, 'max': 1000.0},
        'bufferDistance': {'min': 0.0, 'max': 1000.0}
    }
}

# Valid text alignments
VALID_TEXT_ALIGNMENTS = {
    'LEFT', 'RIGHT', 'CENTER', 'JUSTIFIED', 'DISTRIBUTED'
}

# Standard text styles (name, font, oblique angle)
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

# Default color mapping (fallback if aci_colors.yaml is not found)
DEFAULT_COLOR_MAPPING = {
    'white': 7,
    'red': 1,
    'yellow': 2,
    'green': 3,
    'cyan': 4,
    'blue': 5,
    'magenta': 6,
    'black': 0,
    'gray': 8,
    'light_gray': 9,
    'dark_gray': 250,
    'bylayer': 256,
    'byblock': 0
}

# Default layer names
DEFAULT_LAYER_NAMES = {
    'text': 'Text',  # Default layer for text entities
    'hatch': 'Hatch',  # Default layer for hatch entities
    'block': 'Blocks',  # Default layer for block references
    'viewport': 'VIEWPORTS',  # Default layer for viewports
    'legend': 'Legend'  # Default layer for legend elements
} 