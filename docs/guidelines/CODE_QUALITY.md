# Code Quality Guidelines

## Overview
This document outlines the code quality standards and best practices for the Python ACAD Tools project, based on our tooling configuration and quality requirements.

## Related Documents
- [Boundaries](BOUNDARIES.md) - Component boundary rules
- [Testing Guidelines](TESTING.md) - Testing requirements
- [Logging Guidelines](LOGGING.md) - Logging standards
- [INDEX](../INDEX.md) - Documentation index

## Version Applicability
- Python Version: 3.12+
- Last Updated: 2024-02-22
- Status: Draft

## Dependencies
- Static type checkers (mypy, pyright)
- Runtime type validation (beartype)
- Code formatters (black, isort)
- Linters (flake8, pylint)
- Documentation tools (pydocstyle)
- Testing frameworks (pytest)

## Python Version

- Python 3.12 or higher is required
- Use modern Python features and type hints
- Leverage new Python 3.12+ functionality where appropriate

## Code Style

### Line Length and Indentation
- Maximum line length: 100 characters
- Indentation: 4 spaces
- Maximum docstring length: 100 characters
- No implicit string concatenation across lines

### Quotes
- Double quotes for all string literals
- Double quotes for docstrings
- Double quotes for multiline strings

### Imports
1. **Import Order**
   ```python
   from __future__ import annotations  # Required in all files

   # Standard library imports
   import os
   import sys
   from pathlib import Path
   from typing import Any

   # Third-party imports
   import numpy as np
   import shapely

   # Core types
   from src.core.types import BaseType

   # Component types
   from src.geometry.types import GeometryType

   # First-party imports
   from src import module

   # Local imports
   from . import local_module
   ```

2. **Import Rules**
   - No relative imports
   - Single-line imports only
   - Combine `as` imports
   - Import types through `core.types` or component types
   - Access implementations through `dependencies.py`

### Type Checking
- Strict type checking enabled
- Runtime evaluated base classes:
  - `BaseModel`
  - `Protocol`
  - `TypedDict`
  - `BaseConfigManager`
  - `BaseGeometryManager`
  - `BaseExportManager`
- Runtime evaluated decorators:
  - `@dataclass`
  - `@attrs`
  - `@beartype`

## Code Organization

### Module Structure
1. **Types Module**
   - Define interfaces and protocols
   - Export type definitions
   - No implementation details

2. **Dependencies Module**
   - Declare component dependencies
   - Configure dependency injection
   - Import implementations

3. **Implementation Modules**
   - Contain actual implementations
   - Follow single responsibility
   - Keep complexity low

### Component Boundaries
1. **Access Rules**
   - No access to internal modules
   - No access to implementation details
   - Access services through dependency injection
   - Access repositories through dependency injection
   - Access managers through dependency injection

2. **Type Import Rules**
   - Import core types through `core.types`
   - Import component types through respective type modules
   - No direct imports from implementation modules

## Code Quality Checks

### Enabled Rules
1. **Style Checks**
   - PEP 8 compliance (E, W)
   - Import sorting (I)
   - Quotes consistency (Q)
   - Docstring style (D)
   - Naming conventions (N)

2. **Code Quality**
   - Complexity checks (C)
   - Bug prevention (B)
   - Type checking (TCH)
   - Return statement validation (RET)
   - Self usage validation (SLF)
   - Argument usage (ARG)

3. **Best Practices**
   - Use pathlib over os.path (PTH)
   - Modern datetime usage (DTZ)
   - Proper logging format (G)
   - Pytest style (PT)
   - Import conventions (ICN)

### Complexity Rules
- Maximum cyclomatic complexity: 10
- Encourage list comprehensions
- Simplify complex expressions
- Refactor long functions

## Documentation

### Docstring Standards
- Google docstring convention
- Required for all public APIs
- Ignored for properties and decorators
- Code examples limited to 80 characters

### Type Annotations
- Required for all functions
- Required for class attributes
- Required for complex data structures
- Clear parameter and return types

## Testing

### Test Organization
- Tests excluded from main code quality checks
- Separate test configuration
- Allow necessary test-specific patterns
- Maintain test readability

### Test Style
- No parentheses for fixtures
- No parentheses for marks
- Clear test names and organization
- Proper test documentation

## Legacy Code

- Legacy code in `src_old` ignored
- Migration path required for updates
- Document technical debt
- Plan for modernization
