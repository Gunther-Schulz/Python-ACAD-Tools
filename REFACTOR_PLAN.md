# Python-ACAD-Tools Refactor Plan

## What this tool does
Config-driven GIS-to-DXF pipeline. User writes YAML configs defining geometry layers + operations, runs CLI, gets reproducible DXF + shapefile output. Supports bidirectional sync with AutoCAD (push/pull), hatching, viewports, block inserts, text, legends, WMTS/WMS tiles.

## Codebase
- Location: ~/dev/Gunther-Schulz/Python-ACAD-Tools
- 14K+ lines in src/, 36 operation modules in src/operations/
- Entry point: main.py -> ProjectProcessor
- Key files: layer_processor.py (orchestrator), dxf_exporter.py (GeoDataFrame->DXF), dxf_utils.py (entity creation), unified_sync_processor.py (bidirectional sync), project_loader.py (YAML config)
- Currently uses conda env `pycad` -- should move to editable pip install (see below)
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

## Implemented

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

#### Legend defaults
Shared text styles and spacing for legends. Define once in legends.yaml via `legendDefaults`, each legend inherits and can override.

```yaml
# legends.yaml
legendDefaults:
  max_width: 160
  title_spacing: 0
  subtitle_spacing: 4
  group_spacing: 3
  item_spacing: 4
  titleTextStyle:
    height: 8
    color: "white"
    text_style: "Arial"
  itemTextStyle:
    color: "white"
    height: 3
    text_style: "Arial"

legends:
  - name: "Legend NW"
    position:
      x: 368340
      y: 5942620
    # inherits all defaults, only specifies what differs
```

### 4. `enabled: false` instead of commenting out
All entity types support `enabled: false`: geomLayers, viewports, texts, blocks, legends, pathArrays. Disabled entities are skipped during processing without commenting out.

### 5. Hatching as a layer property
Instead of creating separate "Schraffur" layers that just reference a parent layer, hatching becomes a property on the source layer. The engine creates the hatch layer(s) automatically.

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

Templates can live in:
- Tool repo `templates/` directory (shared across all projects)
- Project `templates.yaml` file (project-specific)
- Inline in any layer YAML file

Cross-project template library (shipped with the tool):

| Template | What it does | Found in |
|----------|-------------|----------|
| admin_boundaries | Parcel/Flur/Gemarkung/Gemeinde + labels + boundary extraction | All projects |
| geltungsbereich | Parcels -> filter -> dissolve -> exclude | All projects |
| baugrenze_chain | Baufeld -> Baugrenze(-3m) -> Baugrenze 2(-0.4m) + reports | All projects |
| zone_report | Standard area/perimeter report for a zone | All projects |

### 7. Legend normalization
- Legend identifier changed from `id` to `name` for consistency (backward compatible with `id`)
- `legendDefaults` support for shared settings across legends

### 8. Style system improvements

#### Style inheritance (`extends`)
Styles can inherit from a parent style via `extends`. Child values override parent via deep merge.

```yaml
# styles.yaml
baugrenze:
  layer:
    linetype: ACAD_ISO11W100
    lineweight: 50
  entity:
    linetypeGeneration: true

testZone:
  extends: baugrenze
  layer:
    color: "green"    # adds color, keeps linetype + lineweight from parent
```

#### Per-project style overrides
Projects can have their own `styles.yaml` that merges into the global styles. Only styles defined in the project file override the global ones; everything else is kept.

### 9. Project settings improvements

#### `useFolderPrefix`
Projects can opt out of the global `folderPrefix` from `projects.yaml` by setting `useFolderPrefix: false` in their `project.yaml`. Useful for projects with absolute paths or projects living outside the standard folder structure.

#### `autoConflictResolution` (camelCase)
Renamed from `auto_conflict_resolution` to follow camelCase convention used by all other settings. No backward compatibility fallback.

### 10. Bug fixes
- `simpleLabel` operation now correctly resolves source layer from `layers` key when no explicit `sourceLayer` is specified. Fixes label column not found warnings on boundary layers.
- `zone_report` template opts out of auto-repair on intersection to prevent data column loss.

### 11. Deprecated systems removed
- `dxf_processor.py` removed -- `dxf_operations.extracts` fully superseded by `dxfSource` in geom_layers, `transfers` unused
- `dxf_operations.yaml`, `dxf_transfer.yaml`, `update_from_source.yaml` moved to `deprecated/` folder in each project for reference
- Backend code cleaned from project_loader.py and dxf_exporter.py

---

## Decided against
- **Template conditionals**: Not needed. Templates handle the 80% common pattern; the remaining 20% stays as regular layers.
- **Inline buffer references** (`Wald Input | buffer(10)`): Not worth it. Introduces a mini-expression parser for marginal line savings.
- **Templating viewports/texts/blocks**: The `_sync` metadata makes these bidirectional sync entities. Templating would conflict with the sync system.
- **Restructuring generated/interactive directories**: The split reflects sync direction (push-only vs bidirectional), which is meaningful.

## Future vision
Web frontend where users chat with AI to manage GIS projects. The AI calls Python-ACAD-Tools programmatically. This requires a clean API layer on top of the engine.
