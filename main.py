import sys
from ezdxf.addons import odafc
import argparse
from fiona.errors import DriverIOError
import yaml
import os

from src.project_loader import ProjectLoader
from src.layer_processor import LayerProcessor
from src.dxf_exporter import DXFExporter
from src.utils import log_error, setup_logging, setup_proj

class ProjectProcessor:
    def __init__(self, project_name: str):
        self.project_loader = ProjectLoader(project_name)
        self.layer_processor = LayerProcessor(self.project_loader)
        self.dxf_exporter = DXFExporter(self.project_loader, self.layer_processor)

    def run(self):
        self.layer_processor.process_layers()
        self.dxf_exporter.export_to_dxf()

def main():
    setup_logging()
    setup_proj()

    parser = argparse.ArgumentParser(description="Process and export project data to DXF.")
    parser.add_argument("project_name", help="Name of the project to process")
    args = parser.parse_args()

    try:
        processor = ProjectProcessor(args.project_name)
        processor.run()
    except yaml.YAMLError as e:
        error_message = f"YAML parsing error in projects.yaml: {str(e)}"
        log_error(error_message)
        if hasattr(e, 'problem_mark'):
            mark = e.problem_mark
            print(f"Error position: line {mark.line + 1}, column {mark.column + 1}")
        sys.exit(1)
    except ValueError as e:
        log_error(str(e))
        print(f"Error: {e}")
        sys.exit(1)
    except DriverIOError as e:
        error_message = str(e)
        file_path = error_message.split("Failed to create file")[1].split(":")[0].strip()
        directory = os.path.dirname(file_path)
        error_message = f"Error: Unable to create file. The directory does not exist: {directory}\n"
        error_message += "Please ensure that the directory exists before running the program."
        log_error(error_message)
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred:")
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()