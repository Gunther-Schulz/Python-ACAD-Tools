# Planning: Iterative DXF Output and Intelligent Updates

## 1. Introduction

This document outlines a proposal to enhance `dxfplanner` to support an iterative workflow. This involves allowing the output DXF file to be specified in the project configuration and implementing an intelligent update mechanism where the script modifies this existing file, managing only the entities it creates via XDATA.

## 2. Problem Statement

Currently, `dxfplanner` generates a new DXF file on each run. This is not ideal for workflows where users:
- Make manual modifications to the DXF in CAD software.
- Want to re-run the script to update only the programmatically generated parts, preserving their manual changes.
- Need to iterate on the design by adjusting the configuration and observing changes in the same DXF file.

## 3. Proposed Solution: High-Level

The core idea is to transform the DXF generation from a "create new" to a "read-modify-write" process when an output file is specified and already exists.

**3.1. Configurable Output DXF Path:**
- Introduce a field (e.g., `output_filepath`) in the `AppConfig` (specifically under `io.writers.dxf`) to allow users to define a persistent output DXF file for their project.

**3.2. Intelligent Update Workflow:**
- **On script execution:**
    1.  **Check Output Path:** Determine the target output DXF file (from config, potentially overridden by CLI).
    2.  **Load or Create Document:**
        - If the target DXF file exists: Load it using `ezdxf.readfile()`.
        - If it does not exist: Create a new document using `ezdxf.new()` (or from a template if specified, as per existing logic).
    3.  **Clear Previously Managed Entities (if existing file was loaded):**
        - Iterate through entities in the loaded DXF document.
        - Identify entities managed by `dxfplanner` by checking for a specific XDATA application name (e.g., `self._writer_config.xdata_application_name`).
        - Delete these identified entities.
        - **Note:** The implementation of this step should draw heavily on best practices for entity management with `ezdxf`, potentially referencing patterns from the `OLDAPP` codebase (e.g., how entities were cleared or managed on layers in `del_dxf_transfer.py` or `dxf_utils.py`).
    4.  **Generate and Add New Entities:**
        - Proceed with the standard `dxfplanner` logic to process layers and operations, generating new DXF entities.
        - As entities are created, attach the identifying XDATA tag to them.
    5.  **Save Document:**
        - Save the (now modified) document back to the specified `output_filepath` using `doc.saveas()` or `doc.save()`.

## 4. Benefits

- **Supports Iterative Design:** Users can refine configurations and see updates in their working DXF without losing manual CAD work.
- **Preserves Manual Changes:** Manual additions/modifications made in CAD software to unmanaged entities are retained.
- **Streamlined Workflow:** Reduces the need for manual file management (copying, renaming) when iterating.
- **Script "Ownership":** The script only takes responsibility for the entities it creates, clearly demarcated by XDATA.

## 5. Key Implementation Areas & Considerations

- **Configuration Schema (`src/dxfplanner/config/schemas.py`):**
    - Add `output_filepath: Optional[str]` to `DxfWriterConfig`.
- **DXF Writer Service (`src/dxfplanner/io/writers/dxf_writer.py`):**
    - Major refactor of the `write_drawing` method to implement the read-load/create-clear-generate-save logic.
    - Develop a robust `_clear_managed_entities(doc, modelspace)` method. This method needs to:
        - Reliably find all entities with the script's XDATA tag (across modelspace, potentially block definitions if the script creates/modifies blocks).
        - Delete them efficiently and safely.
        - Consider how `OLDAPP` handled entity removal based on specific identifiers or layer properties, adapting this for XDATA.
- **XDATA Strategy:**
    - Confirm the existing `xdata_application_name` in `DxfWriterConfig` is suitable.
    - Ensure XDATA is consistently applied to all script-generated entities.
- **Command Line Interface (`src/dxfplanner/cli.py`):**
    - Adjust CLI argument handling for `--output` to interact correctly with the new config option (e.g., CLI overrides config).
- **Error Handling & Robustness:**
    - Handle cases where the existing DXF is corrupt or cannot be read.
    - Ensure entity deletion is comprehensive.
- **Performance:**
    - Be mindful of performance impacts when reading/writing/processing potentially large existing DXF files.

## 6. Reference to `OLDAPP` for Entity Management

The `OLDAPP` codebase, particularly modules like `OLDAPP/src/dxf_utils.py` (functions like `remove_entities_by_layer`, `attach_custom_data`, `is_created_by_script`) and `OLDAPP/del_dxf_transfer.py`, contains examples of managing DXF entities with `ezdxf`, including clearing entities from layers. While the new system will use XDATA for a more granular "ownership" model rather than just clearing entire layers, the `ezdxf` interaction patterns for querying, checking XDATA (or custom properties in the old app), and deleting entities will be valuable references.

## 7. Next Steps

- [ ] Discuss this proposal with the development team.
- [ ] Refine the XDATA content if more specific identifiers (beyond application name) are deemed necessary for future granularity.
- [ ] Create detailed issues for the schema changes and the `DXFWriterService` modifications.
- [ ] Implement the changes, starting with the config and then the writer service.
- [ ] Test thoroughly with various scenarios: new DXF, existing DXF with no managed entities, existing DXF with managed entities, existing DXF with manual additions.
- [ ] Update documentation.
