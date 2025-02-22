# Selective Layer Export Guide

## Overview
This guide explains how to selectively export layers using the Python ACAD Tools project's configuration system.

## Related Documents
- [Code Quality Guidelines](../guidelines/CODE_QUALITY.md)
- [Integration Patterns](../guidelines/INTEGRATION.md)
- [INDEX](../INDEX.md)

## Version Applicability
- Python Version: 3.12+
- Last Updated: 2024-02-22
- Status: Draft

## Project Setup

### 1. Project Structure
Create a project directory with the required structure:
```
projects/
└── my_project/
    ├── config/
    │   ├── project.yaml    # Project configuration
    │   ├── layers.yaml     # Layer definitions
    │   └── styles.yaml     # Style definitions
    ├── input/             # Input files
    ├── output/            # Output files
    └── logs/             # Log files
```

### 2. Project Configuration
Create `config/project.yaml`:
```yaml
name: "my_project"
dxfFilename: "input/source.dxf"
shapefileOutputDir: "output/shapefiles"
dxfDumpOutputDir: "output/dxf"
```

### 3. Layer Configuration
Create `config/layers.yaml`:
```yaml
layers:
  - name: "WALLS"
    sourceFile: "input/source.dxf"
    updateDxf: true
    operations: []  # No preprocessing

  - name: "WINDOWS"
    sourceFile: "input/source.dxf"
    updateDxf: true
    operations:
      - type: "block_exploder"
        enabled: true

  - name: "SITE_BOUNDARY"
    sourceFile: "input/source.dxf"
    updateDxf: false
    operations:
      - type: "circle_extractor"
        enabled: true
        parameters:
          minRadius: 0.5
          extractCenterPoints: true
    style: "site_boundary_style"
```

### 4. Style Configuration
Create `config/styles.yaml`:
```yaml
styles:
  site_boundary_style:
    color: "red"
    linetype: "CONTINUOUS"
    lineweight: 0.5
    plot: true
```

## Running the Export

### Basic Usage
```bash
# Process the project
python -m src.main my_project

# With custom project directory
python -m src.main my_project --project-dir /path/to/projects

# With logging
python -m src.main my_project --log-file logs/processing.log
```

## Configuration Details

### 1. Layer Configuration Options
```yaml
name: "LAYER_NAME"          # Layer name (required)
sourceFile: "path/to/file"  # Source file path (required)
updateDxf: true/false      # Whether to update DXF (optional)
style: "style_name"        # Style reference (optional)
operations:                # List of operations (optional)
  - type: "operation_name"
    enabled: true/false
    parameters:
      param1: value1
```

### 2. Available Operations
- `block_exploder`: Explodes blocks into constituent geometries
- `circle_extractor`: Extracts circles and center points
- `basepoint_extractor`: Extracts basepoints from geometry

### 3. Style Configuration
```yaml
style_name:
  color: "color_name" | ACI_code
  linetype: "line_type_name"
  lineweight: float_value
  plot: true/false
```

## Best Practices

1. **Project Organization**
   - Use consistent naming for layers
   - Keep configurations in the config directory
   - Use relative paths from project root
   - Follow the standard project structure

2. **Layer Management**
   - Group related layers together
   - Use descriptive layer names
   - Document layer purposes
   - Consider dependencies

3. **Operation Configuration**
   - Enable only needed operations
   - Validate operation parameters
   - Test operations individually
   - Document operation chains

4. **Style Management**
   - Use consistent style naming
   - Document style purposes
   - Reuse common styles
   - Test style rendering

## Troubleshooting

### Common Issues

1. **Configuration Errors**
   - Check YAML syntax
   - Verify file paths
   - Validate style references
   - Check operation parameters

2. **Processing Errors**
   - Check layer existence
   - Verify operation compatibility
   - Review operation parameters
   - Check log files

3. **Export Issues**
   - Verify output directories
   - Check file permissions
   - Validate export formats
   - Review error messages

## See Also
- [Example Configurations](../examples/)
- [API Documentation](../api/)
- [Development Guide](../development/)
