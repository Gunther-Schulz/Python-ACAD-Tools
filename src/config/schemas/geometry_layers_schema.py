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
                    "simpleLabelColumn": {"type": "string"},
                    "style": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "object",
                             "properties": {
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
                                         "transparency": {"type": "integer"}
                                     }
                                 },
                                 "entity": {
                                     "type": "object",
                                     "properties": {
                                         "close": {"type": "boolean"},
                                         "linetypeScale": {"type": "number"},
                                         "linetypeGeneration": {"type": "boolean"}
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
                                 }
                             }
                            }
                        ]
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
                    "hatches": {
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