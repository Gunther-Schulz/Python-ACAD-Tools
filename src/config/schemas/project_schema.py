"""Project configuration schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "crs": {"type": "string"},
        "dxfFilename": {"type": "string"},
        "exportFormat": {"type": "string", "enum": ["dxf", "shapefile"]},
        "dxfVersion": {"type": "string", "enum": ["R2010", "R2013", "R2018"]},
        "template": {"type": "string"},
        "shapefileOutputDir": {"type": "string"}
    },
    "required": ["crs", "dxfFilename", "exportFormat", "dxfVersion"],
    "additionalProperties": False
} 