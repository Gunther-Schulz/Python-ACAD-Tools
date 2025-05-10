# Planning: Optional Layer Names for Operations in `dxfplanner`

## 1. Introduction

This document outlines a proposal to simplify the configuration of layer processing operations within `dxfplanner`. The goal is to reduce boilerplate and improve user experience for common linear operation chains by making `source_layer` and `output_layer_name` optional for individual operations.

## 2. Problem Statement

Currently, each operation defined within a `LayerConfig` requires explicit declaration of:
- `source_layer`: The name of the layer providing input to the operation.
- `output_layer_name`: The name assigned to the layer produced by the operation.

While this explicitness offers clarity and flexibility for complex scenarios (e.g., branching, merging multiple sources), it leads to significant boilerplate in common cases where operations are chained linearly. In such chains, the output of one operation becomes the input of the next, and intermediate layer names are often just temporary placeholders.

**Example (Current Boilerplate):**

```yaml
layers:
  - name: "processed_buildings"  # Final output name
    source:
      type: shapefile
      path: "data/buildings.shp"
    operations:
      - type: buffer
        source_layer: "processed_buildings" # Initial source is the layer itself
        distance: 5.0
        output_layer_name: "buffered_buildings"
      - type: simplify
        source_layer: "buffered_buildings"   # Must match previous output
        tolerance: 0.5
        output_layer_name: "simplified_buffered_buildings" # Final operation's output before being named "processed_buildings"
    style_preset_name: "building_style"
    enabled: true
```

This requires users to invent and track names for intermediate steps, even if those names are not directly used or referenced elsewhere.

## 3. Proposed Solution

We propose to make `source_layer` and `output_layer_name` optional within the `OperationConfig` schema.

**3.1. Implicit `source_layer`:**
- If an operation omits `source_layer`:
    - For the first operation in the list, its input will implicitly be the main layer defined by `LayerConfig.name` (acting as the initial state of the data from `LayerConfig.source`).
    - For subsequent operations, its input will implicitly be the output of the immediately preceding operation in the list.

**3.2. Implicit `output_layer_name` for Intermediate Operations:**
- If an operation (that is not the last in the chain) omits `output_layer_name`, the system will internally manage its output. This output will then serve as the implicit input for the next operation.
    - For logging and debugging, these implicitly named intermediate layers could follow a convention (e.g., `_op_0_result_for_layer_X_`, `_op_1_result_for_layer_X_`).
- The `LayerConfig.name` will *always* refer to the name of the layer after *all* operations in its list have been processed. The output of the *final* operation in the chain is effectively renamed to `LayerConfig.name`.

**3.3. Explicit Naming Still Supported:**
- Users can still provide explicit `source_layer` and `output_layer_name` if they need to:
    - Reference a specific intermediate layer later (e.g., for a branching workflow, though this is a more advanced use case not directly simplified by this proposal).
    - Provide more descriptive names for clarity during debugging or for specific intermediate outputs they wish to inspect (though inspecting intermediate outputs is not a current feature).

**Example (Proposed Simplified Config):**

```yaml
layers:
  - name: "processed_buildings"  # Final output name
    source:
      type: shapefile
      path: "data/buildings.shp"
    operations:
      - type: buffer  # source_layer implicitly "processed_buildings" (initial state)
        distance: 5.0  # output_layer_name is implicit
      - type: simplify # source_layer implicitly output of buffer
        tolerance: 0.5 # output_layer_name is implicit; result becomes "processed_buildings"
    style_preset_name: "building_style"
    enabled: true
```

## 4. Benefits

- **Reduced Boilerplate:** Significantly less configuration for common linear workflows.
- **Improved User Experience:** More intuitive and less error-prone, as users don't need to invent and manage temporary intermediate names.
- **Focus on Transformation Flow:** Configuration becomes more focused on the sequence of transformations rather than naming logistics.

## 5. Implementation Considerations

**5.1. Schema Changes (`src/dxfplanner/config/schemas.py`):**
- `OperationConfig`:
    - `source_layer`: Change from `str` to `Optional[str]`.
    - `output_layer_name`: Change from `str` to `Optional[str]`.

**5.2. Logic Changes (`src/dxfplanner/services/layer_processor_service.py`):**
- The `LayerProcessorService` will need to be updated to:
    - Resolve the `source_layer` for an operation:
        - If explicitly provided, use it.
        - If not provided and it's the first operation, use the main `LayerConfig.name` (or an internal representation of the initial data).
        - If not provided and it's a subsequent operation, use the managed output name of the previous operation.
    - Manage the `output_layer_name`:
        - If explicitly provided, use it.
        - If not provided for an intermediate step, generate and track an internal name.
        - The final result of the operation chain for a `LayerConfig` will always be associated with `LayerConfig.name`.

**5.3. Logging:**
- Logging messages should be adapted. When an `output_layer_name` is not explicitly provided by the user for an intermediate operation, logs should refer to the internally generated name or clearly indicate it's an intermediate, unnamed step in the processing of `LayerConfig.name`.
- Example log: `"Processing layer 'buildings': Applying 'buffer' (step 1/2, output: _intermediate_buffer_for_buildings_)..."`
- Example log: `"Processing layer 'buildings': Applying 'simplify' (step 2/2) from _intermediate_buffer_for_buildings_ to final output 'buildings'..."`

**5.4. Backwards Compatibility:**
- Existing configurations with explicit `source_layer` and `output_layer_name` should continue to work without change. The new behavior applies when these fields are omitted.

## 6. Potential Challenges and Future Considerations

- **Debugging Clarity:** While aiming to simplify, implicitly named layers might make debugging slightly less direct if a problem occurs in an intermediate step. Clear logging (as mentioned above) will be crucial.
- **Non-Linear/Complex Workflows:** This proposal primarily benefits linear chains. If `dxfplanner` evolves to support more complex operation graphs (e.g., operations taking multiple input layers, conditional branching based on intermediate results), the fully explicit naming might still be necessary or preferred for those advanced scenarios. The proposed simplification does not preclude this but focuses on the common case.
- **User Understanding:** Documentation will need to clearly explain both the simplified implicit naming and the option for explicit naming.

## 7. Next Steps
- [ ] Discuss this proposal with the development team.
- [ ] If agreed, create issues for schema changes and `LayerProcessorService` modifications.
- [ ] Implement the changes.
- [ ] Update documentation.
- [ ] Test with existing and new configuration examples.
