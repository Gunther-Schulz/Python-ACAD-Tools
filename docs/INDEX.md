# Documentation Index

## Overview
This document serves as the primary navigation guide and reference for the Python ACAD Tools project documentation.

## Quick Start

1. **Installation**
   ```bash
   # Create conda environment
   conda env create -f environment.yml
   conda activate pycad
   ```

2. **Basic Usage**
   ```bash
   # Process a project
   python -m src.main PROJECT_NAME
   ```

3. **Project Structure**
   ```
   projects/
   └── PROJECT_NAME/
       ├── config/           # Configuration files
       │   ├── project.yaml  # Project settings
       │   ├── layers.yaml   # Layer definitions
       │   └── styles.yaml   # Style definitions
       ├── input/           # Input files
       ├── output/          # Generated files
       └── logs/           # Log files
   ```

## Documentation Map

### 1. User Documentation
- [User Guide](user/GUIDE.md) - Getting started
- [Configuration Guide](user/CONFIG.md) - Configuration options
- [Examples](examples/) - Example projects and configurations
- [Troubleshooting](user/TROUBLESHOOTING.md) - Common issues and solutions

### 2. Development Documentation
- [Architecture](architecture/ARCHITECTURE.md) - System design and components
- [Development Phases](development/PHASES.md) - Implementation phases
- [API Reference](api/) - API documentation

### 3. Guidelines
- [Code Quality](guidelines/CODE_QUALITY.md) - Coding standards
- [Testing](guidelines/TESTING.md) - Testing requirements
- [Integration](guidelines/INTEGRATION.md) - Integration patterns
- [Boundaries](guidelines/BOUNDARIES.md) - Component boundaries
- [Logging](guidelines/LOGGING.md) - Logging standards

## Version History

| Version | Date | Changes | Status |
|---------|------|---------|--------|
| 0.1.0   | 2024-02-22 | Initial documentation | Draft |
| 0.2.0   | 2024-02-22 | Added TDD guidelines | Draft |
| 0.3.0   | 2024-02-22 | Added logging guidelines | Draft |
| 0.4.0   | 2024-02-22 | Added integration patterns | Draft |

## Documentation TODOs

### High Priority
- [ ] repsect this:
      "I removed the test files as they are outdated completely. The way we will approach this is build test for existing code instead of using TDD. Unless we write new code, then we use TDD. It sa mixed approach until we have enough tests for the existing code."
- [ ] Finalize code flow between components.
- [ ] Finalyze configuration structure definition as this is front facing and thus very important!!!
- [ ] Keep main.py up-to-date with latest changes. It should always be able to run as is with --verify.
- [ ] Multiple Export Formats - What does this really do? whats the point? This realtes to how we can load layres from arbitrary DXF files, preprocess them and save them to different formats.
      Export different layers to different formats
      Configure format-specific parameters
      Create reference drawings when needed
      Where does this live in code?
- [ ] Reduced DXF implementation
      - [ ] Where should this live in code?
- [ ] Complete logging guidelines
- [ ] Enhance type management documentation
- [x] Add integration patterns
- [ ] Expand error handling examples

### Medium Priority
- [ ] Add more integration test examples
- [ ] Expand API documentation
- [ ] Add user guides

### Low Priority
- [ ] Add more code examples
- [ ] Create video tutorials
- [ ] Add troubleshooting guides
- [ ] Create quick reference cards
