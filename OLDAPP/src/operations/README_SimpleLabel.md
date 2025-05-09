# Simple Label Operation

The `simpleLabel` operation provides a straightforward way to add labels to geometries without the complexity of the full `labelAssociation` operation.

## Basic Usage

Add this to your `geomLayers` section in your YAML configuration file:

```yaml
- name: MyLayer
  updateDxf: true
  label: myLabelColumn
  shapeFile: "path/to/my/shapefile.shp"
  operations:
    - type: simpleLabel
      # If not specified, it uses the parent layer as source
      # and the label column from the parent layer config
```

## Advanced Configuration

You can customize the simple label operation with these options:

```yaml
- name: LabelLayer
  updateDxf: true
  operations:
    - type: simpleLabel
      sourceLayer: SourceGeometryLayer
      labelColumn: nameColumn
      style: textStyle
```

## Text Styling

The `simpleLabel` operation supports the same text styling options as other text operations.
Here's an example of using a style preset:

```yaml
- name: LabelLayer
  updateDxf: true
  operations:
    - type: simpleLabel
      sourceLayer: Parcel
      labelColumn: FLURSTNR
      style: parcelLabel
```

Or you can define an inline style:

```yaml
- name: LabelLayer
  updateDxf: true
  operations:
    - type: simpleLabel
      sourceLayer: Parcel
      labelColumn: FLURSTNR
      style:
        text:
          height: 2.5
          font: "Arial"
          color: "white"
          attachmentPoint: "MIDDLE_CENTER"
          rotation: 0
```

## Behavior by Geometry Type

- **Polygons**: Labels are placed at the centroid. If the centroid is outside the polygon, the representative point is used instead.
- **Lines**: Labels are placed at the midpoint of the line, with rotation aligned to the line direction.
- **Points**: Labels are placed at the point location.

## Example Configurations

### Simple label using the parent layer's label column

```yaml
- name: Flur
  updateDxf: true
  label: flurname
  shapeFile: "path/to/flur.shp"
  operations:
    - type: simpleLabel
```

### Creating a separate layer with parcel labels

```yaml
- name: ParcelLabels
  updateDxf: true
  style: parcelText
  operations:
    - type: simpleLabel
      sourceLayer: Parcel
      labelColumn: FLURSTNR
```

### Multiple label layers with different styles

```yaml
- name: ParcelLabels
  updateDxf: true
  operations:
    - type: simpleLabel
      sourceLayer: Parcel
      labelColumn: FLURSTNR
      style: parcelText

- name: FlurLabels
  updateDxf: true
  operations:
    - type: simpleLabel
      sourceLayer: Flur
      labelColumn: flurname
      style: flurText
```
