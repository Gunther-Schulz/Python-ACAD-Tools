import sys
from ezdxf.addons import odafc
import argparse
from fiona.errors import DriverIOError
import yaml
import os
import traceback

from src.project_loader import ProjectLoader
from src.layer_processor import LayerProcessor
from src.dxf_exporter import DXFExporter
from src.utils import log_error, setup_logging, setup_proj
from src.dump_to_shape import dxf_to_shapefiles

import src.easyocr_patch

class ProjectProcessor:
    def __init__(self, project_name: str, plot_ops=False):
        self.project_loader = ProjectLoader(project_name)
        self.layer_processor = LayerProcessor(self.project_loader, plot_ops)
        self.dxf_exporter = DXFExporter(self.project_loader, self.layer_processor)

    def run(self):
        self.layer_processor.process_layers()
        self.dxf_exporter.export_to_dxf()
        
        # Run the dumping process after exporting to DXF
        project_settings = self.project_loader.project_settings
        folder_prefix = self.project_loader.folder_prefix
        dxf_filename = self.project_loader.dxf_filename
        
        if 'dumpOutputDir' not in project_settings:
            print("Skipping DXF dump: 'dumpOutputDir' not specified in project configuration.")
            return

        dump_output_dir = os.path.expanduser(os.path.join(folder_prefix, project_settings['dumpOutputDir']))
        
        print(f"DXF filename: {dxf_filename}")
        print(f"Dump output directory: {dump_output_dir}")
        
        if os.path.exists(dxf_filename):
            print(f"DXF file exists: {dxf_filename}")
        else:
            print(f"DXF file does not exist: {dxf_filename}")
        
        if os.path.exists(dxf_filename) and dump_output_dir:
            print(f"Dumping DXF to shapefiles: {dxf_filename} -> {dump_output_dir}")
            dxf_to_shapefiles(dxf_filename, dump_output_dir)
        else:
            print("Skipping DXF dump: DXF file not found or dump output directory not specified.")
            if not os.path.exists(dxf_filename):
                print(f"DXF file does not exist: {dxf_filename}")
            if not dump_output_dir:
                print("Dump output directory not specified.")

def print_layer_operations():
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

    print("Available Layer Operations:")
    for op, details in operations.items():
        print(f"\n{op.upper()}:")
        print(f"  Description: {details['description']}")
        print("  Options:")
        for option, description in details['options'].items():
            if isinstance(description, dict):
                print(f"    - {option}:")
                for sub_option, sub_description in description.items():
                    print(f"      - {sub_option}: {sub_description}")
            else:
                print(f"    - {option}: {description}")

def main():
    setup_logging()
    setup_proj()

    parser = argparse.ArgumentParser(description="Process and export project data to DXF.")
    parser.add_argument("project_name", nargs="?", help="Name of the project to process")
    parser.add_argument('--plot-ops', action='store_true', help="Plot the result of each operation")
    parser.add_argument('-l', '--list-operations', action='store_true', help="List all possible layer operations and their options")
    args = parser.parse_args()

    if args.list_operations:
        print_layer_operations()
        return

    if not args.project_name:
        parser.error("project_name is required unless --list-operations is specified")

    print(f"Processing project: {args.project_name}")

    try:
        processor = ProjectProcessor(args.project_name, plot_ops=args.plot_ops)
        processor.run()
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        traceback_str = traceback.format_exc()
        
        log_error(f"Error Type: {error_type}")
        log_error(f"Error Message: {error_message}")
        log_error(f"Traceback:\n{traceback_str}")
        
        print(f"An error occurred: {error_type}")
        print(f"Error details: {error_message}")
        print("Check the log file for the full traceback.")
        
        sys.exit(1)

if __name__ == "__main__":
    main()