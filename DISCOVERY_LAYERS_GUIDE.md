# Discovery Layers Feature Guide

## Overview

The Discovery Layers feature allows you to control which layers are scanned during entity discovery. This gives you fine-grained control over which entities get automatically discovered and added to your YAML configurations.

## Configuration

### Global Settings

Add `discovery_layers` to your entity configuration files:

#### In `block_inserts.yaml`:
```yaml
blockInserts:
  - name: "MyBlock"
    blockName: "SampleBlock"
    # ... other settings

# Global settings
discovery: true
discovery_layers: "all"  # Default: discover from all layers
```

#### In `text_inserts.yaml`:
```yaml
textInserts:
  - name: "MyText"
    text: "Sample text"
    # ... other settings

# Global settings
discovery: true
discovery_layers:  # Only discover from these specific layers
  - "TextLayer"
  - "AnnotationLayer"
```

#### In `viewports.yaml`:
```yaml
viewports:
  - name: "MainView"
    # ... other settings

# Global settings
discovery: true
discovery_layers:  # Only discover from these layers
  - "VIEWPORTS"
  - "DEFPOINTS"
```

## Configuration Options

### 1. Discover from All Layers (Default)
```yaml
discovery_layers: "all"
```
- Discovers entities from every layer in the DXF file
- This is the default behavior if `discovery_layers` is not specified

### 2. Discover from Specific Layers Only
```yaml
discovery_layers:
  - "LayerA"
  - "LayerB"
  - "LayerC"
```
- Only discovers entities that are on the specified layers
- Entities on other layers will be ignored during discovery

### 3. Disable Discovery
```yaml
discovery: false
```
- Completely disables discovery regardless of layer settings

## Use Cases

### 1. **Avoid System Layers**
Skip discovery from layers containing system/template entities:
```yaml
# Discover only from user content layers
discovery_layers:
  - "UserBlocks"
  - "ContentLayer"
  - "ImportedData"
```

### 2. **Focus on Specific Workflows**
Limit text discovery to annotation layers:
```yaml
# text_inserts.yaml
discovery_layers:
  - "Annotations"
  - "Labels"
  - "Notes"
```

### 3. **Organize by Purpose**
Different layer sets for different entity types:
```yaml
# block_inserts.yaml - Only structural elements
discovery_layers:
  - "Structures"
  - "Equipment"

# text_inserts.yaml - Only documentation
discovery_layers:
  - "Documentation"
  - "Titles"
```

## Entity Layer Detection

The system automatically detects which layer each entity belongs to:

- **Blocks**: Uses the layer of the block INSERT entity
- **Text**: Uses the layer of the TEXT/MTEXT entity
- **Viewports**: Uses the layer of the VIEWPORT entity

If an entity has no layer assigned, it defaults to layer `"0"`.

## Benefits

1. **Reduced Noise**: Avoid discovering irrelevant entities from system layers
2. **Organized Discovery**: Focus on specific areas of your drawing
3. **Performance**: Faster discovery when scanning fewer layers
4. **Control**: Precise control over which entities get managed

## Examples

### Example 1: Architecture Project
```yaml
# block_inserts.yaml - Only building components
discovery_layers:
  - "Doors"
  - "Windows"
  - "Fixtures"

# text_inserts.yaml - Only room labels and annotations
discovery_layers:
  - "RoomLabels"
  - "Dimensions"
```

### Example 2: Engineering Drawing
```yaml
# block_inserts.yaml - Only symbols and equipment
discovery_layers:
  - "ElectricalSymbols"
  - "MechanicalParts"

# viewports.yaml - Only detail views
discovery_layers:
  - "DetailViewports"
```

### Example 3: Mixed Discovery Strategy
```yaml
# Some entity types discover from all layers
# block_inserts.yaml
discovery_layers: "all"

# Others are more selective
# text_inserts.yaml
discovery_layers:
  - "TitleBlock"
  - "Annotations"
```

## Troubleshooting

### No Entities Discovered
If discovery isn't finding entities you expect:

1. **Check layer names**: Ensure the layer names in your configuration match exactly (case-sensitive)
2. **Verify entity layers**: Check which layer the entities are actually on in your DXF
3. **Enable discovery**: Make sure `discovery: true` is set
4. **Check logs**: Look for discovery debug messages in the output

### Too Many Entities Discovered
If discovery is finding unwanted entities:

1. **Specify layers**: Change from `"all"` to a specific list of layers
2. **Exclude system layers**: Don't include layers like `"0"`, `"DEFPOINTS"`, etc.
3. **Review layer organization**: Consider reorganizing your DXF layer structure

## Logging

The system logs discovery activity:
```
INFO:root:Discovery completed: Found 5 unknown block entities
```

When layer filtering is active, entities on excluded layers are silently skipped (no log messages).
