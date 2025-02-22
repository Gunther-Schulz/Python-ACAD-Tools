# Phase 1: Core Infrastructure

## Overview
This phase establishes the foundational components of the system, including the core type system, configuration management, testing infrastructure, and error handling.

## Goals
- Establish core type system
- Set up project configuration
- Create basic testing infrastructure
- Implement logging and error handling

## Tasks

### 1. Core Type Definitions
- Base protocols and interfaces
- Common data structures
- Error types
- Type validation utilities

#### Implementation Details
```python
# Core protocols
class StyleProvider(Protocol):
    """Central style provider protocol."""
    def get_style(self, style_id: StyleID) -> dict[str, Any]: ...
    def get_default_style(self) -> dict[str, Any]: ...
    def validate_style(self, style_id: StyleID) -> bool: ...

class GeometryProcessor(Protocol):
    """Enhanced geometry processing protocol."""
    def get_dependencies(self) -> set[str]: ...
    def validate_input(self, geometry: GeometryData) -> bool: ...
    def process(self, geometry: GeometryData, context: ProcessingContext) -> GeometryData: ...
    def can_process(self, geometry_type: GeometryType) -> bool: ...
    def get_output_type(self) -> GeometryType: ...

class ComponentFactory(Protocol):
    """Factory for creating drawing components."""
    def create_component(
        self,
        config: ComponentConfig,
        geometry_provider: GeometryProvider,
        style_provider: StyleProvider
    ) -> DrawingComponent: ...
    def validate_config(self, config: ComponentConfig) -> bool: ...
    def get_required_geometry(self, config: ComponentConfig) -> set[str]: ...

# Core data structures
@dataclass
class Style:
    """Immutable style definition."""
    id: StyleID
    properties: dict[str, Any]
    parent: StyleID | None = None

# Error hierarchy
class CoreError(Exception): pass
class ValidationError(CoreError): pass
class ConfigError(ValidationError): pass
class GeometryError(CoreError): pass
class ExportError(CoreError): pass
```

### 2. Configuration System
- Component-specific configuration types
- JSON Schema validation
- Path resolution and validation
- Configuration caching

#### Implementation Details
```python
# Configuration manager with caching and validation
class ConfigManager(AbstractConfigManager):
    """Configuration manager implementation."""
    def __init__(self, project_dir: Path) -> None:
        super().__init__()
        self.project_dir = project_dir
        self.config_dir = project_dir / "config"
        self.root_dir = project_dir.parent.parent
        self._style_cache: dict[str, StyleConfig] | None = None
        self._viewport_cache: dict[str, Any] | None = None
        self._config_cache: dict[str, ConfigDict] = {}
        self._schema_cache: dict[str, SchemaDict] = {}

    def _load_yaml_file(self, filepath: Path, required: bool = True) -> ConfigDict:
        """Load and cache YAML configuration."""
        try:
            if not filepath.exists():
                if required:
                    raise ConfigFileNotFoundError(f"Configuration file not found: {filepath}")
                return {}

            cache_key = str(filepath)
            if cache_key in self._config_cache:
                return self._config_cache[cache_key]

            with filepath.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data is None:
                    data = {}
                self._config_cache[cache_key] = data
                return data

        except yaml.YAMLError as e:
            raise ConfigError(f"Error loading {filepath}: {e!s}") from e

    def _validate_config(self, data: ConfigDict, schema_name: str, config_name: str) -> None:
        """Validate configuration against JSON schema."""
        try:
            schema = self._load_schema(schema_name)
            jsonschema.validate(data, schema)
        except JsonSchemaValidationError as e:
            raise ConfigValidationError(f"Invalid {config_name} configuration: {e!s}") from e

    def _load_schema(self, schema_name: str) -> SchemaDict:
        """Load and cache JSON schema."""
        if schema_name in self._schema_cache:
            return self._schema_cache[schema_name]

        schema_path = self.root_dir / "src" / "config" / "schemas" / f"{schema_name}.json"
        try:
            with schema_path.open("r", encoding="utf-8") as f:
                schema = json.load(f)
                self._schema_cache[schema_name] = schema
                return schema
        except (json.JSONDecodeError, OSError) as e:
            raise ConfigError(f"Error loading schema {schema_name}: {e!s}") from e

# Component-specific configuration types
@dataclass
class ProjectConfig:
    """Project configuration."""
    name: str
    dxf_filename: str
    template: str | None = None
    shapefile_output_dir: str | None = None
    dxf_dump_output_dir: str | None = None

@dataclass
class GeometryLayerConfig:
    """Geometry layer configuration."""
    name: str
    source_file: str
    operations: list[dict[str, Any]]
    style: str | None = None
    update_dxf: bool = False

@dataclass
class BlockInsertConfig:
    """Block insert configuration."""
    name: str
    block_name: str
    position: PositionConfig
    scale: float = 1.0
    rotation: float = 0.0

@dataclass
class TextInsertConfig:
    """Text insert configuration."""
    name: str
    text: str
    position: PositionConfig
    height: float
    style: str | None = None

@dataclass
class ViewportConfig:
    """Viewport configuration."""
    name: str
    center: tuple[float, float]
    height: float
    width: float
    scale: float
```

### 3. Project Structure
```
projects/
└── PROJECT_NAME/
    ├── config/           # Project configuration
    │   ├── project.yaml  # Main project config
    │   ├── layers.yaml   # Layer definitions
    │   ├── styles.yaml   # Style definitions
    │   ├── blocks.yaml   # Block insert definitions
    │   ├── text.yaml     # Text insert definitions
    │   └── viewports.yaml # Viewport definitions
    ├── input/           # Input files
    ├── output/          # Generated files
    └── logs/           # Project logs
```

### 4. Configuration Validation
```python
# JSON Schema validation
project_schema = {
    "type": "object",
    "required": ["name", "dxfFilename"],
    "properties": {
        "name": {"type": "string"},
        "dxfFilename": {"type": "string"},
        "template": {"type": "string"},
        "shapefileOutputDir": {"type": "string"},
        "dxfDumpOutputDir": {"type": "string"}
    }
}

# Path validation
def validate_file_path(
    path: str | Path,
    base_dir: str | Path | None = None,
    must_exist: bool = True,
    allowed_extensions: set[str] | None = None,
    path_type: str = "file",
    folder_prefix: str | None = None,
) -> None:
    """Validate file paths with comprehensive checks."""
    path_obj = Path(path) if isinstance(path, str) else path
    if base_dir:
        base_dir_obj = Path(base_dir) if isinstance(base_dir, str) else base_dir
        path_obj = base_dir_obj / path_obj

    if folder_prefix:
        path_obj = Path(folder_prefix) / path_obj

    if must_exist and not path_obj.exists():
        raise ConfigError(f"Path does not exist: {path_obj}")

    if path_type == "file":
        if must_exist and not path_obj.is_file():
            raise ConfigError(f"Path is not a file: {path_obj}")
        if allowed_extensions and path_obj.suffix.lower() not in allowed_extensions:
            raise ConfigError(
                f"Invalid file extension for {path_obj}. "
                f"Allowed extensions: {', '.join(allowed_extensions)}"
            )
    elif path_type == "directory":
        if must_exist and not path_obj.is_dir():
            raise ConfigError(f"Path is not a directory: {path_obj}")
```

### 3. Testing Infrastructure
- Unit test framework setup
- Integration test framework
- Test utilities
- CI/CD pipeline configuration

#### Implementation Details
```python
# Example test utilities
@pytest.fixture
def test_config() -> Config:
    """Create test configuration."""
    return Config(
        name="test_project",
        project_dir=Path("tests/data/test_project")
    )

def create_test_geometry() -> GeometryData:
    """Create test geometry data."""
    return {
        "type": "Point",
        "coordinates": [0, 0]
    }
```

### 4. Logging and Error Handling
- Logging configuration
- Error types and handling
- Debug utilities
- Performance monitoring

#### Implementation Details
```python
# Example logging setup
def setup_logger(name: str, log_file: Path | None = None) -> Logger:
    """Set up logging configuration."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Add console handler
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(console)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(str(log_file))
        logger.addHandler(file_handler)

    return logger
```

## Deliverables

### 1. Core Component
- Complete type system implementation
- Error hierarchy
- Utility functions
- Base protocols

### 2. Configuration System
- YAML configuration loader
- Schema validation system
- Path resolution utilities
- Configuration types

### 3. Testing Framework
- PyTest configuration
- Test utilities
- Fixtures
- CI/CD pipeline

### 4. Logging System
- Logging configuration
- Error handling system
- Debug utilities
- Performance monitoring tools

## Success Criteria

1. **Type System**
   - All core types defined
   - Type checking passes
   - Clear type hierarchy
   - Documentation complete

2. **Configuration**
   - YAML loading works
   - Schema validation active
   - Path resolution functional
   - Error handling in place

3. **Testing**
   - Unit tests running
   - Integration tests working
   - CI/CD pipeline active
   - Test coverage >80%

4. **Logging**
   - Logging configured
   - Error handling working
   - Debug tools available
   - Performance monitoring active

## Dependencies
- Python 3.12+
- PyTest
- PyYAML
- Type checking tools
- CI/CD platform

## Timeline
- Week 1-2: Core type system
- Week 3-4: Configuration system
- Week 5-6: Testing infrastructure
- Week 7-8: Logging and monitoring

## Risks and Mitigation

### Risks
1. Type system complexity
2. Configuration edge cases
3. Test coverage gaps
4. Performance overhead

### Mitigation
1. Regular type checking
2. Comprehensive testing
3. Coverage monitoring
4. Performance profiling
