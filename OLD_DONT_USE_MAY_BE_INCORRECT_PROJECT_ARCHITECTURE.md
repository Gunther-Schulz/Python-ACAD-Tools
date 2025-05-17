# DXFPlanner - Code Architecture Standards

**Version: 1.1** (Updated with deeper analysis of OLADPP structure)

**ATTENTION AI ASSISTANT: This document provides specific technical guidelines, patterns, and concrete examples for the DXFPlanner project. You MUST adhere to these guidelines when implementing solutions. This architecture is designed to align with `PROJECT_STANDARDS.md`.**

---

## 1. Overview

This document outlines the architecture for the DXFPlanner application, a platform for autogenerating DXF files through the processing of geodata. The goal is to create a robust, maintainable, and scalable codebase by adhering to modern software design principles and the guidelines set forth in `PROJECT_STANDARDS.md`. This version incorporates insights from a more detailed analysis of the previous `OLADPP` structure to ensure comprehensive coverage of functionalities in the new architecture.

The application will be structured within a new `src/` directory at the project root.

## 2. Guiding Principles (from `PROJECT_STANDARDS.md`)

The following core principles from `PROJECT_STANDARDS.md` are paramount:

*   **Complete & Integrated Implementation**
*   **Work with Facts**
*   **Critical Principle: Preserve Existing Functionality** (during refactoring)
*   **Consistency**
*   **Verification**
*   **Robust Solutions, Not Quick Fixes**
*   **Dependency Injection (DI)**
*   **Centralized Configuration**
*   **Custom Exception Hierarchy**
*   **Standard Logging**
*   **Domain Models as Single Source of Truth**
*   **Protocol-Based Interfaces (`typing.Protocol`)**

## 3. Proposed Directory Structure (under `src/`)

```
src/
├── dxfplanner/                  # Main application package for DXFPlanner
│   ├── __init__.py
│   ├── app.py                  # Main application orchestrator/entry point for CLI or services
│   │
│   ├── core/                   # Core framework components, base classes, utilities
│   │   ├── __init__.py
│   │   ├── di.py               # Dependency Injection container setup
│   │   ├── exceptions.py       # Custom exception hierarchy
│   │   ├── logging_config.py   # Logging setup and configuration
│   │   └── base_types.py       # Base Pydantic models, core component interfaces (e.g., ConfigurableComponent)
│   │
│   ├── config/                 # Configuration loading and type definitions
│   │   ├── __init__.py
│   │   ├── loaders.py          # Logic for loading configuration (e.g., from YAML, env vars)
│   │   └── schemas.py          # Pydantic models defining configuration structure (AppConfig, module configs)
│   │
│   ├── domain/                 # Core business logic, entities, value objects, and interfaces
│   │   ├── __init__.py
│   │   ├── models/             # Pydantic models for domain entities
│   │   │   ├── __init__.py
│   │   │   ├── common.py         # Common value objects (e.g., Coordinate, Color, Extents)
│   │   │   ├── geo_models.py     # Models for geodata (e.g., GeoFeature, Point, Polyline, Polygon with attributes)
│   │   │   └── dxf_models.py     # Models for DXF entities (e.g., DxfLayer, DxfLine, DxfText, DxfBlockReference)
│   │   └── interfaces.py       # Abstract interfaces (Protocols) for services, repositories, readers, writers
│   │
│   ├── geometry/               # Geometry processing, algorithms, and transformations
│   │   ├── __init__.py
│   │   ├── operations.py       # Geometric algorithms (e.g., buffer, intersect, simplify, reprojection)
│   │   ├── transformations.py  # Coordinate transformations, scaling, rotation specific to geodata-to-DXF
│   │   └── utils.py            # Geometric utility functions
│   │
│   ├── services/               # Application services, orchestrating domain logic
│   │   ├── __init__.py
│   │   ├── geoprocessing/      # Modules for specific geodata processing tasks
│   │   │   ├── __init__.py
│   │   │   ├── coordinate_svc.py # Service for coordinate reference system transformations
│   │   │   ├── simplification_svc.py # Service for geometry simplification
│   │   │   └── attribute_mapping_svc.py # Service for mapping geodata attributes to DXF properties
│   │   ├── dxf_generation_svc.py # Service orchestrating the overall DXF generation workflow
│   │   └── validation_svc.py   # Service for validating input geodata or intermediate results
│   │
│   ├── io/                     # Input/Output operations, data adapters
│   │   ├── __init__.py
│   │   ├── readers/            # Modules for reading geodata from various sources
│   │   │   ├── __init__.py
│   │   │   ├── shapefile_reader.py
│   │   │   ├── geojson_reader.py
│   │   │   └── csv_wkt_reader.py # Example for CSV with Well-Known Text geometries
│   │   └── writers/            # Modules for writing data to various formats, primarily DXF
│   │       ├── __init__.py
│   │       └── dxf_writer.py
│   │
│   └── cli.py                  # Command-line interface (if applicable)
│
└── scripts/                    # Utility scripts, one-off tasks (outside the main application package)

tests/                          # Pytest tests mirroring the src/dxfplanner structure
├── integration/
├── unit/
│   ├── domain/test_models.py
│   ├── services/test_dxf_generation_svc.py
│   └── ... (other unit test modules)
└── conftest.py
```

## 4. Key Architectural Components & Patterns

### 4.1. Dependency Injection (DI)

*   **Framework:** `python-dependency-injector` is recommended.
*   **Configuration:** `src/dxfplanner/core/di.py`.
*   **Injection Points:**
    *   Primarily use constructor injection for mandatory dependencies.
    *   Services, readers, writers, and geometry operations will receive their dependencies (like configuration objects, loggers, or other services) via DI.
*   **Example (`src/dxfplanner/core/di.py` - Conceptual):
    ```plaintext
    Define a DI container:
      - Provide configuration objects.
      - Provide a logger instance.
      - Define factory providers for geometry operations (e.g., GeometryTransformer)
        injecting logger and relevant config.
      - Define factory providers for various data readers (e.g., ShapefileReader)
        injecting config and logger.
      - Define factory providers for data writers (e.g., DxfWriter)
        injecting config and logger.
      - Define factory providers for geoprocessing services (e.g., CoordinateTransformService,
        AttributeMappingService) injecting logger and relevant config.
      - Define factory provider for validation service, injecting logger and config.
      - Define factory provider for the main DxfGenerationService, injecting its
        dependencies (config, logger, specific reader, writer, transformer,
        and other relevant services).
    ```

### 4.2. Configuration Management

*   **Location:** Schemas in `src/dxfplanner/config/schemas.py`, loading in `src/dxfplanner/config/loaders.py`.
*   **Structure:** `AppConfig` as the root, with nested Pydantic models for each module/area (e.g., `IOSettings`, `ServicesSettings`, `ReaderSettings`, `DxfWriterConfig`).
*   **Example (`src/dxfplanner/config/schemas.py` - Conceptual):
    ```plaintext
    Define Pydantic models for configuration:

    AppConfig:
      - logging: LoggingConfig (level, format)
      - io: IOSettings
        - readers: ReaderConfigs
          - shapefile: ShapefileReaderConfig (default_encoding, etc.)
          # - geojson: GeoJsonReaderConfig (...)
        - writers: WriterConfigs
          - dxf: DxfWriterConfig (target_dxf_version, default_layer, default_color, layer_mapping, etc.)
      - services: ServicesSettings
        - attribute_mapping: AttributeMappingServiceConfig (mapping fields like attribute_to_layer_field)
        - dxf_generation: DxfGenerationServiceConfig (default_output_crs, etc.)
        # - coordinate: CoordinateServiceConfig (...)
        # - validation: ValidationServiceConfig (...)
      # - other global configurations
    ```

### 4.3. Error Handling

*   **Hierarchy:** `src/dxfplanner/core/exceptions.py`, base `DXFPlannerBaseError`.
    *   Specific errors: `ConfigurationError`, `ValidationError`, `GeoDataReadError`, `UnsupportedGeometryError`, `CoordinateTransformError`, `DxfWriteError`, `AttributeMappingError`.
*   **Logging:** Use the standard `logging` module (configured via `loguru` as suggested in `PROJECT_STANDARDS.md`). Log exceptions with stack traces using `logger.exception()` in `except` blocks. Expected errors (e.g., validation) at `INFO` or `WARNING`.
*   **Example (`src/dxfplanner/core/exceptions.py` - Conceptual):**
    ```plaintext
    Define a base exception class:
      DXFPlannerBaseError (inherits from Exception)

    Define specific exception classes inheriting from DXFPlannerBaseError:
      - ConfigurationError
      - GeoDataReadError
      - DxfGenerationError
        # - DxfWriteError (optional sub-exception)
      - CoordinateTransformError
      - ValidationError
      - AttributeMappingError
      - UnsupportedGeometryError
    ```

### 4.4. Logging

*   **Setup:** `src/dxfplanner/core/logging_config.py` (using `loguru`).
*   **Access:** Logger instances (pre-configured) will be injected via DI into components that need logging.
*   **Usage:** Components use the injected logger (`self.logger.info(...)`, `self.logger.error(...)`, `self.logger.exception(...)`).

### 4.5. Domain Models and Interfaces

*   **Models (`src/dxfplanner/domain/models/`)**:
    *   Split into `common.py`, `geo_models.py`, and `dxf_models.py` for clarity.
    *   `common.py`: `Coordinate(x, y, z=None)`, `Color(r, g, b)`, `BoundingBox(min_x, min_y, max_x, max_y)`.
    *   `geo_models.py`: `GeoFeature(geometry: Union[Point, Polyline, Polygon], attributes: Dict[str, Any])`, `Point(coords: Coordinate)`, `Polyline(points: List[Coordinate])`, `Polygon(exterior: List[Coordinate], interiors: List[List[Coordinate]]=None)`.
    *   `dxf_models.py`: `DxfLayer(name: str, color: Optional[Color]=None, linetype: Optional[str]=None)`, `DxfEntity(layer: str, color: Optional[Color]=None, linetype: Optional[str]=None)`, `DxfLine(start: Coordinate, end: Coordinate, **kwargs)`, `DxfText(text: str, insertion_point: Coordinate, height: float, **kwargs)`, `DxfBlockReference(name: str, insertion_point: Coordinate, **kwargs)`.
        *   DXF entities should inherit from `DxfEntity`.
*   **Interfaces (`src/dxfplanner/domain/interfaces.py`):
    *   `GeoDataReader(Protocol)`: `async def read_features(self, source_path: AnyStr, source_crs: Optional[str] = None) -> AsyncIterator[GeoFeature]: ...`
    *   `DxfWriter(Protocol)`: `async def write_entities(self, file_path: AnyStr, entities: AsyncIterator[DxfEntity], layers: List[DxfLayer]=None, target_crs: Optional[str]=None) -> None: ...`
    *   `GeometryTransformer(Protocol)`: `async def transform_feature_to_dxf_entities(self, feature: GeoFeature, target_crs: Optional[str]) -> AsyncIterator[DxfEntity]: ...`
    *   `CoordinateService(Protocol)`: `def reproject_coordinate(self, coord: Coordinate, from_crs: str, to_crs: str) -> Coordinate: ...`
    *   `AttributeMapper(Protocol)`: `def map_attributes_to_dxf_properties(self, feature: GeoFeature) -> Dict[str, Any]: ...` (e.g., returns layer name, color, text content based on attributes and config).

### 4.6. Services (`src/dxfplanner/services/`)

*   **Geoprocessing Services (`src/dxfplanner/services/geoprocessing/`)**:
    *   `CoordinateTransformService`: Implements `CoordinateService`. Handles transformations between CRSs using libraries like `pyproj`.
    *   `AttributeMappingService`: Implements `AttributeMapper`. Uses configuration to map attributes from `GeoFeature` to visual properties for `DxfEntity` (layer, color, linetype, text content, block name, etc.).
    *   `SimplificationService`: (Optional) If complex geometries need simplification before DXF conversion.
*   **`DxfGenerationService`**:
    *   Orchestrates the end-to-end process: reads geodata using a `GeoDataReader`, applies transformations and attribute mappings (potentially via `GeometryTransformer` which itself uses coordinate and attribute services), and writes output using `DxfWriter`.
    *   Handles layer creation and management based on mapped attributes or configuration.
*   **`ValidationService`**:
    *   Performs pre-flight checks on input data (e.g., valid geometry, presence of required attributes) or configuration.

### 4.7. Input/Output (`src/dxfplanner/io/`)

*   **Readers (`src/dxfplanner/io/readers/`)**: Implementations for `GeoDataReader` (e.g., `ShapefileReader`, `GeoJsonReader`). They should handle reading geometries and their attributes into `GeoFeature` models.
*   **Writers (`src/dxfplanner/io/writers/`)**: Primarily `DxfWriter`. This service will take `DxfEntity` models and use a library like `ezdxf` to generate the DXF file. It should manage layers, linetypes, colors, and entity creation.

### 4.8. Geometry (`src/dxfplanner/geometry/`)

*   **`operations.py`**: Core geometric algorithms not specific to DXF conversion (e.g., simplification, validation, clipping if needed), likely using libraries like Shapely.
*   **`transformations.py`**: Implements `GeometryTransformer`. Contains logic to convert `GeoFeature` objects (Points, Polylines, Polygons, potentially with attributes) into one or more `DxfEntity` objects (LINE, LWPOLYLINE, TEXT, INSERT for blocks, etc.). This includes:
    *   Decomposition of complex geofeatures (e.g., multipolygons).
    *   Conversion of geographic coordinates to DXF's Cartesian coordinates (WCS/UCS handling if necessary).
    *   Application of scaling, rotation if defined in configuration.
*   **`utils.py`**: Helper functions for geometric calculations (e.g., distance, area, bounding box calculations).
