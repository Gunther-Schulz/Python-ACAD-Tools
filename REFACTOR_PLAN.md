# Python-ACAD-Tools Refactor Plan

## What this tool does
Config-driven GIS→DXF pipeline. User writes YAML configs defining geometry layers + operations, runs CLI, gets reproducible DXF + shapefile output. Supports bidirectional sync with AutoCAD (push/pull), hatching, viewports, block inserts, text, legends, WMTS/WMS tiles.

## Codebase
- Location: ~/dev/Gunther-Schulz/Python-ACAD-Tools
- 14K+ lines in src/, 36 operation modules in src/operations/
- Entry point: main.py → ProjectProcessor
- Key files: layer_processor.py (orchestrator), dxf_exporter.py (GeoDataFrame→DXF), dxf_utils.py (entity creation), unified_sync_processor.py (bidirectional sync), project_loader.py (YAML config)
- Currently uses conda env `acad` — should move to editable pip install (see below)
- Real projects in projects/ (Plasten, Friedrichshof, Bibow, Waren, Torgelow, etc.)

## Shared library
gis_utils (find via `pip show gis-utils`, v0.3.0) is the shared utility library. Python-ACAD-Tools should import from it where there's overlap (geometry ops, DXF helpers, markdown tables). gis_utils includes: DXF extraction, geometry utilities (make_valid, subtract, morphological filter, distance_to_nearest), reporting, OSM downloader, workflow runner.

## What we want to do
1. **Discuss usability/workflow design FIRST** — how should configs look? What's the ideal user experience?
2. **Then refactor architecture** — it will follow naturally from usability decisions
3. **Create a new git branch before any code changes**

## Installation & project model (new — follow gis_utils pattern)

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
- `project.yaml` — starter config with CRS, DXF paths, sync settings
- `geom_layers.yaml` — empty/example layer definitions
- `interactive/` — viewport, block, text insert configs
- `generated/` — legend, path array, WMTS/WMS configs
- `CLAUDE.md` — AI-readable project context (user-editable, never overwritten on re-init)

### Generated CLAUDE.md per project
When a Claude session starts in a project folder, it reads CLAUDE.md and immediately knows:
- This is a Python-ACAD-Tools project, here's how to run it
- Here's what's project-specific config vs what belongs as a new operation/extension in the core tool
- Here's where the tool source is (`pip show python-acad-tools`) for when something needs to be added to the engine
- If editing the tool source: commit and push separately (it's a different git repo)

### Clear scope distinction
The CLAUDE.md must teach AI to distinguish:
- **Project config** (geom_layers.yaml, project.yaml) — layer definitions, operation parameters, paths, styles → edit in the project folder
- **Core tool extension** (new operation, new feature) — reusable functionality that other projects would benefit from → edit in the tool source, commit/push that repo separately
- **gis_utils extension** — generic GIS/geometry utility not specific to the ACAD pipeline → edit in gis_utils source, commit/push that repo separately

## Pain points from real project analysis

### Config repetition (biggest issue)
- Plasten has 114 layers, 1793-line geom_layers.yaml
- Same patterns repeat endlessly: copy → buffer → dissolve → difference → repair → report
- Every buffer/difference operation needs 2-3 repair operations after it (slivers, spikes, geometry fix)
- Label layers are near-identical copies of parent layers with simpleLabel added
- No template/inheritance system — changing a pattern means editing 50+ places

### Geometry repair boilerplate
- `repair`, `removeSliversErosion`, `removeDegenerateSpikes` appear after almost every boolean operation
- Buffer oscillation workaround (buffer +d then -d) used for polygon smoothing
- This should be automatic, not manual

### Config management
- Commented-out layers instead of `enabled: false` (Waren is 95% comments)
- Styles referenced externally with no inline definition option
- No way to see "what operations does this layer depend on" without reading the whole file

### Code architecture
- Large monolithic files (dxf_utils 1764 lines, sync 1564 lines, exporter 1319 lines)
- if-elif operation dispatch in layer_processor.py (should be registry pattern)
- Tight coupling between modules

## Most-used operations (from real projects)
copy (75+), buffer (78+), dissolve (77+), intersection (55+), difference (58+), report (44+), removeSliversErosion, removeDegenerateSpikes, repair, filterByIntersection, circle, dissolveByMajorityIntersection

## Usability ideas to discuss
- **Operation presets/macros**: `type: buffered_zone` expands to buffer → dissolve → repair
- **Implicit geometry repair**: auto-repair after every boolean op (opt-out, not opt-in)
- **Layer templates**: define a pattern once, instantiate with parameters
- **`enabled: false`** instead of commenting out
- **Dependency visualization**: see the layer DAG
- **Clean Python API**: for future web frontend / AI chat interface
- **Better error messages**: when configs are wrong

## Future vision
Web frontend where users chat with AI to manage GIS projects. The AI calls Python-ACAD-Tools programmatically. This requires a clean API layer on top of the engine.

## How to start the refactor session
1. Read this file for context
2. Look at projects/Plasten/geom_layers.yaml for the most complex real example
3. Look at src/layer_processor.py for the operation dispatch
4. Discuss usability before touching code
5. Create branch `refactor/v2` before any changes
