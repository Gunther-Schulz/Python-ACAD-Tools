# Python ACAD Tools

A Python package for processing and exporting GIS data to AutoCAD DXF format, with support for various GIS operations and styling.

## Features

- Import and process shapefiles
- Export to DXF format with styling
- Support for various geometry operations (buffer, intersection, difference, etc.)
- Layer management and styling
- Text and label processing
- Hatch pattern support
- WMS/WMTS service integration

## Installation

For regular installation:
```bash
pip install .
```

For development installation (editable mode):
```bash
pip install -e .
```
This allows you to modify the code and have changes take effect immediately without reinstalling.

## Usage

Basic usage:

```bash
acad-tools project_name
```

Options:
- `--plot-ops`: Plot the result of each operation
- `--cleanup`: Perform thorough document cleanup after processing
- `--list-operations`: List all possible layer operations and their options
- `--list-settings`: List all possible layer settings and their options
- `--list-projects`: List all available projects
- `--create-project`: Create a new project with basic settings
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR)

## Project Structure

A project consists of several YAML configuration files:

- `project.yaml`: Core project settings
- `geom_layers.yaml`: Geometry layer definitions
- `legends.yaml`: Legend configurations
- `viewports.yaml`: Viewport settings
- `block_inserts.yaml`: Block insertion definitions
- `text_inserts.yaml`: Text insertion definitions
- `path_arrays.yaml`: Path array definitions
- `web_services.yaml`: WMS/WMTS service configurations

## Development

After installing in development mode with `pip install -e .`, any changes you make to the source code will be immediately reflected when running the package. This is ideal for development and testing.

## License

MIT License
