import sys
from ezdxf.addons import odafc
import argparse

from src.project_loader import ProjectLoader
from src.layer_processor import LayerProcessor
from src.dxf_exporter import DXFExporter
from src.utils import setup_logging, setup_proj

class ProjectProcessor:
    def __init__(self, project_name: str, update_layers_list: list = None):
        self.project_loader = ProjectLoader(project_name)
        self.layer_processor = LayerProcessor(self.project_loader)
        self.dxf_exporter = DXFExporter(self.project_loader, self.layer_processor)
        self.update_layers_list = update_layers_list

    def run(self):
        self.layer_processor.process_layers(self.update_layers_list)
        self.dxf_exporter.export_to_dxf()

def main():
    setup_logging()
    setup_proj()

    parser = argparse.ArgumentParser(description="Process and export project data to DXF.")
    parser.add_argument("project_name", help="Name of the project to process")
    parser.add_argument("--update", nargs='+', help="List of layers to update", default=None)
    args = parser.parse_args()

    try:
        processor = ProjectProcessor(args.project_name, args.update)
        processor.run()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred:")
        print(traceback.format_exc())
        sys.exit(1)
        
if __name__ == "__main__":
    main()