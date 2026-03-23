# Python-ACAD-Tools Refactor Plan

## What this tool does
Config-driven GIS-to-DXF pipeline. User writes YAML configs defining geometry layers + operations, runs CLI, gets reproducible DXF + shapefile output. Supports bidirectional sync with AutoCAD (push/pull), hatching, viewports, block inserts, text, legends, WMTS/WMS tiles.

## Codebase
- Location: ~/dev/Gunther-Schulz/Python-ACAD-Tools
- 14K+ lines in src/, 36 operation modules in src/operations/
- Entry point: main.py -> ProjectProcessor
- Key files: layer_processor.py (orchestrator), dxf_exporter.py (GeoDataFrame->DXF), dxf_utils.py (entity creation), unified_sync_processor.py (bidirectional sync), project_loader.py (YAML config)
- Currently uses conda env `acad` -- should move to editable pip install (see below)
- Real projects in projects/ (Plasten, Friedrichshof, Bibow, Waren, Torgelow, etc.)

## Shared library
gis_utils (find via `pip show gis-utils`, v0.3.0) is the shared utility library. Python-ACAD-Tools should import from it where there's overlap (geometry ops, DXF helpers, markdown tables). gis_utils includes: DXF extraction, geometry utilities (make_valid, subtract, morphological filter, distance_to_nearest), reporting, OSM downloader, workflow runner.

## How to start the refactor
1. Read this file for context
2. Look at projects/Plasten/geom_layers.yaml for the most complex real example
3. Discuss usability before touching code
4. Work on branch `refactor/v2`

## Installation & project model (new -- follow gis_utils pattern)

### Editable install
The tool should be installed as an editable pip package, same as gis_utils:
```bash
pip install -e ~/dev/Gunther-Schulz/Python-ACAD-Tools
```
This means edits to source files take effect immediately. The tool's source lives in its git repo, not copied into site-packages.

### Project configs live OUTSIDE the tool repo
Currently projects live in `Python-ACAD-Tools/projects/`. They should live in their own directories (anywhere on disk), NOT inside the tool repo. The tool repo contains only the engine + operations. Project folders contain only YAML configs + data paths.

### Init command
The tool should have an init command (like `gis-workflow init`):
```bash
python-acad init "/path/to/My Project"
```
This creates:
- `project.yaml` -- starter config with CRS, DXF paths, sync settings, buffer defaults, auto-repair settings
- `layers/` -- directory for layer definition YAML files (can be split however user likes)
- `CLAUDE.md` -- AI-readable project context (user-editable, never overwritten on re-init)

### Generated CLAUDE.md per project
When a Claude session starts in a project folder, it reads CLAUDE.md and immediately knows:
- This is a Python-ACAD-Tools project, here's how to run it
- Here's what's project-specific config vs what belongs as a new operation/extension in the core tool
- Here's where the tool source is (`pip show python-acad-tools`) for when something needs to be added to the engine
- If editing the tool source: commit and push separately (it's a different git repo)

---

## Agreed design decisions

### 1. Keep the flat list format
The current mental model works: layers are a flat list, each layer can reference other layers by name, the engine resolves dependencies automatically (not top-down). No new structural paradigm needed. The problem is verbosity, not structure.

### 2. Multi-file layer splitting
Instead of one massive geom_layers.yaml (1800 lines for Plasten), users can split layer definitions across multiple YAML files in a `layers/` directory. The engine concatenates them into one flat list before processing. File organization is purely for human readability -- the engine doesn't care about file boundaries or ordering.

Example:
```
project/
  project.yaml
  layers/
    01_inputs.yaml
    02_exclusions.yaml
    03_geltungsbereich.yaml
    04_baugrenze.yaml
    05_hatching.yaml
    06_reports.yaml
```

### 3. Project-level defaults

#### Buffer defaults
Stop repeating `joinStyle: round, capStyle: round, quadSegs: 32` on every buffer operation. Define once in project.yaml, override per-operation only when different.

```yaml
# project.yaml
bufferDefaults:
  joinStyle: round
  capStyle: round
  quadSegs: 32
```

#### Auto-repair after boolean operations
The 4-stage cleanup (removeDegenerateSpikes, removeProtrusions, removeSliversErosion, repair) appears after nearly every difference/intersection. Define default repair settings in project.yaml; the engine applies them automatically after boolean ops. Opt out per-operation with `autoRepair: false`.

```yaml
# project.yaml
autoRepair:
  removeDegenerateSpikes:
    tolerance: 0.01
    simplifyTolerance: 0.05
    minSpikeLength: 0.1
  removeProtrusions:
    bufferDistance: 0.5
    minProtrusionLength: 1.0
  removeSliversErosion:
    erosionDistance: 0.2
  repair:
    minArea: 20
    removeEmptyGeometries: true
    removeFailures: true
```

### 4. `enabled: false` instead of commenting out
Layers can be disabled without commenting. Waren's 1296-line config is 95% comments -- this would make disabled layers scannable and re-enableable without risking YAML syntax errors.

```yaml
- name: Bahntrasse
  enabled: false
  source: "input/bahntrasse.shp"
  style: bahntrasse
```

### 5. Hatching as a layer property
Instead of creating separate "Schraffur" layers that just reference a parent layer, hatching becomes a property on the source layer. The engine creates the hatch layer(s) automatically.

Before (2 layers, ~12 lines):
```yaml
- name: Wald
  sync: push
  operations:
    - type: difference
      layers:
        - Acker

- name: Wald Schraffur
  sync: push
  style: wald
  applyHatch:
    layers:
      - Wald
```

After (1 layer, hatching is a property):
```yaml
- name: Wald
  sync: push
  hatch:
    - style: wald
  operations:
    - type: difference
      layers:
        - Acker
```

### 6. Templates

Templates define reusable layer patterns with parameters. They solve two problems:
- **Within a project**: repeated patterns like 3 Geltungsbereich regions with different parcels
- **Across projects**: common patterns like admin boundaries, Baugrenze chain, reports

#### Template definition
Templates can live in the tool repo (shared across all projects) or in a project's own config (project-specific).

```yaml
templates:
  - name: geltungsbereich_region
    params:
      - region
      - parcels
      - flur
      - gemarkung
      - gemeinde
      - landUseLayer
      - landUseMode
      - wegeLayer
    layers:
      - name: "Geltungsbereich ${region} Base"
        style: geltungsbereich
        operations:
          - type: copy
            layers:
              - name: Parcel
                values: ${parcels}
          - type: filterByIntersection
            layers:
              - name: Flur Input
                values:
                  - "${flur}"
              - name: Gemarkung Input
                values:
                  - "${gemarkung}"
              - name: Gemeinde Input
                values:
                  - "${gemeinde}"
          - type: dissolve

      - name: "Geltungsbereich ${region}"
        sync: push
        style: geltungsbereich
        operations:
          - type: dissolve
            layers:
              - AgriPV Base
              - "${landUseLayer}"
          - type: intersection
            layers:
              - "Geltungsbereich ${region} Base"
          - type: dissolve
            layers:
              - Include Geltungsbereich
          - type: intersection
            layers:
              - "Geltungsbereich ${region} Base"
          - type: removeInteriorRings
```

#### Template usage
```yaml
apply:
  - template: geltungsbereich_region
    params:
      region: NW
      parcels:
        - "1"
        - "2"
        - "4"
        - "6"
        - "7"
        - "14"
      flur: "Flur 1"
      gemarkung: "Groß Plasten"
      gemeinde: "Groß Plasten"
      landUseLayer: Acker
      landUseMode: union
      wegeLayer: Wege Filtered NW

  - template: geltungsbereich_region
    params:
      region: S
      parcels:
        - "41/1"
      flur: "Flur 2"
      gemarkung: "Klein Plasten"
      gemeinde: "Groß Plasten"
      landUseLayer: Acker_S
      landUseMode: intersection
```

#### Cross-project template library (shipped with the tool)
Analysis of all projects shows these patterns repeat in nearly every project:

| Template | What it does | Found in |
|----------|-------------|----------|
| admin_boundaries | Parcel/Flur/Gemarkung/Gemeinde + labels + boundary extraction | All projects |
| geltungsbereich | Parcels -> filter -> dissolve -> exclude | All projects |
| baugrenze_chain | Baufeld -> Baugrenze(-3m) -> Baugrenze 2(-0.4m) + reports | All projects |
| zone_report | Standard area/perimeter report for a zone | All projects |
| protection_ring | Buffer ring + T-Linie hatching (Schutzflaecheumgrenzung) | Bibow, Friedrichshof, Torgelow |
| gruenflaeche | Green space calculation from natural features + hatching | Bibow, Friedrichshof, Torgelow |

Templates expand to concrete layers via text substitution before processing. The result is the same flat list of layers.

---

## Estimated impact on Plasten (most complex project)

| Change | Lines saved |
|--------|------------|
| Auto-repair (removes 4-stage cleanup x5) | ~80 |
| Buffer defaults (removes repeated params) | ~90 |
| Hatch as property (eliminates ~10 Schraffur layers) | ~80 |
| Templates for 3 Geltungsbereich regions | ~140 |
| Templates for 12 report layers | ~250 |
| **Total reduction** | **~640 lines (1793 -> ~1150)** |

With multi-file splitting, the remaining ~1150 lines would be across 5-6 files of ~200 lines each.

---

## Decided against
- **Template conditionals**: Not needed. Templates handle the 80% common pattern; the remaining 20% stays as regular layers. If a template needs conditionals, it should be split into simpler templates instead.
- **Moving other YAML files**: dxf_operations.yaml, dxf_transfer.yaml, generated/, interactive/ stay where they are. Their current locations already make sense.
- **Inline buffer references** (`Wald Input | buffer(10)`): Not worth it. Introduces a mini-expression parser for marginal line savings. Buffer-only layers are already shorter with bufferDefaults.

## Future vision
Web frontend where users chat with AI to manage GIS projects. The AI calls Python-ACAD-Tools programmatically. This requires a clean API layer on top of the engine.
