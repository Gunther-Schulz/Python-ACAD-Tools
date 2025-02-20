"""Geometry layers configuration schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "geomLayers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "updateDxf": {"type": "boolean", "default": True},
                    "close": {"type": "boolean", "default": False},
                    "shapeFile": {"type": "string"},
                    "simpleLabel": {"type": "boolean", "default": False},
                    "style": {"type": "string"},
                    "viewports": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "params": {"type": "object"}
                            },
                            "required": ["type"]
                        }
                    },
                    "hatches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pattern": {"type": "string"},
                                "scale": {"type": "number"},
                                "rotation": {"type": "number"}
                            },
                            "required": ["pattern"]
                        }
                    }
                },
                "required": ["name"]
            }
        }
    },
    "required": ["geomLayers"],
    "additionalProperties": False
} 