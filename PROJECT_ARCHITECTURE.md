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
*   **Example (`src/dxfplanner/core/di.py`):
    ```python
    from dependency_injector import containers, providers
    from dxfplanner import config
    from dxfplanner.services import dxf_generation_svc, validation_svc
    from dxfplanner.services.geoprocessing import coordinate_svc, attribute_mapping_svc
    from dxfplanner.io.readers import shapefile_reader
    from dxfplanner.io.writers import dxf_writer
    from dxfplanner.core import logging_config, base_types
    from dxfplanner.geometry import transformations

    class Container(containers.DeclarativeContainer):
        config = providers.Configuration()
        logger = providers.Singleton(logging_config.get_logger, config=config.logging)

        # Geometry Operations
        geometry_transformer = providers.Factory(
            transformations.GeometryTransformer,
            logger=logger,
            # Potentially config for default CRS, etc.
        )

        # Readers
        shapefile_reader_service = providers.Factory(
            shapefile_reader.ShapefileReader,
            config=config.io.readers.shapefile, # Example refined config path
            logger=logger,
        )
        # ... other readers (GeoJSON, etc.)

        # Writers
        dxf_writer_service = providers.Factory(
            dxf_writer.DxfWriter,
            config=config.io.writers.dxf, # Example refined config path
            logger=logger,
        )

        # Geoprocessing Services
        coordinate_transform_service = providers.Factory(
            coordinate_svc.CoordinateTransformService,
            logger=logger,
            # config=config.services.coordinate, (if specific config needed)
        )
        attribute_mapping_service = providers.Factory(
            attribute_mapping_svc.AttributeMappingService,
            logger=logger,
            config=config.services.attribute_mapping,
        )
        # ... other geoprocessing services (simplification, etc.)

        validation_service = providers.Factory(
            validation_svc.ValidationService,
            logger=logger,
            # config=config.services.validation
        )

        # Main Orchestration Service
        dxf_generation_service = providers.Factory(
            dxf_generation_svc.DxfGenerationService,
            config=config.services.dxf_generation,
            logger=logger,
            geo_data_reader=shapefile_reader_service, # Example: inject a specific reader
            dxf_writer=dxf_writer_service,
            geometry_transformer=geometry_transformer,
            coordinate_svc=coordinate_transform_service,
            attribute_mapper=attribute_mapping_service,
            validator=validation_service,
        )
    ```

### 4.2. Configuration Management

*   **Location:** Schemas in `src/dxfplanner/config/schemas.py`, loading in `src/dxfplanner/config/loaders.py`.
*   **Structure:** `AppConfig` as the root, with nested Pydantic models for each module/area (e.g., `IOSettings`, `ServicesSettings`, `ReaderSettings`, `DxfWriterConfig`).
*   **Example (`src/dxfplanner/config/schemas.py`):
    ```python
    from pydantic import BaseModel, Field
    from typing import Optional, Dict

    class LoggingConfig(BaseModel):
        level: str = "INFO"
        format: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

    class ShapefileReaderConfig(BaseModel):
        default_encoding: str = "utf-8"
        # ... other shapefile specific settings

    class DxfWriterConfig(BaseModel):
        target_dxf_version: str = "AC1027" # AutoCAD 2013/2014/2015/2016/2017
        default_layer: str = "0"
        default_color: int = 256 # ByLayer
        layer_mapping: Dict[str, str] = Field(default_factory=dict) # e.g., {"source_layer_A": "target_dxf_layer_X"}
        # ... other DXF specific settings

    class ReaderConfigs(BaseModel):
        shapefile: ShapefileReaderConfig = Field(default_factory=ShapefileReaderConfig)
        # geojson: GeoJsonReaderConfig = Field(default_factory=GeoJsonReaderConfig)

    class WriterConfigs(BaseModel):
        dxf: DxfWriterConfig = Field(default_factory=DxfWriterConfig)

    class IOSettings(BaseModel):
        readers: ReaderConfigs = Field(default_factory=ReaderConfigs)
        writers: WriterConfigs = Field(default_factory=WriterConfigs)

    class AttributeMappingServiceConfig(BaseModel):
        attribute_to_layer_field: Optional[str] = None
        attribute_to_color_field: Optional[str] = None
        attribute_to_text_content_field: Optional[str] = None
        # ... other mapping rules

    class DxfGenerationServiceConfig(BaseModel):
        default_output_crs: Optional[str] = None # e.g., "EPSG:25832"
        # ... other generation specific settings

    class ServicesSettings(BaseModel):
        attribute_mapping: AttributeMappingServiceConfig = Field(default_factory=AttributeMappingServiceConfig)
        dxf_generation: DxfGenerationServiceConfig = Field(default_factory=DxfGenerationServiceConfig)
        # coordinate: CoordinateServiceConfig = Field(default_factory=CoordinateServiceConfig)
        # validation: ValidationServiceConfig = Field(default_factory=ValidationServiceConfig)

    class AppConfig(BaseModel):
        logging: LoggingConfig = Field(default_factory=LoggingConfig)
        io: IOSettings = Field(default_factory=IOSettings)
        services: ServicesSettings = Field(default_factory=ServicesSettings)
        # ... other global configurations
    ```

### 4.3. Error Handling

*   **Hierarchy:** `src/dxfplanner/core/exceptions.py`, base `DXFPlannerBaseError`.
    *   Specific errors: `ConfigurationError`, `ValidationError`, `GeoDataReadError`, `UnsupportedGeometryError`, `CoordinateTransformError`, `DxfWriteError`, `AttributeMappingError`.
*   **Logging:** Use the standard `logging` module (configured via `loguru` as suggested in `PROJECT_STANDARDS.md`). Log exceptions with stack traces using `logger.exception()` in `except` blocks. Expected errors (e.g., validation) at `INFO` or `WARNING`.
*   **Example (`src/dxfplanner/core/exceptions.py`):**
    ```python
    class DXFPlannerBaseError(Exception):
        """Base exception for the DXFPlanner application."""
        pass

    class ConfigurationError(DXFPlannerBaseError):
        """Error related to application configuration."""
        pass

    class GeoDataReadError(DXFPlannerBaseError):
        """Error reading or interpreting input geodata."""
        pass

    class DxfGenerationError(DXFPlannerBaseError):
        """Error specifically during DXF file generation."""
        pass # More specific sub-exceptions like DxfWriteError can be added

    class CoordinateTransformError(DXFPlannerBaseError):
        """Error during coordinate system transformation."""
        pass
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
