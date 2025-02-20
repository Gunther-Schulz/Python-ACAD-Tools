"""Additional configuration schemas."""

LEGENDS_SCHEMA = {
    "type": "object",
    "properties": {
        "legends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "position": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"}
                        },
                        "required": ["x", "y"]
                    },
                    "style": {"type": "string"}
                },
                "required": ["name", "position"]
            }
        }
    }
}

VIEWPORTS_SCHEMA = {
    "type": "object",
    "properties": {
        "viewports": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "center": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"}
                        },
                        "required": ["x", "y"]
                    },
                    "scale": {"type": "number"},
                    "rotation": {"type": "number", "default": 0}
                },
                "required": ["name", "center", "scale"]
            }
        }
    }
}

BLOCK_INSERTS_SCHEMA = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "position": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"}
                        },
                        "required": ["x", "y"]
                    },
                    "scale": {"type": "number", "default": 1.0},
                    "rotation": {"type": "number", "default": 0},
                    "layer": {"type": "string"}
                },
                "required": ["name", "position"]
            }
        }
    }
}

TEXT_INSERTS_SCHEMA = {
    "type": "object",
    "properties": {
        "texts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "position": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"}
                        },
                        "required": ["x", "y"]
                    },
                    "style": {"type": "string"},
                    "layer": {"type": "string"}
                },
                "required": ["text", "position"]
            }
        }
    }
}

PATH_ARRAYS_SCHEMA = {
    "type": "object",
    "properties": {
        "pathArrays": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                    "block": {"type": "string"},
                    "spacing": {"type": "number"},
                    "align": {"type": "boolean", "default": True},
                    "layer": {"type": "string"}
                },
                "required": ["name", "path", "block", "spacing"]
            }
        }
    }
}

WMTS_WMS_LAYERS_SCHEMA = {
    "type": "object",
    "properties": {
        "services": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["wmts", "wms"]},
                    "url": {"type": "string"},
                    "layer": {"type": "string"},
                    "style": {"type": "string"},
                    "format": {"type": "string", "default": "image/png"},
                    "crs": {"type": "string"}
                },
                "required": ["name", "type", "url", "layer", "crs"]
            }
        }
    }
} 