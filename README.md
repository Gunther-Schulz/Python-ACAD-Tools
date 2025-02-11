# Python CAD/GIS Tools

A Python-based CAD/GIS processing tool for automating DXF operations and handling various geospatial data formats.

## Requirements

- Python 3.8 or higher
- Git

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/Python-ACAD-Tools.git
cd Python-ACAD-Tools
```

2. Install in development mode:
```bash
pip install --use-pep517 -e .
```

Note: The `--use-pep517` flag ensures the installation uses modern Python packaging standards.

## Usage

You can run the tool in two ways:

1. Using the installed console script:
```bash
pycad project_name
```

2. Or directly using Python:
```bash
python -m src.main project_name
```

Options:
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO

Example:
```bash
pycad Torgelow2 --log-level DEBUG
```

## Project Configuration

Projects are configured using YAML files in the `projects/` directory. Each project should have its own directory containing the following configuration files:

- `project.yaml`: Main project settings
- `geom_layers.yaml`: Geometry layer configurations
- `legends.yaml`: Legend configurations
- `viewports.yaml`: Viewport configurations
- `block_inserts.yaml`: Block insertion configurations
- `text_inserts.yaml`: Text insertion configurations
- `path_arrays.yaml`: Path array configurations
- `wmts_wms_layers.yaml`: Web map service configurations

# Layer Processor Operations

This document outlines the various operation types available in the LayerProcessor class and their possible options.

## Operation Types

1. Copy
2. Buffer
3. Difference
4. Intersection
5. Filter
6. WMTS/WMS
7. Merge
8. Smooth
9. Contour

## Operation Details

### 1. Copy
Copies geometries from one or more source layers to the target layer.

Options:
- `layers`: List of source layers to copy from. If omitted, the operation will be performed on the current layer.

### 2. Buffer
Creates a buffer around the geometries of the source layers.

Options:
- `layers`: List of source layers. If omitted, the operation will be performed on the current layer.
- `distance`: Buffer distance (positive for outer buffer, negative for inner buffer)
- `joinStyle`: Style of buffer corners (default: 'round')
  - 'round'
  - 'mitre'
  - 'bevel'

### 3. Difference
Subtracts the geometries of overlay layers from the base layer.

Options:
- `layers`: List of overlay layers. If omitted, no difference operation will be performed.
- `reverseDifference`: Boolean flag to manually control the direction of the difference operation (optional)
  - If true, subtracts the base geometry from the overlay geometry
  - If false, performs the standard difference operation (base minus overlay)
  - If omitted, the direction is automatically determined based on the geometries

Notes:
- The `reverseDifference` flag provides a manual override to the automatic direction detection.
- When `reverseDifference` is not specified, the operation uses an algorithm to determine the most appropriate direction based on the geometries involved.
- Use this flag when you need to explicitly control the direction of the difference operation, overriding the automatic detection.

### 4. Intersection
Creates geometries that represent the intersection of the base layer with overlay layers.

Options:
- `layers`: List of overlay layers. If omitted, no intersection operation will be performed.

### 5. Filter
Filters geometries based on their intersection with filter layers.

Options:
- `layers`: List of filter layers. If omitted, no filtering will be performed.

### 6. WMTS/WMS
Downloads and processes Web Map Tile Service (WMTS) or Web Map Service (WMS) tiles.

Options:
- `layers`: List of boundary layers. If omitted, the current layer will be used as the boundary.
- `url`: Service URL
- `layer`: Service layer name
- `proj`: Projection
- `srs`: Spatial Reference System
- `format`: Image format (default: 'image/png')
- `zoom`: Zoom level
- `buffer`: Buffer distance around boundary (default: 100)
- `sleep`: Sleep time between requests (default: 0)
- `limit`: Limit on number of tiles to download (default: 0)
- `overwrite`: Whether to overwrite existing tiles (default: false)
- `stitchTiles`: Whether to stitch downloaded tiles (default: false)
- `postProcess`: Post-processing options
  - `removeText`: Whether to remove text from tiles (default: false)
  - `textRemovalMethod`: Method for text removal (default: 'tesseract')

### 7. Merge
Merges geometries from multiple source layers.

Options:
- `layers`: List of source layers to merge. If omitted, no merge operation will be performed.

### 8. Smooth
Smooths the geometries of source layers.

Options:
- `layers`: List of source layers. If omitted, the operation will be performed on the current layer.
- `strength`: Smoothing strength (default: 1.0)

### 9. Contour
Generates contour lines from elevation data.

Options:
- `layers`: List containing the boundary layer. If omitted, the current layer will be used as the boundary.
- `buffer`: Buffer distance around boundary
- Other options specific to contour generation (e.g., elevation data source, contour interval)

## General Notes

- Most operations support specifying multiple source or overlay layers.
- The `layers` option in operations can accept layer names as strings or as dictionaries with additional filtering options.
- If the `layers` option is omitted in applicable operations, the operation will be performed on the current layer.
- Some operations may have additional options not listed here. Refer to the specific method implementations for more details.
- For the buffer operation, use positive distance values for outer buffers and negative values for inner buffers.
- The difference operation now supports a `reverseDifference` flag to control the direction of the difference operation.
