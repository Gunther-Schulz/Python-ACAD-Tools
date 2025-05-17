# DxfPlanner Project Architecture

This document outlines the high-level architecture of the `dxfplanner` application, primarily located within the `src/dxfplanner` directory.

The `dxfplanner` project is a Python application designed to process geospatial data from various sources and generate DXF (Drawing Exchange Format) files. It appears to follow a layered architecture, potentially influenced by Domain-Driven Design (DDD) principles, to manage complexity and promote modularity.


## Key Dependency: `ezdxf` Usage

### `ezdxf` Library

- **Core Functionality:** The `ezdxf` library is a critical dependency for `dxfplanner`, providing the primary means for creating, reading, and writing DXF files.
- **Local Resources:** The full source code for `ezdxf` is available locally in the `ezdxf/src/` directory within the broader project workspace. Comprehensive documentation for `ezdxf` can also be found locally in `ezdxf/docs/source/`.
- **Importance of Correct Usage:** Due to the complexity of the DXF format, correct usage of `ezdxf` is essential to prevent DXF file corruption or unexpected behavior. The local `ezdxf` documentation and source code are invaluable resources and should be consulted frequently when working with or extending `ezdxf`-related functionalities in `dxfplanner`. Prioritizing these local resources over general web searches is recommended for `ezdxf`-specific questions.


## Core Components and Layers:

The application is broadly structured into the following key directories/layers within `src/dxfplanner/`:

1.  **Entry Points (`app.py`, `cli.py`)**
    *   `app.py`: Potentially the main application runner or an entry point for a future GUI or web API.
    *   `cli.py`: Provides a command-line interface for users to interact with the application's functionalities.

2.  **Core (`core/`)**
    *   This layer contains fundamental building blocks and cross-cutting concerns essential for the application's operation.
    *   Key components include:
        *   `di.py`: Suggests the use of Dependency Injection for managing dependencies and promoting loose coupling.
        *   `logging_config.py`: Handles the setup and configuration of logging throughout the application.
        *   `exceptions.py`: Defines custom exception types for error handling specific to the application.
        *   `base_types.py`: Likely contains custom base data types or Pydantic models used across different modules.

3.  **Configuration (`config/`)**
    *   Responsible for managing all application configurations.
    *   It includes:
        *   `loaders.py`: Handles the loading of configuration data from files or other sources.
        *   A collection of `schemas.py` files (e.g., `common_schemas.py`, `dxf_writer_schemas.py`, `operation_schemas.py`, `style_schemas.py`): These define the structure and validation rules for configuration data, likely using a library like Pydantic. This indicates that aspects like DXF output parameters, operational behaviors, and styling are highly configurable.

4.  **Domain (`domain/`)**
    *   This layer encapsulates the core business logic, entities, and rules of the `dxfplanner` application, aligning with DDD principles.
    *   It comprises:
        *   `models/`: Contains the primary data structures (domain models) representing the application's concepts. This includes `dxf_models.py` for DXF-specific entities and `geo_models.py` for general geospatial data structures.
        *   `interfaces.py`: Defines abstract contracts (interfaces) for services, repositories, or other components, promoting an abstraction layer between the domain and its implementations.

5.  **Geometry (`geometry/`)**
    *   A dedicated module for all geospatial computations, geometric operations, and transformations.
    *   Key functionalities include:
        *   `operations.py`: Contains core geometric algorithms (e.g., buffering, intersections, unions).
        *   `transformations.py`: Manages coordinate system transformations.
        *   `projection.py`: Handles map projection conversions.
        *   `shapely_utils.py`: Provides utility functions for working with the Shapely library, a popular Python package for geometric analysis.
        *   Conversion utilities (`feature_converter.py`, `model_conversion.py`) for translating between different geometric representations or data models.
        *   Utilities for DXF-specific geometric aspects like layers (`layer_utils.py`) and colors (`color_utils.py`).

6.  **Input/Output (`io/`)**
    *   Manages all data input and output operations for the application.
    *   It is divided into:
        *   `readers/`: Contains modules responsible for reading data from various external formats. Supported formats likely include GeoJSON (`geojson_reader.py`), Shapefile (`shapefile_reader.py`), and CSV with Well-Known Text (WKT) geometry (`csv_wkt_reader.py`).
        *   `writers/`: Focuses on generating output files, with a primary emphasis on DXF.
            *   `dxf_writer.py`: The main component for constructing and writing DXF files.
            *   `components/`: A subdirectory containing helper services for the DXF writing process, such as `dxf_entity_converter_service.py` (for converting internal geometry to DXF entities), `dxf_viewport_setup_service.py` (for configuring viewports), and `dxf_resource_setup_service.py` (for managing DXF resources like layers and text styles).

7.  **Services (`services/`)**
    *   This layer contains application services that orchestrate workflows and implement specific use cases by coordinating interactions between different components (e.g., domain objects, I/O modules, geometry tools).
    *   Key services include:
        *   `legend_generation_service.py`: For creating and adding legends to the DXF output.
        *   `validation_service.py`: Performs data validation tasks.
        *   `style_service.py`: Manages styling information for DXF entities.
        *   `layer_processor_service.py`: Handles the processing of data layers.
        *   `pipeline_service.py` and `orchestration_service.py`: Suggest mechanisms for defining and executing sequences of operations or complex data processing pipelines.
        *   `operation_service.py`: Likely provides a higher-level interface to the geometric operations defined in the `geometry/` layer.
    *   It also contains a `geoprocessing/` sub-module with more specialized geospatial services:
        *   `label_placement_service.py`: For automatically placing text labels on the map.
        *   `attribute_mapping_service.py`: For mapping attributes between different data sources or models.
        *   `coordinate_service.py`: Provides services related to coordinate system management and conversions.

## Design Principles and Observations:

*   **Layered Architecture:** The distinct separation of concerns into layers (core, config, domain, geometry, I/O, services) is a prominent feature, aiming for better maintainability, testability, and scalability.
*   **Modularity:** The codebase is organized into well-defined modules with specific responsibilities.
*   **Configuration-Driven:** The extensive use of configuration schemas implies that the application's behavior can be significantly customized through external configuration files.
*   **Geospatial Focus:** The application is clearly tailored for geospatial data processing, with dedicated modules for geometry, various geospatial file readers, and specialized geoprocessing services.
*   **Potential for DDD:** The structure, especially the `domain/` layer with its models and interfaces, suggests an adherence to or influence from Domain-Driven Design principles.

## Note on Project Structure:

There is a nested `src/src/dxfplanner` directory structure that appears to be a duplicate or an outdated part of the `src/dxfplanner/io/writers/components/` path. This analysis focuses on the primary `src/dxfplanner` as the active codebase. The nested `src/src/` should be reviewed for cleanup.
