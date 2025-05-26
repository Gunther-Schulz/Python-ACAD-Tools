# Actionable Comments, TODOs, and Placeholders

**Document Purpose:** To track all `TODO` comments, placeholder implementations, and other actionable remarks identified during the codebase review. This serves as a checklist for future development, bug fixing, and feature completion.

**Review Date:** December 2024

---

## Findings

### 1. Domain Model Issues (`src/domain/geometry_models.py`)

*   **Issue:** `GeomLayerDefinition.validate_operations` method for parsing operation parameters is incomplete.
    *   **Details:** It lacks explicit `elif` branches for many operation types (e.g., `create_circles`, `connect_points`, `contour`, `wmts`, `wms`, `simplify`, `merge`, `clip`, `dissolve`, `rotate`, `scale`, `translate`, `offset_curve`). These currently fall back to being parsed as `AllOperationParams`, losing specific validation.
    *   **Action:** Add specific `elif` blocks for each missing operation type to ensure correct parsing into their respective `OpParams` models.
*   **Issue:** Incorrect `type` field in several `OpParams` models.
    *   **Details:** Models like `ContourOpParams`, `WmtsOpParams`, `WmsOpParams` (and potentially others) have `type: OperationType = OperationType.TRANSFORM` (or similar incorrect fixed type) instead of their actual specific operation type (e.g., `OperationType.CONTOUR`).
    *   **Action:** Correct the `type` field in all specific `OpParams` models to reflect their true `OperationType` enum value.

### 2. Operation Handler Enablement & Parameter TODOs

*   **Location:** `src/services/operations/operation_registry.py` (`_discover_handlers`) and `src/services/operations/__init__.py`.
*   **Issue:** `TODO` comments indicate that `data_processing_handlers.py`, `filtering_handlers.py`, and `advanced_handlers.py` are not fully enabled/integrated due to "missing operation parameters" or other issues.
    *   **Details:** While some `OpParams` for `data_processing_handlers` appear defined, the TODOs suggest a general need to verify and complete parameter definitions and handler registrations for all modules mentioned.
    *   **Action:** Systematically review each handler in these modules. Ensure their corresponding `OpParams` models in `src/domain/geometry_models.py` are fully defined and correctly referenced. Uncomment the handlers in `OperationRegistry` and `src/services/operations/__init__.py` once verified and tested.

### 3. Placeholder Handler Implementations

*   **`FilterByIntersectionHandler` (`src/services/operations/filtering_handlers.py`)**
    *   **Issue:** Currently a placeholder. Logs: "Filter by intersection operation not fully implemented yet."
    *   **Action:** Implement the handler logic. It should leverage the existing `GdfOperationService.filter_gdf_by_intersection()` method, using appropriate parameters from `FilterByIntersectionOpParams` (e.g., main layer, filter layer, predicate).

*   **`ContourHandler` (`src/services/operations/advanced_handlers.py`)**
    *   **Issue:** Placeholder. Logs: "Contour operation is not fully implemented yet - requires DEM processing capabilities".
    *   **Action:** Implement contour generation. This will likely involve integrating with libraries like `rasterio` and `GDAL`, fetching DEM data (e.g., from a URL specified in `ContourOpParams`), clipping to boundary layers, and generating contour lines. Ensure `ContourOpParams` is fully defined to support these needs.

*   **`WmtsHandler` & `WmsHandler` (`src/services/operations/advanced_handlers.py`)**
    *   **Issue:** Placeholders. Log: "{service_type} operation is not fully implemented yet - requires web service integration".
    *   **Action:** Implement WMTS/WMS client functionality. This includes parsing capabilities, calculating and downloading tiles/maps based on boundary and parameters, georeferencing, optional stitching, and saving results. Ensure `WmtsOpParams` and `WmsOpParams` are comprehensive.

### 4. Placeholder Data Source Logic

*   **Location:** `src/services/geometry_processor_service.py` (in `create_layer_from_definition` method).
*   **Issue:** Loading for DXF and SHP data sources are placeholders.
    *   **Comment:** `# TODO: Implement DXF/SHP loading logic using DataSourceService`
    *   **Action:** Implement the DXF and SHP loading branches by calling the appropriate methods on the injected `DataSourceService` (which, in turn, should use `IDXFAdapter` for DXF files).

### 5. Interface Definition Incompleteness

*   **Location:** `src/interfaces/config_validation_interface.py`
*   **Issue:** The `IConfigValidation` interface is missing the `validation_warnings` property.
    *   **Details:** The concrete implementation `ConfigValidationService` has this property, but it's not part of the interface contract.
    *   **Action:** Add `validation_warnings: List[str]` (or appropriate type) as a property to the `IConfigValidation` protocol.

### 6. Minor Refinements & TODOs from Code Review

*   **XDATA Handling (`src/adapters/dxf/entity_operations.py`)**
    *   **Issue:** Potential for suboptimal delegation in XDATA checking logic.
    *   **Action:** Review `has_xdata_value` and `is_created_by_script` to ensure optimal delegation and generality. Specifically, `is_created_by_script` could potentially use `has_xdata_value` more directly.

*   **Type Hint in `OperationRegistry` (`src/services/operations/operation_registry.py`)**
    *   **Issue:** The `params` argument in `execute_operation` is typed as `Any`.
    *   **Action:** Update the type hint for `params` to `AllOperationParams` (or a relevant Union of all `OpParams` models) for better type safety, aligning with `BaseOperationHandler.handle`.

*   **Transformation Origin Logic (`src/services/operations/transformation_handlers.py`)**
    *   **Issue:** `RotateHandler` and `ScaleHandler` use 'centroid' and 'center' origin types interchangeably to mean the center of the bounding box.
    *   **Action:** Clarify if 'centroid' should use the true geometric centroid. If so, implement it. If the current behavior (bounding box center for both) is intended, ensure documentation clearly states this and consider renaming the 'centroid' option to avoid user confusion (e.g., to 'bbox_center').

*   **`eval()` Security in `CalculateHandler` (`src/services/operations/filtering_handlers.py`)**
    *   **Issue:** Uses `eval()` for dynamic expression evaluation, which can be a security risk.
    *   **Action:** Evaluate the security implications. If expressions can come from untrusted sources, or for enhanced robustness, consider replacing `eval()` with a dedicated, safer expression parsing library (e.g., `asteval`, `numexpr`).

*   **MultiGeometry Support in `SnapToGridHandler` (`src/services/operations/data_processing_handlers.py`)**
    *   **Issue:** Currently logs a warning and does not snap MultiGeometries.
    *   **Action:** Consider implementing support for MultiGeometries, potentially by automatically exploding them before snapping or by iterating through `geom.geoms` within the `snap_geometry` helper.

*   **Performance of `DifferenceByPropertyHandler` (`src/services/operations/data_processing_handlers.py`)**
    *   **Issue:** The current implementation might have performance issues on large datasets due to nested iterations and repeated filtering/unioning.
    *   **Action:** Review the logic for performance bottlenecks. Consider optimizations such as pre-grouping or indexing the `difference_gdf` by `params.property_name` before the main loop.

*   **Logger Acquisition Consistency (`src/services/geometry/gdf_operations.py`)**
    *   **Issue:** Logger in `GdfOperationService.get_common_crs` is obtained via `logging.getLogger(__name__ + ".GdfOperationService")` instead of potentially using an injected `ILoggingService` instance.
    *   **Action:** Standardize logger acquisition. If `GdfOperationService` is meant to be injectable and receive `ILoggingService` (like other services/handlers), it should use `self._logger_service.get_logger(__name__)`. If it's a static/utility class not managed by DI, ensure the current pattern is intentional and provides desired logger hierarchy.

*   **Logger Name Consistency (`src/services/geometry/envelope_service.py`)**
    *   **Issue:** `EnvelopeService` uses `logger_service.get_logger("EnvelopeService")` with a hardcoded string.
    *   **Action:** Change to `logger_service.get_logger(__name__)` for consistency with the common pattern used elsewhere, which generally results in more hierarchical and traceable logger names.
