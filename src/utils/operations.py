"""Utility functions for layer operations."""

from .logging import log_info

def print_layer_operations() -> None:
    """Print available layer operations and their options."""
    operations = {
        "copy": {
            "description": "Create a copy of one or more layers",
            "options": {
                "layers": "List of source layers to copy",
                "values": "List of values to filter the source layers"
            }
        },
        "buffer": {
            "description": "Create a buffer around geometries",
            "options": {
                "distance": "Buffer distance",
                "mode": "Buffer mode (outer, inner, keep, off)",
                "joinStyle": "Join style for buffer (round, mitre, bevel)"
            }
        },
        "difference": {
            "description": "Create a layer from the difference of two or more layers",
            "options": {
                "layers": "List of layers to perform difference operation"
            }
        },
        "intersection": {
            "description": "Create a layer from the intersection of two or more layers",
            "options": {
                "layers": "List of layers to perform intersection operation"
            }
        },
        "filter": {
            "description": "Filter geometries based on certain criteria",
            "options": {
                "layers": "List of layers to filter",
                "values": "List of values to filter the layers"
            }
        },
        "wmts": {
            "description": "Add a Web Map Tile Service layer",
            "options": {
                "url": "WMTS service URL",
                "layer": "WMTS layer name",
                "srs": "Spatial Reference System",
                "format": "Image format",
                "targetFolder": "Folder to store downloaded tiles",
                "buffer": "Buffer distance for processing area",
                "zoom": "Zoom level",
                "overwrite": "Whether to overwrite existing tiles",
                "postProcess": {
                    "colorMap": "Map colors in the image",
                    "alphaColor": "Set a color to be fully transparent",
                    "grayscale": "Convert image to grayscale",
                    "removeText": "Remove text from the image"
                }
            }
        },
        "wms": {
            "description": "Add a Web Map Service layer",
            "options": {
                "url": "WMS service URL",
                "layer": "WMS layer name",
                "srs": "Spatial Reference System",
                "format": "Image format",
                "targetFolder": "Folder to store downloaded images",
                "buffer": "Buffer distance for processing area",
                "zoom": "Zoom level",
                "overwrite": "Whether to overwrite existing images",
                "postProcess": {
                    "colorMap": "Map colors in the image",
                    "alphaColor": "Set a color to be fully transparent",
                    "grayscale": "Convert image to grayscale",
                    "removeText": "Remove text from the image"
                }
            }
        },
        "merge": {
            "description": "Merge multiple layers into one",
            "options": {
                "layers": "List of layers to merge"
            }
        },
        "smooth": {
            "description": "Smooth geometries in a layer",
            "options": {
                "strength": "Smoothing strength"
            }
        },
        "contour": {
            "description": "Generate contour lines from elevation data",
            "options": {
                "url": "URL to ATOM feed with elevation data",
                "layers": "List of layers to process",
                "buffer": "Buffer distance for processing area"
            }
        }
    }

    log_info("Available Layer Operations:")
    for op, details in operations.items():
        log_info(f"\n{op.upper()}:")
        log_info(f"  Description: {details['description']}")
        log_info("  Options:")
        for option, description in details['options'].items():
            if isinstance(description, dict):
                log_info(f"    - {option}:")
                for sub_option, sub_description in description.items():
                    log_info(f"      - {sub_option}: {sub_description}")
            else:
                log_info(f"    - {option}: {description}")

def print_layer_settings() -> None:
    """Print available layer settings and their options."""
    settings = {
        "name": {
            "description": "Name of the layer",
            "type": "string"
        },
        "updateDxf": {
            "description": "Whether to update the layer in the DXF file",
            "type": "boolean"
        },
        "shapeFile": {
            "description": "Path to the shapefile for this layer",
            "type": "string"
        },
        "dxfLayer": {
            "description": "Name of the DXF layer to use",
            "type": "string"
        },
        "outputShapeFile": {
            "description": "Path to save the output shapefile",
            "type": "string"
        },
        "style": {
            "description": "Style settings for the layer",
            "options": {
                "color": "Color of the layer (name or ACI code)",
                "linetype": "Line type for the layer",
                "lineweight": "Line weight for the layer",
                "plot": "Whether to plot this layer",
                "locked": "Whether the layer is locked",
                "frozen": "Whether the layer is frozen",
                "is_on": "Whether the layer is visible",
                "transparency": "Transparency of the layer (0.0 to 1.0)"
            }
        },
        "labelStyle": {
            "description": "Style settings for labels",
            "options": {
                "color": "Color of the labels (name or ACI code)",
                "size": "Size of the label text",
                "font": "Font for the label text"
            }
        },
        "label": {
            "description": "Column to use for labels",
            "type": "string"
        },
        "close": {
            "description": "Whether to close polygons",
            "type": "boolean"
        },
        "linetypeScale": {
            "description": "Scale factor for line types",
            "type": "float"
        },
        "linetypeGeneration": {
            "description": "Whether to generate line types",
            "type": "boolean"
        },
        "operations": {
            "description": "List of operations to perform on the layer",
            "type": "list of operation objects"
        }
    }

    log_info("Available Layer Settings:")
    for setting, details in settings.items():
        log_info(f"\n{setting.upper()}:")
        log_info(f"  Description: {details['description']}")
        if 'type' in details:
            log_info(f"  Type: {details['type']}")
        if 'options' in details:
            log_info("  Options:")
            for option, description in details['options'].items():
                log_info(f"    - {option}: {description}") 