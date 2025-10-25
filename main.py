import sys
import argparse
import os
import traceback

from src.project_loader import ProjectLoader
from src.layer_processor import LayerProcessor
from src.dxf_exporter import DXFExporter
from src.utils import create_sample_project, log_error, log_info, setup_logging, setup_proj, set_log_level, log_debug, set_profiling_enabled
from src.dump_to_shape import dxf_to_shapefiles
from src.dxf_utils import cleanup_document

class ProjectProcessor:
    def __init__(self, project_name: str, plot_ops=False, skip_dxf=False, enable_profiling=False):
        try:
            # Set profiling state early
            set_profiling_enabled(enable_profiling)

            self.project_loader = ProjectLoader(project_name)
            if not self.project_loader.project_settings:
                raise ValueError(f"Could not load settings for project '{project_name}'. Please check if the project files exist and are valid YAML.")

            # Initialize LayerProcessor first
            self.layer_processor = LayerProcessor(self.project_loader, plot_ops)

            # Pass the initialized LayerProcessor to DXFExporter only if not skipping DXF
            self.skip_dxf = skip_dxf
            if not skip_dxf:
                self.dxf_exporter = DXFExporter(self.project_loader, self.layer_processor)
            else:
                self.dxf_exporter = None

            self.doc = None  # Add this to store the document reference

        except Exception as e:
            available_projects = list_available_projects()
            error_msg = f"Error initializing project '{project_name}': {str(e)}\n"
            if available_projects:
                error_msg += "\nAvailable projects:\n" + "\n".join(f"  - {p}" for p in available_projects)
            else:
                error_msg += "\nNo projects found. Use --create-project to create a new project."

            # Log the full traceback before raising the error
            log_error(f"Error initializing project '{project_name}':")
            log_error(f"Error details: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")

            raise ValueError(error_msg) from e

    def run(self):
        if self.skip_dxf:
            # Only process layers without DXF operations
            log_info("Skipping DXF generation - processing geometries and shapefiles only")
            self.layer_processor.process_layers()
        else:
            # Load the document and process DXF operations early
            doc = self.dxf_exporter._load_or_create_dxf(skip_dxf_processor=False)
            self.layer_processor.set_dxf_document(doc)
            self.layer_processor.process_layers()
            self.dxf_exporter.export_to_dxf()

        project_settings = self.project_loader.project_settings
        folder_prefix = self.project_loader.folder_prefix
        dxf_filename = self.project_loader.dxf_filename

        if 'dxfDumpOutputDir' in project_settings:
            dump_output_dir = os.path.expanduser(os.path.join(folder_prefix, project_settings['dxfDumpOutputDir']))
            geometry_types = project_settings.get('dxfDumpGeometryTypes', None)

            if os.path.exists(dxf_filename) and dump_output_dir:
                if geometry_types:
                    log_info(f"Dumping DXF to shapefiles (geometry types: {', '.join(geometry_types)}): {dxf_filename} -> {dump_output_dir}")
                else:
                    log_info(f"Dumping DXF to shapefiles: {dxf_filename} -> {dump_output_dir}")
                dxf_to_shapefiles(dxf_filename, dump_output_dir, geometry_types=geometry_types)
            else:
                log_info("Skipping DXF dump: DXF file not found or dump output directory not specified.")

    def process(self):
        # Load the document and process DXF operations early
        doc = self.dxf_exporter._load_or_create_dxf(skip_dxf_processor=False)
        self.layer_processor.set_dxf_document(doc)
        self.layer_processor.process_layers()

        # Pass skip_dxf_processor=True to avoid second processing
        self.dxf_exporter.export_to_dxf(skip_dxf_processor=True)

        # Store and return the document reference
        self.doc = doc
        return doc

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

def print_layer_settings():
    settings = {
        "name": {
            "description": "Name of the layer",
            "type": "string"
        },
        "sync": {
            "description": "Sync mode: 'push' (write to DXF), 'pull' (read from DXF), 'auto' (bidirectional), 'skip' (no sync)",
            "type": "string"
        },
        "shapeFile": {
            "description": "Path to the shapefile for this layer",
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

def list_available_projects():
    projects_dir = 'projects'
    if not os.path.exists(projects_dir):
        os.makedirs(projects_dir)
        log_info(f"Created projects directory: {projects_dir}")
        return []

    projects = []
    for file in os.listdir(projects_dir):
        if file.endswith('.yaml'):
            projects.append(file[:-5])  # Remove .yaml extension
    return projects

def main():
    parser = argparse.ArgumentParser(description="Process and export project data to DXF.")
    parser.add_argument("project_name", nargs="?", help="Name of the project to process")
    parser.add_argument('--plot-ops', action='store_true', help="Plot the result of each operation")
    parser.add_argument('--cleanup', action='store_true', help="Perform thorough document cleanup after processing")
    parser.add_argument('--skip-dxf', action='store_true', help="Skip DXF generation and only process geometries/shapefiles")
    parser.add_argument('--profile', action='store_true', help="Enable performance profiling (logs to logs/performance.log)")
    parser.add_argument('-l', '--list-operations', action='store_true', help="List all possible layer operations and their options")
    parser.add_argument('-s', '--list-settings', action='store_true', help="List all possible layer settings and their options")
    parser.add_argument('--list-projects', action='store_true', help="List all available projects")
    parser.add_argument('--create-project', action='store_true', help="Create a new project with basic settings")
    parser.add_argument('--log-level',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO',
                       help='Set the logging level')
    args = parser.parse_args()

    # Initialize logging with the specified level
    setup_logging(args.log_level)
    set_log_level(args.log_level)

    if args.list_projects:
        projects = list_available_projects()
        if projects:
            log_info("Available projects:")
            for project in projects:
                log_info(f"  - {project}")
        else:
            log_info("No projects found.")
        return

    if args.list_operations:
        print_layer_operations()
        return

    if args.list_settings:
        print_layer_settings()
        return

    if not args.project_name:
        parser.error("project_name is required unless --list-operations, --list-settings, or --list-projects is specified")

    if args.create_project:
        # Check if project already exists
        project_dir = os.path.join('projects', args.project_name)
        if os.path.exists(project_dir):
            log_info(f"\nError: Project '{args.project_name}' already exists at: {project_dir}")
            log_info("Please choose a different project name or remove the existing project directory.")
            sys.exit(1)

        project_dir = create_sample_project(args.project_name)
        log_info(f"\nCreated new project directory: {project_dir}")
        log_info("\nThe following files were created with sample configurations:")
        log_info("  - project.yaml         (required core settings)")
        log_info("  - geom_layers.yaml     (geometry layer definitions)")
        log_info("  - legends.yaml         (legend configurations)")
        log_info("  - viewports.yaml       (viewport settings)")
        log_info("  - block_inserts.yaml   (block insertion definitions)")
        log_info("  - text_inserts.yaml    (text insertion definitions)")
        log_info("  - path_arrays.yaml     (path array definitions)")
        log_info("  - web_services.yaml    (WMS/WMTS service configurations)")
        log_info("\nPlease edit these files with your project-specific settings.")
        return

    log_info(f"Processing project: {args.project_name}")

    try:
        if args.project_name:
            processor = ProjectProcessor(args.project_name, args.plot_ops, args.skip_dxf, args.profile)
            processor.run()

            # Add cleanup step if requested (only if DXF was generated)
            if args.cleanup and not args.skip_dxf:
                log_debug("Performing document cleanup...")
                cleanup_document(processor.doc)
                log_debug("Document cleanup completed")

    except ValueError as e:
        error_message = str(e)
        traceback_str = traceback.format_exc()

        log_error(f"Error Message: {error_message}")
        log_error(f"Traceback:\n{traceback_str}")

        log_info(f"\nError: {error_message}")
        sys.exit(1)
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        traceback_str = traceback.format_exc()

        log_error(f"Error Type: {error_type}")
        log_error(f"Error Message: {error_message}")
        log_error(f"Traceback:\n{traceback_str}")

        log_info(f"\nAn unexpected error occurred: {error_type}")
        log_info(f"Error details: {error_message}")
        log_info("Check the log file for the full traceback.")

        sys.exit(1)

if __name__ == "__main__":
    main()
