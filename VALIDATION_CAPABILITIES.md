# Configuration Validation Capabilities

## Overview

Our comprehensive configuration validation system provides extensive checking for `geom_layers.yaml` and other configuration files, catching errors, performance issues, and security risks before they cause runtime problems.

## ✅ What IS Validated

### 1. **Unknown Settings Detection**
```yaml
# ❌ These will be caught:
- name: "buildings"
  geojsonFile: "@data.test"
  unknownSetting: "value"        # ❌ Unknown key detected
  labelColum: "name"             # ❌ Typo detected with suggestion
  styl: "building_style"         # ❌ Typo detected with suggestion
```

**Output:**
```
⚠️  Layer 'buildings': Unknown key 'unknownSetting'
⚠️  Layer 'buildings': Unknown key 'labelColum'. Did you mean 'labelColumn'?
⚠️  Layer 'buildings': Unknown key 'styl'. Did you mean 'style'?
```

### 2. **Style Preset Validation**
```yaml
# ❌ These will be caught:
- name: "buildings"
  geojsonFile: "@data.test"
  style: "non_existent_style"    # ❌ Style doesn't exist

- name: "roads"
  geojsonFile: "@data.test"
  style: "building_styl"         # ❌ Typo in style name
```

**Output:**
```
❌ Layer 'buildings': Style preset 'non_existent_style' not found
❌ Layer 'roads': Style preset 'building_styl' not found. Did you mean 'building_style'?
```

### 3. **File Reference Validation**
```yaml
# ❌ These will be caught:
- name: "buildings"
  geojsonFile: "@data.missing_file"     # ❌ File doesn't exist

- name: "roads"
  shapeFile: "path/to/missing.shp"     # ❌ File doesn't exist

- name: "parcels"
  geojsonFile: "data.txt"              # ❌ Wrong file extension
```

**Output:**
```
❌ Layer 'buildings' geojsonFile: File does not exist: /path/to/missing_file.geojson
❌ Layer 'roads' shapeFile: File does not exist: path/to/missing.shp
❌ Layer 'parcels' geojsonFile: File must have one of these extensions: ['.geojson', '.json']
```

### 4. **Operation Type Validation**
```yaml
# ❌ These will be caught:
- name: "buffered_buildings"
  geojsonFile: "@data.test"
  operations:
    - type: "invalid_operation"        # ❌ Unknown operation
      distance: 10.0

    - type: "bufer"                    # ❌ Typo in operation type
      distance: 10.0
```

**Output:**
```
❌ Layer 'buffered_buildings' operation[0]: Unknown operation type 'invalid_operation'
❌ Layer 'buffered_buildings' operation[1]: Unknown operation type 'bufer'. Did you mean 'buffer'?
```

### 5. **Enhanced Operation Parameter Validation**
```yaml
# ❌ These will be caught:
- name: "advanced_buffer"
  geojsonFile: "@data.test"
  operations:
    - type: "buffer"
      distance: -5.0                   # ❌ Negative distance
      cap_style: "invalid_cap"         # ❌ Invalid cap style
      join_style: "invalid_join"       # ❌ Invalid join style
      resolution: -1                   # ❌ Negative resolution

    - type: "transform"
      target_crs: "INVALID_CRS"        # ❌ Invalid CRS
      source_crs: "EPSG:99999"         # ❌ Invalid EPSG code

    - type: "filter"
      spatial_predicate: "invalid_predicate"  # ❌ Invalid spatial predicate
```

**Output:**
```
❌ operation[0]: buffer distance cannot be negative, got -5.0
❌ operation[0]: Invalid cap style 'invalid_cap'. Valid values: {'round', 'square', 'flat'}
❌ operation[0]: Invalid join style 'invalid_join'. Valid values: {'round', 'mitre', 'bevel'}
❌ operation[0]: buffer resolution must be positive, got -1
❌ operation[1]: target_crs Invalid CRS 'INVALID_CRS'
❌ operation[1]: source_crs EPSG code 99999 is outside valid range (1-32767)
❌ operation[2]: Invalid spatial predicate 'invalid_predicate'. Valid values: {'intersects', 'contains', 'within', ...}
```

### 6. **Enhanced Style Property Validation**
```yaml
# ❌ These will be caught:
- name: "styled_layer"
  geojsonFile: "@data.test"
  style:
    layer:
      linetype: "INVALID_LINETYPE"     # ❌ Invalid linetype
      transparency: 1.5                # ❌ Transparency > 1.0
      frozen: true
      plot: true                       # ❌ Conflict: frozen layers shouldn't plot
    text:
      height: -2.0                     # ❌ Negative height
      attachmentPoint: "INVALID_POINT" # ❌ Invalid attachment point
      flowDirection: "INVALID_FLOW"    # ❌ Invalid flow direction
      lineSpacingStyle: "INVALID_SPACING" # ❌ Invalid spacing style
```

**Output:**
```
❌ Layer 'styled_layer' layer style: Invalid linetype 'INVALID_LINETYPE'
❌ Layer 'styled_layer' layer style: transparency must be between 0.0 and 1.0, got 1.5
❌ Layer 'styled_layer': frozen layers should not be set to plot
❌ Layer 'styled_layer' text style: text height must be positive, got -2.0
❌ Layer 'styled_layer' text style: Invalid attachment point 'INVALID_POINT'
❌ Layer 'styled_layer' text style: Invalid flow direction 'INVALID_FLOW'
❌ Layer 'styled_layer' text style: Invalid line spacing style 'INVALID_SPACING'
```

### 7. **Performance Monitoring**
```yaml
# ❌ These will trigger performance warnings:
- name: "performance_issues"
  geojsonFile: "@data.test"
  operations:
    - type: "buffer"
      distance: 15000.0              # ❌ Exceeds 10km threshold
    # ... 11 more operations         # ❌ Exceeds 10 operation limit

main:
  maxMemoryMb: 256                   # ❌ Below 512MB recommendation
```

**Output:**
```
❌ operation[0]: buffer distance (15000.0) exceeds recommended maximum (10000.0) - may cause performance issues
⚠️  Operation chain length (11) exceeds recommended maximum (10) - may cause performance issues
⚠️  main.max_memory_mb: Memory limit below 512MB may cause performance issues
```

### 8. **Security Validation**
```yaml
# ❌ These will trigger security warnings:
pathAliases:
  data:
    dangerous: "../../../etc/passwd"  # ❌ Path traversal attempt

geomLayers:
  - name: "security_risk"
    geojsonFile: "@data.dangerous"   # ❌ Resolves to dangerous path
```

**Output:**
```
⚠️  Path alias 'data.dangerous' contains '..' which may be a security risk
```

### 9. **Dependency and Consistency Validation**
```yaml
# ❌ These will be caught:
- name: "circular_dependency"
  geojsonFile: "@data.test"
  operations:
    - type: "union"
      layers: ["circular_dependency"] # ❌ References itself

- name: "invalid_overlay"
  geojsonFile: "@data.test"
  operations:
    - type: "difference"
      overlay_layer: "invalid_overlay" # ❌ Same as target layer
```

**Output:**
```
❌ Layer 'circular_dependency': Operation 1 creates circular dependency
❌ Layer 'invalid_overlay': Operation 1: overlay layer cannot be the same as the target layer
```

### 10. **Data Integrity Validation**
```yaml
# ❌ These will be caught:
- name: "data_issues"
  geojsonFile: "@data.test"
  labelColumn: ""                    # ❌ Empty column name
  updateDxf: "yes"                   # ❌ Should be boolean
  linetypeScale: -1.0                # ❌ Should be positive
  selectByProperties:
    "": "value"                      # ❌ Empty property name
```

**Output:**
```
❌ Layer 'data_issues': labelColumn must be a non-empty string
⚠️  Layer 'data_issues': updateDxf should be a boolean value
❌ Layer 'data_issues': linetypeScale must be positive, got -1.0
❌ Layer 'data_issues': selectByProperties property name must be a non-empty string
```

## 🎯 Enhanced Validation Features

### **Performance Monitoring**
- **Buffer Distance Thresholds**: Warns when buffer distances exceed 10km
- **File Size Warnings**: Alerts for files larger than 100MB
- **Operation Chain Limits**: Warns when operation chains exceed 10 operations
- **Memory Usage Warnings**: Alerts when memory limits are below 512MB
- **Feature Count Warnings**: Future support for 50k+ feature warnings

### **Operation Parameter Validation**
- **Buffer Operations**: Validates cap_style, join_style, resolution, distance
- **Transform Operations**: Validates CRS for both source and target
- **Filter Operations**: Validates spatial predicates
- **Scale Operations**: Ensures positive scale factors
- **Rotate Operations**: Requires angle parameter
- **Missing Parameter Detection**: Catches required parameters

### **Style Property Validation**
- **Text Styles**: Validates attachment points, flow direction, line spacing
- **Layer Styles**: Validates linetype patterns, transparency ranges
- **Hatch Styles**: Validates patterns and scale factors
- **Style Consistency**: Checks for logical conflicts (e.g., frozen vs plot)
- **Color Validation**: Validates ACI codes and color names

### **Security Validation**
- **Path Traversal Detection**: Identifies dangerous `../` patterns
- **Path Alias Security**: Warns about risky path aliases
- **File Extension Validation**: Ensures proper file types
- **Directory Existence**: Checks parent directories exist
- **Permission Validation**: Validates output path permissions

### **Intelligent Suggestions**
- **Typo Detection**: Uses Levenshtein distance for suggestions
- **Case Mismatch Detection**: Identifies case-sensitive issues
- **Column Name Suggestions**: Suggests similar column names
- **Performance Optimization**: Provides performance tips

## 📋 Valid Configuration Reference

### **Operation Types**
```yaml
# All valid operation types:
buffer               # Buffer geometries
intersection         # Intersect geometries
union                # Union geometries
difference           # Difference operation
simplify             # Simplify geometries
transform            # Transform coordinates
filter               # Filter features
merge                # Merge features
clip                 # Clip geometries
dissolve             # Dissolve boundaries
envelope             # Create envelope
bounding_box         # Create bounding box
rotate               # Rotate geometries
scale                # Scale geometries
translate            # Translate geometries
offset_curve         # Offset curves
symmetric_difference # Symmetric difference
connect_points       # Connect points
create_circles       # Create circles
copy                 # Copy features
filterByIntersection # Filter by intersection
simpleLabel          # Simple labeling
wmts                 # WMTS operations
wms                  # WMS operations
contour              # Contour operations
```

### **Buffer Operation Parameters**
```yaml
- type: "buffer"
  distance: 10.0                    # Required: buffer distance
  cap_style: "round"                # Valid: round, flat, square
  join_style: "round"               # Valid: round, mitre, bevel
  resolution: 16                    # Positive integer
  layers: ["layer_name"]            # Required: source layers
```

### **Transform Operation Parameters**
```yaml
- type: "transform"
  target_crs: "EPSG:4326"          # Required: valid CRS
  source_crs: "EPSG:3857"          # Optional: source CRS
```

### **Filter Operation Parameters**
```yaml
- type: "filter"
  spatial_predicate: "intersects"   # Valid: intersects, contains, within, etc.
  layers: ["layer_name"]            # Required: source layers
```

### **Text Style Properties**
```yaml
text:
  height: 3.0                       # Positive number
  attachmentPoint: "TOP_LEFT"       # Valid attachment points
  flowDirection: "LEFT_TO_RIGHT"    # Valid flow directions
  lineSpacingStyle: "AT_LEAST"      # Valid spacing styles
  font: "Arial"
  color: "red"
```

### **Valid Attachment Points**
```
TOP_LEFT, TOP_CENTER, TOP_RIGHT
MIDDLE_LEFT, MIDDLE_CENTER, MIDDLE_RIGHT
BOTTOM_LEFT, BOTTOM_CENTER, BOTTOM_RIGHT
```

### **Valid Flow Directions**
```
LEFT_TO_RIGHT, TOP_TO_BOTTOM, BY_STYLE
```

### **Valid Line Spacing Styles**
```
AT_LEAST, EXACT
```

### **Valid Spatial Predicates**
```
intersects, contains, within, touches, crosses, overlaps,
disjoint, equals, covers, covered_by
```

## 📊 Performance Thresholds

| Setting | Threshold | Action |
|---------|-----------|--------|
| Buffer Distance | 10,000m | Warning |
| File Size | 100MB | Warning |
| Operation Chain | 10 operations | Warning |
| Memory Limit | 512MB | Warning |
| Feature Count | 50,000 features | Warning (future) |

## 🚨 Validation Categories

### **ERRORS (Block Processing)**
- Missing required fields
- Invalid data types
- Non-existent file references
- Invalid CRS specifications
- Circular dependencies
- Unknown operation types
- Invalid parameter values
- Negative numeric values where positive required

### **WARNINGS (Allow with Notice)**
- Performance threshold exceeded
- Unknown configuration keys
- Typos with suggestions
- Security risks (path traversal)
- Memory usage concerns
- Style conflicts
- Case mismatches
- Boolean type mismatches

### **SUGGESTIONS (Helpful Hints)**
- Alternative spellings for typos
- Similar column names
- Performance optimization tips
- Best practice recommendations
- Configuration improvements

## 🔧 Integration

### **Automatic Validation**
The validation system is automatically integrated into the configuration loading process:

```python
# Validation happens automatically when loading project configs
config = config_loader.load_specific_project_config("project_name", projects_root)
# Any validation errors will be caught and reported with detailed messages
```

### **Manual Validation**
You can also run validation manually:

```python
from src.domain.config_validation import ConfigValidationService

validator = ConfigValidationService(base_path="project/path")
try:
    validated_config = validator.validate_project_config(config_data, "config_file.yaml")
    print("✅ Configuration is valid!")

    # Check for warnings
    if validator.validation_warnings:
        for warning in validator.validation_warnings:
            print(f"⚠️  {warning}")

except ConfigValidationError as e:
    print(f"❌ Validation failed: {e}")
    for error in e.validation_errors:
        print(f"   • {error}")
```

## 📈 Benefits

1. **Early Error Detection**: Catch configuration issues before runtime
2. **Intelligent Suggestions**: Get helpful suggestions for typos and mistakes
3. **Comprehensive Coverage**: Validates all aspects of configuration files
4. **Clear Error Messages**: Understand exactly what's wrong and how to fix it
5. **Performance Monitoring**: Identify potential performance bottlenecks
6. **Security Awareness**: Detect potential security risks
7. **Dependency Validation**: Ensure all references are valid
8. **Style Consistency**: Maintain consistent styling across layers
9. **Data Integrity**: Ensure data references are valid and accessible
10. **Best Practices**: Encourage optimal configuration patterns

## 🎯 Example Comprehensive Validation Session

```bash
$ python test_comprehensive_validation_demo.py

🔍 Comprehensive Enhanced Validation Demonstration
======================================================================

📁 Testing: projects/test_project/geom_layers_comprehensive_validation_test.yaml
📋 Description: ❌ Comprehensive Validation Issues
--------------------------------------------------
❌ Validation Failed: Configuration validation failed with 65 errors

🚨 65 Validation Errors:
   1. main.crs: EPSG code 99999 is outside valid range (1-32767)
   2. main.dxf_version: Invalid DXF version 'R2025'
   3. main.export_format: Invalid export format 'invalid'
   4. layer 'performance_warning_buffer' operation[0]: buffer distance (15000.0) exceeds recommended maximum (10000.0)
   5. layer 'invalid_buffer_params' operation[0]: Invalid cap style 'invalid_cap'
   6. Layer 'invalid_text_style' text style: Invalid attachment point 'INVALID_POINT'
   7. Layer 'invalid_layer_style': frozen layers should not be set to plot
   8. layer 'invalid_transform' operation[0]: Invalid CRS 'INVALID_CRS'
   9. layer 'invalid_filter' operation[0]: Invalid spatial predicate 'invalid_predicate'
   10. Layer 'circular_dependency': Operation 1 creates circular dependency
   ... and 55 more detailed errors

⚠️  6 Validation Warnings:
   1. main.max_memory_mb: Memory limit below 512MB may cause performance issues
   2. layer 'long_operation_chain': Operation chain length (11) exceeds recommended maximum (10)
   3. Layer 'invalid_settings': updateDxf should be a boolean value
   4. Path alias 'data.dangerous' contains '..' which may be a security risk
   ... and 2 more warnings
```

This comprehensive validation system ensures that your `geom_layers.yaml` configurations are correct, secure, performant, and will work as expected when processed by the application.

**Total validation checks: 50+ different types covering every aspect of configuration integrity!**
