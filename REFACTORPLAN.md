## DXFPlanner - Refactoring Plan (from OLADPP)

**Objective:** Refactor the existing OLADPP/src codebase into the new `DXFPlanner` architecture as defined in `PROJECT_ARCHITECTURE.md` (v1.1). This plan outlines the phased approach to ensure a structured and manageable transition.

---

### Phase 1: Foundation & Core Setup (`src/dxfplanner/`)

1.  **Establish Project Structure:**
    *   Create the main `src/dxfplanner/` directory.
    *   Create all subdirectories as specified in `PROJECT_ARCHITECTURE.md` (v1.1), including `core`, `config`, `domain/models`, `domain/interfaces`, `geometry`, `services/geoprocessing`, `io/readers`, `io/writers`, and `tests` (with `unit` and `integration` subfolders).

2.  **Implement Core Framework (`src/dxfplanner/core/`):
    *   **Dependency Injection (`di.py`):** Set up the initial `python-dependency-injector` container structure.
    *   **Exceptions (`exceptions.py`):** Define the base `DXFPlannerBaseError` and common application-specific exceptions (e.g., `ConfigurationError`, `GeoDataReadError`).
    *   **Logging (`logging_config.py`):** Configure `loguru` for application-wide logging as per standards.
    *   **Base Types (`base_types.py`):** Define any core base classes or component interfaces (e.g., a `ConfigurableComponent` if desired).

3.  **Implement Configuration System (`src/dxfplanner/config/`):
    *   **Schemas (`schemas.py`):** Define Pydantic models for the application configuration (`AppConfig` and nested models for `IOSettings`, `ServicesSettings`, specific reader/writer/service configs) as detailed in `PROJECT_ARCHITECTURE.md`.
    *   **Loaders (`loaders.py`):** Implement logic to load configuration from YAML files or environment variables.
    *   Migrate relevant configuration structure and default values from `OLADPP/src/config/`.

### Phase 2: Domain Modeling (`src/dxfplanner/domain/`)

4.  **Define Domain Models (`src/dxfplanner/domain/models/`):
    *   **Common Models (`common.py`):** Implement `Coordinate`, `Color`, `BoundingBox`, etc.
    *   **Geodata Models (`geo_models.py`):** Implement `GeoFeature`, `Point`, `Polyline`, `Polygon`. These will be informed by `OLADPP/src/geometry/types/` and general geodata principles.
    *   **DXF Models (`dxf_models.py`):** Implement `DxfLayer`, `DxfEntity` (as a base), `DxfLine`, `DxfText`, `DxfBlockReference`, etc. These will be informed by `OLADPP/src/export/dxf/types/` (if it exists and is relevant) and `ezdxf` library capabilities.

5.  **Define Domain Interfaces (`src/dxfplanner/domain/interfaces.py`):
    *   Define `typing.Protocol` based interfaces for key components:
        *   `GeoDataReader` (e.g., `async def read_features(...) -> AsyncIterator[GeoFeature]: ...`)
        *   `DxfWriter` (e.g., `async def write_entities(...) -> None: ...`)
        *   `GeometryTransformer` (e.g., `async def transform_feature_to_dxf_entities(...) -> AsyncIterator[DxfEntity]: ...`)
        *   `CoordinateService` (e.g., `def reproject_coordinate(...) -> Coordinate: ...`)
        *   `AttributeMapper` (e.g., `def map_attributes_to_dxf_properties(...) -> Dict[str, Any]: ...`)
        *   Other service interfaces as needed (e.g., `ValidationServiceProtocol`).

### Phase 3: Component Implementation & Refactoring (from OLADPP/src)

6.  **Implement Geometry Modules (`src/dxfplanner/geometry/`):
    *   **Core Operations (`operations.py`):** Develop general geometric algorithms (simplification, validation). Refactor relevant logic from `OLADPP/src/geometry/operations/`.
    *   **DXF Transformations (`transformations.py`):** Implement the `GeometryTransformer` interface. This includes logic for converting `GeoFeature` objects to `DxfEntity` objects, handling coordinate system conversions (from geographic to DXF WCS), scaling, and feature decomposition.
    *   **Utilities (`utils.py`):** Create helper functions for common geometric calculations.

7.  **Implement I/O Adapters (`src/dxfplanner/io/`):
    *   **Readers (`io/readers/`):**
        *   Implement `ShapefileReader`, `GeoJsonReader`, `CsvWktReader`, etc., as concrete implementations of `GeoDataReader`.
        *   Adapt logic from `OLADPP/src/export/shapefile/` if it contains relevant geodata reading capabilities, otherwise create anew.
    *   **Writers (`io/writers/`):**
        *   Implement `DxfWriter` as a concrete implementation of the `DxfWriter` interface, using a library like `ezdxf`.
        *   Refactor DXF writing logic from `OLADPP/src/export/dxf/`.

8.  **Implement Services (`src/dxfplanner/services/`):
    *   **Geoprocessing Services (`services/geoprocessing/`):**
        *   `CoordinateTransformService` (`coordinate_svc.py`): Implement `CoordinateService` interface, likely using `pyproj`.
        *   `AttributeMappingService` (`attribute_mapping_svc.py`): Implement `AttributeMapper` interface.
        *   `SimplificationService` (`simplification_svc.py`): Implement if geometry simplification is a required feature.
        *   (Refactor and integrate logic from `OLADPP/src/operations/` and `OLADPP/src/preprocessors/` into these granular services).
    *   **Validation Service (`validation_svc.py`):** Implement data and configuration validation logic.
    *   **Main Orchestration Service (`dxf_generation_svc.py`):** Implement `DxfGenerationService`. This service will coordinate `GeoDataReader`s, geoprocessing services, `GeometryTransformer`, and `DxfWriter` to perform the end-to-end DXF generation.

9.  **Wire Components with Dependency Injection:**
    *   Incrementally update `src/dxfplanner/core/di.py` to register all implemented readers, writers, geometry components, and services.
    *   Ensure dependencies are correctly injected via constructors.

### Phase 4: Application Entry & Testing

10. **Create Application Entry Point (`src/dxfplanner/app.py` or `cli.py`):
    *   Develop the main application runner or command-line interface.
    *   This entry point will initialize the DI container, load configuration, and invoke the main `DxfGenerationService`.

11. **Develop Comprehensive Tests (`tests/`):
    *   **Unit Tests:** Write unit tests for all domain models, individual services, I/O components, and geometry transformation logic. Target specific functions and classes.
    *   **Integration Tests:** Write integration tests for key workflows, such as the complete geodata-to-DXF pipeline for sample input files. Test interactions between services.
    *   Ensure DI container wiring is implicitly tested through integration tests or with specific container tests.

### Phase 5: Cleanup & Finalization

12. **Review and Refine Codebase:**
    *   Perform a thorough review for adherence to `PROJECT_STANDARDS.md` and `PROJECT_ARCHITECTURE.md`.
    *   Ensure consistency in coding style, naming, and error handling.
    *   Remove any dead code or remnants from the old `OLADPP` structure.

13. **Update Project Documentation:**
    *   Update `README.md` with instructions for setting up, configuring, and running `DXFPlanner`.
    *   Ensure any other developer-facing documentation is current.

This phased plan provides a roadmap for systematically refactoring OLADPP into the robust and maintainable DXFPlanner application.
