"""Geometry layers configuration schema."""

from .styles_schema import STYLE_PROPERTIES

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
                    "simpleLabelColumn": {"type": "string"},
                    "style": {"type": "string"},
                    "inlineStyle": {
                        "type": "object",
                        "properties": STYLE_PROPERTIES
                    },
                    "viewports": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "style": {"type": "string"}
                            },
                            "required": ["name"]
                        }
                    },
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "layers": {
                                    "oneOf": [
                                        {
                                            "type": "array",
                                            "items": {
                                                "oneOf": [
                                                    {"type": "string"},
                                                    {
                                                        "type": "object",
                                                        "properties": {
                                                            "name": {"type": "string"},
                                                            "values": {
                                                                "type": "array",
                                                                "items": {"type": "string"}
                                                            }
                                                        },
                                                        "required": ["name"]
                                                    }
                                                ]
                                            }
                                        },
                                        {"type": "string"}
                                    ]
                                },
                                "distance": {"type": "number"},
                                "reverseDifference": {
                                    "oneOf": [
                                        {"type": "boolean"},
                                        {"type": "string", "enum": ["auto"]}
                                    ]
                                },
                                "useBufferTrick": {"type": "boolean"},
                                "bufferDistance": {"type": "number"},
                                "useAsymmetricBuffer": {"type": "boolean"},
                                "minArea": {"type": "number"},
                                "params": {"type": "object"}
                            },
                            "required": ["type"]
                        }
                    },
                    "hatchLayers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "style": {"type": "string"},
                                "pattern": {"type": "string"},
                                "scale": {"type": "number"},
                                "rotation": {"type": "number"}
                            },
                            "required": ["name"]
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