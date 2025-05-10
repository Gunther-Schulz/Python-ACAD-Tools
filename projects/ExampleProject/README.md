# ExampleProject

This is a template project directory for use with the new DXFPlanner app structure.

## Structure

- `project.yaml` — Main project configuration (AppConfig format)
- `data/` — Place your geodata files here (e.g., `example.shp`)
- `template.dxf` — (Optional) A template DXF file to use as a base for output
- `output.dxf` — (To be generated) The output DXF file

## Usage

1. **Edit `project.yaml`** to reference your actual data files and desired settings.
2. **Run the app** from the repository root:

   ```bash
   python -m src.dxfplanner.cli --config projects/ExampleProject/project.yaml generate --output projects/ExampleProject/output.dxf
   ```

3. The output DXF will be written to `output.dxf` in this directory.

---

You can copy this directory to start new projects, adjusting the config and data as needed.
