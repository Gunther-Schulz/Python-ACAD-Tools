# Project Architecture: Python-ACAD-Tools (Refactored)

**Version:** 1.0
**Date:** (Current Date)
**Status:** Initial Draft

## 1. Introduction

This document outlines the architectural design for the refactored `src/` directory of the Python-ACAD-Tools project. It aims to establish clear module boundaries, promote maintainability, ensure scalability, and enforce consistency by adhering to `PROJECT_STANDARDS.MD`.

The primary goal of this refactoring effort is to modernize the codebase, eliminate technical debt, and create a robust foundation for future development.

## 2. Guiding Principles & Standards Compliance

This architecture adheres to the principles outlined in `PROJECT_STANDARDS.MD`. Key principles include:

*   **Clear Boundaries & Separation of Concerns:** Modules will have well-defined responsibilities.
*   **Domain Models as Single Source of Truth:** All data structures, enums, and constants will be defined as Pydantic V2 models within a central `src.domain` module.
*   **Pydantic V2 Mandate:** All data validation, serialization, and data representation will use Pydantic V2 models. This ensures type safety and data integrity.
*   **Protocol-Based Interfaces:** Interactions between major components will be defined by `typing.Protocol` where appropriate, promoting loose coupling.
*   **Dependency Injection (DI):** DI will be the primary mechanism for object creation and wiring, managed by a central DI container.
*   **Upfront Configuration:** Application configuration will be loaded into a Pydantic V2-based `AppConfig` model at startup and accessed via DI.
*   **Stateless Utilities:** Common, pure functions will reside in dedicated utility modules.

## 3. High-Level Module Structure (src/)

The new `src/` directory will be organized into the following top-level Python packages:

*   `src.domain`:
    *   **Responsibility:** Contains all Pydantic V2 models representing the core data structures, enums, and constants for the application domain (e.g., CAD entities, project configurations, geometric types). This is the single source of truth for data shapes.
    *   **Interactions:** Imported by virtually all other modules. Does not depend on other application modules.
*   `src.interfaces`:
    *   **Responsibility:** Defines `typing.Protocol` (or abstract base classes if more suitable) for key services and components. These interfaces dictate the contracts between different parts of the application.
    *   **Interactions:** Implemented by service and core logic modules. Used by components that require these services.
*   `src.services`:
    *   **Responsibility:** Contains implementations of the interfaces defined in `src.interfaces`. Houses business logic related to specific tasks (e.g., DXF processing, style management, data conversion). Services should be stateless or manage state explicitly.
    *   **Sub-packages (examples, to be refined based on `OLDAPP` analysis):**
        *   `src.services.dxf_handling`: Logic for reading, processing, and writing DXF files.
        *   `src.services.style_management`: Logic for managing CAD styles.
        *   `src.services.geometry_ops`: Geometric calculations and transformations.
        *   `src.services.project_ops`: Operations related to project loading and management.
    *   **Interactions:** Implements `src.interfaces`. Uses `src.domain` models. May use `src.utils`.
*   `src.core`:
    *   **Responsibility:** Houses the core application orchestration, DI container setup, and entry points (e.g., CLI command handlers, main application runner). It wires together different services and components.
    *   **Interactions:** Uses `src.interfaces`, `src.services`, `src.config`. Initializes the DI container.
*   `src.config`:
    *   **Responsibility:** Manages application configuration. Defines `AppConfig` (a Pydantic V2 model, potentially using `pydantic-settings` for environment variable loading) and provides access to configuration values via DI.
    *   **Interactions:** Used by `src.core` for initialization and by any service/component needing configuration.
*   `src.utils`:
    *   **Responsibility:** Contains common, stateless utility functions and helper classes that are not specific to any single domain or service (e.g., file I/O helpers, string manipulation, generic data transformations).
    *   **Interactions:** Can be used by any other module. Should not have dependencies on other application modules except potentially `src.domain` for simple types if absolutely necessary (prefer passing primitive types).
*   `src.adapters`:
    *   **Responsibility:** (Optional, consider if needed based on `OLDAPP` complexity) Handles interactions with external systems or libraries, adapting their interfaces to those used within the application (defined in `src.interfaces`). This could include wrappers for database connectors, external APIs, or specific file format libraries if their direct usage in services is too coupled.
    *   **Interactions:** Implements interfaces from `src.interfaces`. Consumed by services.
*   `src.cli`:
    *   **Responsibility:** If the application has a Command Line Interface, this module will contain the CLI command definitions and handlers, likely using a library like Typer or Click. Commands will typically orchestrate actions by calling services via interfaces.
    *   **Interactions:** Uses `src.core` (for DI access to services) and `src.interfaces`.

## 4. Data Modeling with Pydantic V2

*   All domain entities, data transfer objects (DTOs), and configuration objects **MUST** be defined as Pydantic V2 `BaseModel` subclasses.
*   Models should be placed in the `src.domain` package, organized into sub-modules by concern (e.g., `src.domain.common`, `src.domain.dxf_entities`, `src.domain.project_settings`).
*   **Best Practices for Pydantic V2 (to be expanded with project specifics):**
    *   Use specific types (e.g., `int`, `str`, `float`, `bool`, `datetime`).
    *   Use `Optional[X] = None` for optional fields with no default other than `None`.
    *   Use `Field(default_factory=list)` for mutable default values like lists or dicts.
    *   Utilize nested models for complex data structures.
    *   Employ `@field_validator` for custom validation logic beyond type checking.
    *   Use `model_config = ConfigDict(...)` for model-specific configurations (e.g., `frozen=True`, `extra='ignore'`).
    *   Leverage `AliasGenerator` with `AliasChoices` or `AliasPath` if input data field names vary or are nested.
    *   Strict mode (`strict=True` in `ConfigDict` or per-field) should be considered for areas requiring exact type matches without coercion, where appropriate.
    *   For settings management, `pydantic-settings` `BaseSettings` should be used within `src.config`.

## 5. Dependency Management and DI

*   The project will use a Dependency Injection (DI) container (e.g., `dependency-injector`).
*   The DI container will be configured in `src.core`.
*   Components (services, adapters) should declare their dependencies via constructor arguments, typed using interfaces from `src.interfaces`.
*   The DI container will be responsible for instantiating and wiring these components.

## 6. Error Handling

*   A consistent error handling strategy will be adopted.
*   Custom exceptions should inherit from a base application exception class.
*   Services should raise specific exceptions defined in `src.domain.exceptions` or `src.interfaces.exceptions` to indicate failures.
*   Pydantic's `ValidationError` will be the standard for data validation issues.

## 7. Future Considerations / To Be Detailed Further

*   Logging strategy (refer to `PROJECT_STANDARDS.MD`).
*   Testing strategy (unit, integration, contract tests for interfaces).
*   Detailed breakdown of sub-modules within `src.services` based on analysis of `OLDAPP/`.

## 8. Document Evolution

This document is a living document and will be updated as the refactoring progresses and new architectural decisions are made.
