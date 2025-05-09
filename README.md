# DXFPlanner: Geospatial to DXF Converter

DXFPlanner is a Python application designed to automate the generation of DXF (Drawing Exchange Format) files from various geospatial data sources. It aims to provide a flexible and configurable pipeline for transforming geographic features into DXF entities suitable for CAD applications.

This project is currently undergoing a significant refactoring to a new, modern architecture to enhance maintainability, scalability, and testability.

## Project Status

**Current Phase: Scaffolding Complete & Initial Implementation Ongoing**

*   The core architectural components (modules, services, interfaces, domain models, configuration schemas, DI container, entry points) have been scaffolded.
*   Placeholder implementations exist for most readers, writers, and services, which will raise `NotImplementedError` if run without further development.
*   The next steps involve implementing the core logic within these components and writing comprehensive tests.

## Architecture Overview

DXFPlanner is built with a modular and decoupled architecture, emphasizing:

*   **Domain-Driven Design (DDD) principles:** Clear separation of domain models, interfaces, and services.
*   **Dependency Injection (DI):** Using `python-dependency-injector` for managing component dependencies.
*   **Protocol-Based Interfaces:** Defining contracts between components using `typing.Protocol`.
*   **Centralized Configuration:** Pydantic models for typed configuration, loaded from YAML files.
*   **Structured Logging:** Using `loguru` for application-wide logging.
*   **Custom Exception Hierarchy:** For clear error reporting.

Key modules include:
*   `src/dxfplanner/core/`: Core framework (DI, exceptions, logging).
*   `src/dxfplanner/config/`: Configuration schemas and loaders.
*   `src/dxfplanner/domain/`: Domain models (geospatial, DXF) and interfaces.
*   `src/dxfplanner/services/`: Application and geoprocessing services (orchestration, validation, coordinate transformation, attribute mapping, geometry transformation).
*   `src/dxfplanner/io/`: Data readers (e.g., Shapefile) and writers (DXF).
*   `src/dxfplanner/geometry/`: (Planned) Geometry operations and transformations.
*   `src/dxfplanner/app.py`: Main application logic, initialization.
*   `src/dxfplanner/cli.py`: Command-line interface using Typer.

Refer to `PROJECT_ARCHITECTURE.md` and `PROJECT_STANDARDS.md` for detailed architectural guidelines.

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    # git clone <repository-url> # Replace with actual URL
    # cd DXFPlanner
    ```

2.  **Create and Activate a Virtual Environment:**
    It's highly recommended to use a virtual environment (e.g., `venv`, `conda`).
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    Install all required Python packages from `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: Some libraries like `fiona` (if chosen for Shapefile reading) may have non-Python system dependencies (e.g., GDAL). Ensure these are installed on your system if you encounter issues.*
    *`pyshp` is a pure Python alternative for Shapefiles included in requirements.*

4.  **Configuration (`config.yml`):
    The application uses a `config.yml` (or `config.yaml`) file for its settings.
    *   When you first run the application (e.g., via `app.py` or `cli.py`), if a `config.yml` is not found in standard locations (current directory, `./config/`), a minimal dummy `config.yml` will be created in the current working directory.
    *   It is recommended to review and customize this `config.yml` file with your desired settings. You can also place it in a `config/` subdirectory.
    *   The structure of the configuration is defined by Pydantic models in `src/dxfplanner/config/schemas.py`.

## Basic Usage (CLI)

Once set up, you can use the command-line interface to generate DXF files.

```bash
python -m dxfplanner.cli generate --source path/to/your/input.shp --output path/to/your/output.dxf
```

**Example:**

```bash
# Ensure test_data directories exist if running the example directly
# mkdir -p test_data/input test_data/output

# You'll need to provide an actual Shapefile (e.g., test_data/input/sample.shp)
# and its associated files (.dbf, .shx, etc.)

python -m dxfplanner.cli generate \
    --source test_data/input/sample.shp \
    --output test_data/output/generated_sample.dxf \
    --source-crs "EPSG:4326" \
    --target-crs "EPSG:25832"
```

**CLI Help:**

```bash
python -m dxfplanner.cli --help
python -m dxfplanner.cli generate --help
```

**Important Notes for Current Version:**
*   The core processing logic in services (readers, transformers, writers) are currently placeholders. Running the `generate` command will likely result in `NotImplementedError` until these are implemented.
*   You will need to install the necessary geospatial libraries (like `pyshp`, `fiona`, `pyproj`, `shapely`) and `ezdxf` by running `pip install -r requirements.txt`.

## Development

(Placeholder for information on running tests, linters, formatters, and contributing guidelines.)

## License

(Placeholder for license information - e.g., MIT, Apache 2.0.)
