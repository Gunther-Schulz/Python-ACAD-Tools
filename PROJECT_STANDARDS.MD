# DXFPlanner - Project Coding Standards

**Version: 0.3** <!-- Updated version -->

**ATTENTION AI ASSISTANT: This document, along with `PROJECT_ARCHITECTURE.MD`, provides specific technical guidelines and patterns for the DXFPlanner project. You MUST adhere to these guidelines rigorously when implementing solutions.**

---

## 0. Foundational Principles

*   **Complete & Integrated Implementation:** Strive for fully functional, integrated solutions, not just isolated snippets. Solutions must be demonstrably integrated into the existing application structure.
*   **Work with Facts, Not Assumptions:** Base decisions on verified information from the codebase, requirements, or direct user input. If information is missing, actively seek it (e.g., read files, ask clarifying questions if blocked). Do not invent file paths, function names, or configurations.
*   **Critical Principle: Preserve Existing Functionality (Non-Regression):** When refactoring or adding features, ensure that existing, unrelated functionalities are not broken. The AI is responsible for considering and mitigating potential regressions.
*   **Consistency:** Adhere to established patterns, naming conventions, and architectural choices within the project. If a pattern is unclear, refer to existing code or `PROJECT_ARCHITECTURE.MD`.
*   **Verification:** Implementations must be verifiable. This includes:
    *   Ensuring code compiles/runs without syntax errors.
    *   Basic validation of outputs if applicable.
    *   Adherence to type hints.
    *   Consideration of how the code would be tested.
*   **Robust Solutions, Not Quick Fixes:** Aim for solutions that are maintainable, readable, and address the root cause of issues rather than applying superficial patches.
*   **Proactive Problem Solving:** If a user request implies a deeper issue or a necessary prerequisite task, identify and address it, or propose it to the user.

## 1. Code Formatting & Linting

*   **Formatter:** Black (default settings). `Ruff` should be configured to use Black as its underlying formatter.
*   **Linter:** Ruff (configure via `pyproject.toml` or `.ruff.toml`). Aim for a comprehensive ruleset.
*   **EditorConfig:** Use an `.editorconfig` file for basic editor settings (indentation, line endings).

## 2. Python Version

*   Target **Python 3.9** or higher to leverage modern features and type hinting capabilities. (Current codebase structure and dependencies like `asteval` are compatible).

## 3. Typing & Type Hinting

*   **Mandatory Type Hints:** All function and method signatures (arguments and return types) MUST include type hints.
*   **Variable Annotations:** Use type hints for complex variable types where it improves clarity.
*   **`typing.Protocol`:** Use `typing.Protocol` to define interfaces for services and components, promoting loose coupling and testability (as per `PROJECT_ARCHITECTURE.MD`).
*   **Pydantic:** Use Pydantic models for data validation, serialization, and configuration objects. Define clear schemas.

## 4. Naming Conventions (PEP 8 + Project Specifics)

*   **Modules:** `lower_case_with_underscores`.
*   **Packages:** `lower_case_with_underscores`.
*   **Classes:** `CapWords` (e.g., `DxfGenerationService`).
*   **Interfaces (Protocols):** `CapWords` prefixed with `I` (e.g., `IGeoDataReader`).
*   **Functions & Methods:** `lower_case_with_underscores` (e.g., `generate_dxf_file`).
*   **Variables:** `lower_case_with_underscores`.
*   **Constants:** `UPPER_CASE_WITH_UNDERSCORES` (e.g., `DEFAULT_ENCODING`).
*   **Private Members:** Prefix with a single underscore (e.g., `_internal_method`). Avoid `__double_underscore` (name mangling) unless strictly necessary for inheritance.

## 5. Error Handling & Custom Exceptions

*   **Custom Exception Hierarchy:** Define a clear hierarchy of custom exceptions inheriting from a base `DXFPlannerBaseError` in `src/dxfplanner/core/exceptions.py`. Examples: `ConfigurationError`, `GeoDataReadError`, `DxfWriteError`. (Consistent with `PROJECT_ARCHITECTURE.MD`).
*   **Raise Specific Exceptions:** Catch broad exceptions (e.g., `Exception`, `IOError`) only when necessary, and re-raise as more specific custom exceptions where appropriate.
*   **Logging:** Log exceptions with stack traces using `logger.exception()` within `except` blocks. For expected, non-critical errors (e.g., validation failures that are handled), log at `INFO` or `WARNING`.

## 6. Logging

*   **Framework:** Use the standard Python `logging` module. The current `src/dxfplanner/core/logging_config.py` initializes the standard logger. (`PROJECT_ARCHITECTURE.MD` mentions `loguru` which might be an aspirational future state or a misunderstanding; for now, standard `logging` is the active standard).
*   **Injection:** Logger instances should be injected into classes/services via Dependency Injection.
*   **Usage:** Use descriptive log messages at appropriate levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Use `logger.exception()` for unhandled exceptions to include stack traces.

## 7. Configuration Management

*   **Centralized Schemas:** Use Pydantic models in `src/dxfplanner/config/schemas.py` and related submodules (`operation_schemas.py`, `style_schemas.py`, etc.) to define the structure of all application configuration.
*   **Loading:** Configuration loading logic (e.g., from YAML files) should be in `src/dxfplanner/config/loaders.py`.
*   **Access:** Configuration objects (`ProjectConfig`, specific sub-configs) should be provided to components via Dependency Injection.

## 8. Dependency Injection (DI)

*   **Framework:** Use `python-dependency-injector`.
*   **Setup:** Container defined in `src/dxfplanner/core/di.py`.
*   **Pattern:** Prefer constructor injection for mandatory dependencies.
*   **Scope:** Inject dependencies into services, readers, writers, operations and other components as needed. Avoid global state.

## 9. Domain-Driven Design (DDD) Principles (Adapted)

*   **Domain Models:** Pydantic models in `src/dxfplanner/domain/models/` represent the core entities and value objects (e.g., `GeoFeature`, `DxfEntity`, `Coordinate`). These are the single source of truth for data structures.
*   **Services:** Application and domain services in `src/dxfplanner/services/` encapsulate business logic and orchestrate operations.
*   **Interfaces (Protocols):** Define clear contracts for services and components in `src/dxfplanner/domain/interfaces.py`.
*   **Separation of Concerns:** Maintain a clear distinction between modules as outlined in `PROJECT_ARCHITECTURE.MD` (`core`, `config`, `domain`, `services`, `io`, `geometry`).

## 10. Asynchronous Programming (`async/await`)

*   **Usage:** Employ `async/await` for I/O-bound operations (e.g., file reading/writing, potentially some geoprocessing operations that can release GIL) and for orchestrating multiple service calls.
*   **Libraries:** Utilize `asyncio` and compatible libraries. Note that core `ezdxf` operations for document manipulation are synchronous; async primarily benefits orchestration around `ezdxf`.

## 11. Testing

*   **Framework:** Pytest.
*   **Structure:** Tests in the `tests/` directory, mirroring the `src/dxfplanner` package structure (`tests/unit/`, `tests/integration/`).
*   **Unit Tests:** Focus on individual components (classes, functions) in isolation. Use mocking/stubbing for dependencies.
*   **Integration Tests:** Verify interactions between components (e.g., service calling a reader and then a writer).
*   **Coverage:** Aim for high test coverage. Consider using `pytest-cov`.

## 12. Documentation & Comments

*   **Docstrings:**
    *   **Modules:** Every module should have a docstring explaining its purpose.
    *   **Classes:** Every class should have a docstring describing its role and key functionalities. Include basic usage examples if complex.
    *   **Functions & Methods:** Every public function and method MUST have a docstring explaining its purpose, arguments (type and meaning), and return value (type and meaning). Use Google Python Style Docstrings.
*   **Inline Comments:** Use for complex or non-obvious logic. Avoid commenting on code that is self-explanatory.
*   **README.md:** Keep the main `README.md` updated with project overview, setup instructions, and basic usage.
*   **Architectural Documents:** Maintain `PROJECT_ARCHITECTURE.MD` and these `PROJECT_STANDARDS.MD`.

## 13. API Design (Internal Services)

*   Strive for clear, minimal, and consistent interfaces (Protocols).
*   Services should expose methods that represent clear use cases or operations.
*   Avoid overly complex or "god" objects.

## 14. Security Considerations

*   **Input Validation:** Validate all external inputs (e.g., configuration files, geodata). Pydantic helps with config validation. For geodata, check for consistency and expected values.
*   **Safe Expression Evaluation:** If using dynamic expression evaluation (e.g., for attribute mapping conditions or style conditions), use safe evaluators like `asteval` (as currently implemented) instead of `eval()`.
*   **File Handling:** Be cautious with file paths. Avoid constructing paths directly from user input without sanitization if applicable (though primarily internal config will drive paths).

## 15. Dependencies Management

*   **Primary:** The project contains both `environment.yaml` (for Conda) and `requirements.txt`. For development consistency, `environment.yaml` should be considered the primary source for defining the environment, especially if Conda-specific packages or channels are used. `requirements.txt` can be generated from the Conda environment for pip-only or alternative virtual environment setups.
*   **Minimize Dependencies:** Only add dependencies that are truly necessary.
*   **Regular Updates:** Periodically review and update dependencies to address security vulnerabilities and get bug fixes/new features.

## 16. AI Collaboration Guidelines

*   Refer to the comprehensive "AI Coding Guidelines (Comprehensive - Refactored)" document (currently **v0.6.2**) provided to the AI for detailed operational procedures, phase execution, reporting, and exception handling.
*   The AI MUST adhere to the principles and procedures outlined in that document, in addition to these project-specific standards.

## 17. DXF / `ezdxf` Specifics (Optional Addition)

*   **Core Concepts:** Developers working with DXF output should familiarize themselves with `ezdxf`'s core concepts: `Drawing` document, modelspace (`msp`), paperspace layouts, blocks, layers, and entity types.
*   **Units & Precision:** Be mindful of drawing units and precision requirements for DXF.
*   **`ezdxf` Documentation:** The official `ezdxf` documentation (available within the project at `ezdxf/docs/` or online) is the primary reference for `ezdxf` usage.
*   **Error Handling:** `ezdxf` operations can raise specific exceptions. Handle these appropriately.

---
