"""Styles configuration schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "styles": {
            "type": "object",
            "patternProperties": {
                "^[a-zA-Z0-9_]+$": {
                    "type": "object",
                    "properties": {
                        "layer": {
                            "type": "object",
                            "properties": {
                                "color": {"type": "string"},
                                "lineweight": {"type": "number"},
                                "linetype": {"type": "string"}
                            }
                        },
                        "entity": {
                            "type": "object",
                            "properties": {
                                "close": {"type": "boolean"},
                                "elevation": {"type": "number"},
                                "color": {"type": "string"}
                            }
                        },
                        "text": {
                            "type": "object",
                            "properties": {
                                "height": {"type": "number"},
                                "color": {"type": "string"},
                                "style": {"type": "string"},
                                "rotation": {"type": "number"},
                                "alignment": {"type": "string"}
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
                }
            }
        }
    },
    "required": ["styles"],
    "additionalProperties": False
} 