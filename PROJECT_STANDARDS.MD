# Beat the Books - Development Standards and Requirements

**ATTENTION AI ASSISTANT: This document outlines development standards and requirements. The Core Principles are paramount and MUST be adhered to strictly. This document may reference common patterns and tools (potentially using Python examples), but project-specific implementation details (like specific file names or chosen library configurations) are defined in `PROJECT_ARCHITECTURE.md`. Violations, especially of the 'Work with Facts' principle, are critical failures. The AI Assistant's operational process for adhering to these standards and its detailed verification procedures are outlined in `CLIPPY.md`.**

## Quick Reference Guide

| Context / Task                      | Key Standard / Tool Recommendation (Examples may be Python-specific) | Section Reference                |
| :---------------------------------- | :------------------------------------------------------------------ | :------------------------------- |
| Debugging Errors                    | Capture full traceback with standard logging (`logger.exception()` or `exc_info=True`) | Debugging & Analysis             |
| Inspecting Large Files (esp. JSON)  | Use command-line tools (`jq`, `grep`, `cat`, etc.)                  | Debugging & Analysis             |
| Defining Types (Enums, Models)      | Use central Domain Models                                           | Code Quality - Domain Models     |
| Creating/Wiring Components          | Use Dependency Injection (DI) container (configured in central DI module) | Patterns & Practices - DI        |
| Handling Configuration              | Load central config object (e.g., `AppConfig`) via DI at startup    | Architecture - Configuration     |
| Interface Definitions               | Use language's interface/protocol features (e.g., `typing.Protocol`) | Code Quality - Typing            |
| Implementing Cross-Cutting Logic    | Consider Decorator Pattern                                          | Patterns & Practices - Decorator |
| CLI Command Implementation          | Use Command Pattern via DI                                          | Patterns & Practices - Command   |
| Adding Common Pure Functions        | Place in dedicated utility modules                                  | Code Quality - Stateless Utils   |

## Core Principles

- **Complete & Integrated Implementation:**
    - Aim for complete and robust solutions that address all directly related aspects of a requested change, ensuring proper integration and adherence to architectural principles, not just the minimal fix.
- **Work with Facts:**
    - All implementations must be based *only* on specified requirements or verified information. Avoid guesswork, assumptions, and unrequested default values or fallback behaviors. The AI Assistant follows detailed procedures in `CLIPPY.md` (e.g., Step 3.3, `Procedure: Verify Hypothesis`) to ensure factual grounding and seek clarification when needed.
- **Critical Principle: Preserve Existing Functionality:** Modifications **MUST NOT** break or degrade existing core functionality. Proposed changes must be explicitly assessed for their impact on related components and data flows. Preventing regressions is paramount and takes precedence over expediency. Any change introducing a regression requires immediate remediation.
- **Consistency:**
    - Strongly prefer using patterns and libraries already present in the codebase to maintain consistency.
    - If a clearly superior alternative (new pattern, external library) exists, **propose its adoption with justification** rather than implementing it directly without approval.
- **Verification:**
    - Interface contracts must be verified before implementation, and files read before editing. The AI Assistant employs comprehensive verification steps (detailed in `CLIPPY.md`, e.g., `Procedure: Ensure Sufficient File Context`, `Procedure: Verify Diff`) throughout its process.
- **Robust Solutions, Not Quick Fixes:**
    - Prioritize well-designed, maintainable, and correct code adhering to established best practices and architectural standards over temporary hacks, workarounds, or shortcuts that compromise quality or introduce technical debt.
- **Review Focus:**
    - When reviewing code: Focus on problematic issues rather than listing what's correct.

## Key Dependency: `ezdxf` Usage

- **Local Resources:** The full source code for `ezdxf` is available locally in the `ezdxf/src/` directory, and comprehensive documentation can be found in `ezdxf/docs/source/`.
- **Importance of Correct Usage:** These local resources are invaluable and **SHOULD BE CONSULTED** frequently when working with `ezdxf` functionalities. Correct usage is critical to prevent DXF file corruption or unexpected behavior. Prioritize searching these local resources over general web searches for `ezdxf`-related questions.

# NOTE: This document provides principles and a checklist, potentially with language-relevant examples (e.g., Python). Refer to the project-specific `PROJECT_ARCHITECTURE.md` for detailed implementation choices, configurations, and concrete examples for this project.

## Debugging & Analysis
- **Traceback Analysis:** Prioritize obtaining and analyzing the full traceback when diagnosing errors. Leverage the existing logging setup, specifically using standard methods like `logger.error(message, exc_info=True)` or its shorthand `logger.exception(message)`, to capture tracebacks effectively within `except` blocks and minimize guesswork.
- **Large File Handling:** When analyzing large files (especially structured text like JSON), prefer using command-line tools (e.g., `jq`, `cat`, `grep`, `less`) for inspection and querying rather than attempting to load the entire file into memory or an editor.

## Architecture & Design

- **Clear Boundaries:** Ensure sensible architecture design with clear boundaries (See `PROJECT_ARCHITECTURE.MD`).
- **Separation of Concerns:** Ensure clean separation between domain models, interfaces, and implementations.
- **Adherence to Defined Modularity:** Strictly follow the component and module boundaries, including the specified use of sub-packages for services (e.g., `services/styling/` for style-related components), as detailed in `PROJECT_ARCHITECTURE.MD`. Prioritize grouping related functionalities into these defined architectural units.


## Code Quality & Correctness

- **Strict Implementation:** 100% adherence to specifications and interfaces.
- **Future Focus:** No backwards compatibility, no deprecation handling required.
- **DRY Principle:** Avoid code duplication. Actively seek to reuse existing logic. The AI Assistant includes steps to search for existing implementations (see `CLIPPY.md`, Step 3.1).
- **Cleanliness:** Clean up old/deprecated code during refactoring.
- **Integration:** Ensure refactors are well integrated and don't leave remnants.
- **Interface Matching:** Match async/sync method calls to interface definitions precisely. Validate parameter/return types against interfaces.
- **Function/Method Conciseness:** Functions and methods should be kept concise, focused on a single responsibility, and avoid excessive nesting (e.g., deep if/else chains or loops). Aim for shorter, understandable units; consider refactoring or decomposing if they become overly long or complex. The AI Assistant includes planning steps to promote this (see `CLIPPY.md`, Steps 3.2, 3.4.0.b).
- **Typing:**
    - Strict compliance with chosen data validation libraries (e.g., Pydantic v2).
    - Use the language's features for runtime-checkable interfaces/protocols where available (e.g., `typing.Protocol`).
    - Follow language-specific typing best practices (use modern type annotations).
    - Use domain interfaces for type safety and dependency abstraction.
- **Error Handling:**
    - Implement proper error hierarchy and contextual error handling per domain context.
    - Use centralized utilities for common operations (including error patterns).
    - Implement comprehensive exception hierarchy.
- **Logging:** Ensure consistent usage of the standard logging framework (configured and injected via DI).
- **Stateless Utilities:** Maintain pure, stateless, well-tested functions in dedicated utility modules/files.
- **Domain Models:** Maintain domain models as the single source of truth for all type definitions (enums, types, constants) used across the application. Import domain types/interfaces rather than redefining.

## Architecture & Design

- **Clear Boundaries:** Ensure sensible architecture design with clear boundaries (See `PROJECT_ARCHITECTURE.md`).
- **Separation of Concerns:** Ensure clean separation between domain models, interfaces, and implementations.
- **Protocol-Based Interfaces:** Maintain protocol-based interfaces with clear contracts. Document interface method signatures and async/sync behavior.
- **Single Source of Truth:** Domain models must define all type definitions used across the application.
- **Facade Pattern:** Follow facade pattern for orchestration components.
- **Component Lifecycles:** Utilize the Dependency Injection (DI) container to manage component lifecycles (including Singleton scope where appropriate) instead of manual singletons.
- **Configuration:** Implement Upfront Configuration loading pattern (loading a central configuration object, e.g., `AppConfig`, once at startup via DI). (See `PROJECT_ARCHITECTURE.md` Config Module section)

## Patterns & Practices

- **Dependency Injection (DI):**
    - Ensure proper DI as the primary mechanism for object creation and wiring. (See `PROJECT_ARCHITECTURE.md` DI section).
    - Rely on DI container configuration (e.g., using the container's mapping features) for component mapping where possible, avoiding dedicated registries.
- **Factory/Registry:** Use dedicated Factory or Registry patterns **only** when the specific, stringent conditions outlined in `PROJECT_ARCHITECTURE.md` are met.
- **Command Pattern:** Apply command pattern for CLI interactions (with commands resolved via DI).
- **Decorator Pattern:** Use decorator pattern judiciously for cross-cutting concerns (e.g., error handling, logging context).
- **Template Method:** Apply template method pattern for base implementations with standardized workflows.
- **Diagnostics:** Use diagnostic information pattern for collecting and propagating execution metrics.

## Module & File Structure

- **Standard Structure:** Maintain consistent standardized module structure (See project-specific `PROJECT_ARCHITECTURE.md`).
- **Separation:** Ensure proper separation of base classes and implementations.
- **Domain Modules:** Follow domain module structure for core interfaces.
- **Component Folders:** Implement component-specific folder structure in each module (e.g., `strategies/`, `implementations/`).

## Testing

- **Contract Testing:** Test interface implementations against their defined contracts (e.g., `Protocol`s).
- **Comprehensive Tests:** Add appropriate tests (unit, integration, container tests verifying DI wiring).

## Implementation Workflow (Guide, Not Standard)

*Note: This workflow describes how to implement features, not strictly audit standards. The AI Assistant follows its own detailed, mandatory operational workflow outlined in `CLIPPY.md`.*
1. Define necessary domain interfaces or use existing ones.
2. Implement components, ensuring they declare dependencies clearly (e.g., in constructor/`__init__`) for DI.
3. Register new components explicitly within the main DI container configuration (defined in the project's central DI module).
4. Import domain types/interfaces rather than redefining.
5. Cross-reference interfaces before implementing methods.
6. Add appropriate tests.

Document each step with what is being done and why.
