# Layer Processor Operations

This document outlines the various operation types available in the LayerProcessor class and their possible options.

## Code Quality and Development Setup

### Prerequisites
1. Python 3.12 or higher
2. Git
3. Conda (for environment management)
4. Cursor IDE (recommended)

### Setting Up Development Environment

1. Create and activate the Conda environment:
```bash
# Create environment from environment.yml
conda env create -f environment.yml

# Activate the environment
conda activate pycad
```

2. Verify the installation:
```bash
# Check Python version
python --version  # Should show Python 3.12.x

# Verify key packages
black --version
flake8 --version
mypy --version
```

3. Set up pre-commit hooks:
```bash
pre-commit install
```

### Code Quality Tools

The project uses several tools to maintain code quality, configured centrally in `pyproject.toml`:

1. **Linting and Style**
   - Flake8: Code style and quality checker
   - Pylint: Static code analysis
   - Black: Code formatter
   - isort: Import statement organizer

2. **Type Checking**
   - MyPy: Static type checker with strict settings

3. **Pre-commit Hooks**
   - Automatically check code before commits
   - Ensures consistent code style
   - Validates type hints
   - Organizes imports

### Code Style Guidelines

1. **Imports**
   - Group imports in this order:
     1. Standard library
     2. Third party
     3. First party (`src.*`)
     4. Local (same component)
   - Only import from component roots (e.g., `from src.config import X`)
   - No direct imports from component internals

2. **Component Boundaries**
   - Each component has a clear public API in `__init__.py`
   - External code only imports from component roots
   - Internal imports follow consistent patterns
   - Components are independently testable

3. **Documentation**
   - Google-style docstrings
   - Clear module-level documentation
   - Type hints for all functions
   - Comments for complex logic

### Running Code Quality Checks

1. **Cursor IDE Integration**
   - Real-time linting with flake8
   - Format on save with Black
   - Import organization with isort
   - Type checking with MyPy

2. **Manual Checks**
```bash
# Run all linters
flake8 src/
pylint src/
mypy src/

# Format code
black src/
isort src/
```

3. **Pre-commit Hooks**
```bash
# Run all pre-commit hooks
pre-commit run --all-files
```

### Development Environment
The project uses Conda for environment management. Key files:
- `environment.yml`: Defines all project dependencies
- `pyproject.toml`: Centralizes tool configurations (Black, MyPy, Pylint, etc.)
- `.flake8`: Flake8-specific configuration

## Diagrams

The project includes PlantUML diagrams that visualize the code architecture and flows. These diagrams are located in the `diagrams/` directory.

### Updating Diagrams

To update or generate the diagrams, you need:
1. PlantUML (`sudo pacman -S plantuml graphviz` on CachyOS/Arch-based systems)
2. Graphviz (installed as a dependency of PlantUML)

To generate/update a diagram:
```bash
plantuml diagrams/<diagram_name>.puml
```

Available diagrams:
- `code_flow.puml`: Overall code architecture and component relationships
- `style_flow.puml`: Style settings and application flow

The generated PNG files will be placed in the same directory as the source `.puml` files.

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
