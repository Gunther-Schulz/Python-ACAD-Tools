"""
Command-line interface for PyCAD.
"""
import os
import typer
from rich.console import Console
from rich.table import Table
from src.core.project import Project
from src.core.exceptions import ProjectError, ProcessingError
from src.core.processor import Processor

# Initialize Typer app
app = typer.Typer(
    name="pycad",
    help="Python CAD Data Processing Pipeline",
    add_completion=False
)

# Initialize Rich console
console = Console()


def list_available_projects() -> list:
    """List all available projects in the projects directory."""
    projects_dir = 'projects'
    if not os.path.exists(projects_dir):
        return []

    projects = []
    for item in os.listdir(projects_dir):
        if os.path.isdir(os.path.join(projects_dir, item)):
            projects.append(item)
    return sorted(projects)


@app.command()
def list_projects():
    """List all available projects."""
    projects = list_available_projects()

    if not projects:
        console.print("[yellow]No projects found in the projects directory.[/yellow]")
        return

    table = Table(title="Available Projects")
    table.add_column("Project Name", style="cyan")
    table.add_column("Status", style="green")

    for project in projects:
        # Check if project has required configuration files
        project_dir = os.path.join('projects', project)
        has_config = os.path.exists(os.path.join(project_dir, 'project.yaml'))
        status = "✓ Ready" if has_config else "⚠ Missing config"
        table.add_row(project, status)

    console.print(table)


@app.command()
def process(
    project_name: str = typer.Argument(..., help="Name of the project to process")
):
    """
    Process a project using its configuration files.

    The project configuration should be defined in:
    projects/{project_name}/
    """
    try:
        # Load project
        project = Project(project_name)

        # Initialize processor
        processor = Processor(project)

        # Process project
        processor.process()

        console.print(f"[green]Project '{project_name}' processed successfully![/green]")
    except ProjectError as e:
        console.print(f"[red]Project error: {str(e)}[/red]")
        raise typer.Exit(1)
    except ProcessingError as e:
        console.print(f"[red]Processing error: {str(e)}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command()
def show_operations():
    """Show available layer operations."""
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

    table = Table(title="Available Layer Operations")
    table.add_column("Operation", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("Options", style="yellow")

    for op, details in operations.items():
        options_str = "\n".join(
            f"{k}: {v}" if not isinstance(v, dict)
            else f"{k}:\n" + "\n".join(f"  {sk}: {sv}" for sk, sv in v.items())
            for k, v in details['options'].items()
        )
        table.add_row(
            op.upper(),
            details['description'],
            options_str
        )

    console.print(table)


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
