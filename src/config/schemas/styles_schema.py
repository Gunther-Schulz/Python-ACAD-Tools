"""Styles configuration schema."""

# Common style schema that can be reused
STYLE_PROPERTIES = {
    "layer": {
        "type": "object",
        "properties": {
            "color": {"type": "string"},
            "linetype": {"type": "string"},
            "lineweight": {"type": "integer"},
            "plot": {"type": "boolean"},
            "locked": {"type": "boolean"},
            "frozen": {"type": "boolean"},
            "is_on": {"type": "boolean"},
            "transparency": {"type": "number"}
        }
    },
    "polygon": {
        "type": "object",
        "properties": {
            "close": {"type": "boolean"},
            "linetypeScale": {"type": "number"},
            "linetypeGeneration": {"type": "boolean"},
            "color": {"type": "string"},
            "transparency": {"type": "number"},
            "linetype": {"type": "string"},
            "lineweight": {"type": "integer"}
        }
    },
    "text": {
        "type": "object",
        "properties": {
            "height": {"type": "number"},
            "font": {"type": "string"},
            "style": {"type": "string"},
            "color": {"type": "string"},
            "attachmentPoint": {"type": "string"},
            "paragraph": {
                "type": "object",
                "properties": {
                    "align": {"type": "string"}
                }
            }
        }
    },
    "hatch": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "scale": {"type": "number"},
            "rotation": {"type": "number"},
            "color": {"type": "string"}
        }
    }
}

# Main schema for styles configuration
SCHEMA = {
    "type": "object",
    "properties": {
        "styles": {
            "type": "object",
            "patternProperties": {
                "^[a-zA-Z0-9_]+$": {
                    "type": "object",
                    "properties": STYLE_PROPERTIES
                }
            }
        }
    },
    "required": ["styles"],
    "additionalProperties": False
} 