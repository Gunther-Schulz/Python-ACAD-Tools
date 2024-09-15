# Python-ACAD-Tools

## FAQ

Q: Linetype are set in the config.yaml but not available in the CAD file.
A: This is a limitaion of ezdfx. You meend to load all line types into ACAD in the layer editor. Then all Layers should display fine

## Features

- Load and process multiple GIS layers
- Perform various geometric operations (buffer, intersection, difference, etc.)
- Filter layers by attributes
- Download WMTS tiles for specified areas
- Export processed data to DXF format compatible with AutoCAD
- Support for multiple projects with different configurations

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/Python-ACAD-Tools.git
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Configure your project in the `projects.yaml` file. This file defines all the layers, operations, and export settings for each project.

2. Run the main script:
   ```
   python main.py --project <project_name> [--update <layer1,layer2,...]
   ```

   - `<project_name>`: The name of the project as defined in `projects.yaml`
   - `--update`: (Optional) Comma-separated list of layers to update. If not provided, all layers will be processed.

## Configuration (projects.yaml)

The `projects.yaml` file is the heart of the configuration. Here's a breakdown of its structure:

```yaml
folderPrefix: "~/hidrive"
projects:
  - name: ProjectName
    exportFormat: dxf
    dxfVersion: R2018
    crs: EPSG:25833
    dxfFilename: "path/to/output.dxf"
    dxfLayers:
      - name: LayerName
        add: true
        update: true
        shapeFile: "path/to/input.shp"
        label: "attribute_name"
        color: "ColorName"
        # ... other layer properties ...
        operations:
          - type: operation_type
            # ... operation-specific parameters ...
```

### Key Configuration Options:

- `folderPrefix`: Base directory for all relative paths
- `exportFormat`: Output format (currently supports 'dxf')
- `dxfVersion`: AutoCAD DXF version
- `crs`: Coordinate Reference System
- `dxfFilename`: Output DXF file path

### Layer Configuration:

- `name`: Layer name
- `add`: Whether to add this layer if it doesn't exist
- `update`: Whether to update this layer if it already exists
- `shapeFile`: Input shapefile path
- `label`: Attribute to use for labels
- `color`: Layer color in AutoCAD
- `operations`: List of operations to perform on the layer

### Supported Operations:

1. `copy`: Copy geometries from one or more layers
2. `buffer`: Create a buffer around geometries
3. `difference`: Subtract one geometry from another
4. `intersection`: Find the intersection of geometries
5. `filter_by_attributes`: Filter geometries based on attribute values
6. `wmts`: Download WMTS tiles for specified areas
7. `merge`: Merge multiple geometries

## Examples and Operation Options

The `projects.yaml` file allows you to define various operations on layers. Here are some real-life examples and explanations of the available operations:

### 1. Buffer Operation

The buffer operation creates a new geometry by expanding or shrinking the original geometry by a specified distance.

Example:
```yaml
- name: Waldabstand
  color: "Dark Green"
  close: true
  locked: false
  operations:
    - type: buffer
      layers:
        - Wald
      distance: 30
```

This operation creates a 30-meter buffer around the "Wald" (forest) layer and names it "Waldabstand" (forest distance).

### 2. Filter by Attributes

This operation allows you to select specific features from a layer based on attribute values.

Example:
```yaml
- name: Geltungsbereich
  color: "Red"
  locked: false
  close: false
  operations:
    - type: filter_by_attributes
      layers:
        - name: Parcel
          valueList:
            - "81"
            - "87/1"
            - "89"
        - name: Flur
          valueList:
            - Flur 2
        - name: Gemarkung
          valueList:
            - Torgelow am See
```

This operation creates a "Geltungsbereich" (area of application) by filtering parcels, "Flur" (cadastral district), and "Gemarkung" (cadastral area) based on specific values.

### 3. WMTS (Web Map Tile Service) Download

This operation downloads map tiles for a specified area.

Example:
```yaml
- name: WMTS DOP
  color: Black
  locked: true
  operations:
    - type: wmts
      url: "https://www.geodaten-mv.de/dienste/dop_wmts/wmts/1.0.0/WMTSCapabilities.xml"
      layer: "mv_dop"
      zoom: "10"
      proj: "ETRS89UTM33"
      targetFolder: "Öffentlich Planungsbüro Schulz/Projekte/23-25 Maxsolar - Torgelow/GIS/DOP"
      layers:
        - Geltungsbereich
      buffer: 100
```

This operation downloads Digital Orthophotos (DOP) for the "Geltungsbereich" area with a 100-meter buffer.

### 4. Difference Operation

The difference operation subtracts one or more geometries from another.

Example:
```yaml
- name: Baufeld
  color: "Light Red"
  locked: false
  close: true
  operations:
    - type: copy
      layers:
        - Geltungsbereich
    - type: difference
      layers:
        - Wald Abstand
        - Grünfläche
```

This operation creates a "Baufeld" (building area) by copying the "Geltungsbereich" and then subtracting the "Wald Abstand" (forest distance) and "Grünfläche" (green area) from it.

### 5. Intersection Operation

The intersection operation creates a new geometry from the overlapping areas of two or more geometries.

Example:
```yaml
- name: Wald Abstand
  color: "Light Green"
  close: true
  locked: false
  operations:
    - type: buffer
      layers:
        - Wald
      distance: 30
    - type: intersection
      layers:
        - Geltungsbereich
```

This operation creates a 30-meter buffer around the "Wald" layer and then intersects it with the "Geltungsbereich" to create the "Wald Abstand" layer.

### 6. Merge Operation

The merge operation combines multiple geometries into a single layer.

Example:
```yaml
- name: Grünfläche
  color: "Light Green"
  close: true
  locked: false
  operations:
    - type: merge
      layers:
        - Grünflächeinput
        - Temp Grünfl
        - Wald Abstand
```

This operation merges the "Grünflächeinput", "Temp Grünfl", and "Wald Abstand" layers into a single "Grünfläche" layer.

These examples demonstrate how you can use various operations to process and manipulate geographic data in your project. The operations can be combined and chained to create complex workflows for urban planning and GIS applications.

## Output

The script will generate:
1. A DXF file with all processed layers
2. Downloaded WMTS tiles (if specified)
3. Output shapefiles for certain layers (if specified)

## Logging

The script logs its progress and any issues to both the console and a log file. Check the log file for detailed information about the processing steps and any warnings or errors.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.