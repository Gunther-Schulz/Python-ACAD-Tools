#// ... existing code ...
### Gap 4: Label Placement Integration

*   **Status:** <font color="red">OPEN</font> -> <font color="green">RESOLVED</font>
*   **Summary:** The current `LabelOperation` is too simplistic. We need a robust `LabelPlacementOperation` that integrates with `LabelSettings` (for defining what to label and how) and `IStyleService` (for label text style). This operation should delegate complex placement logic to a new `ILabelPlacementService`.
*   **Details & Requirements:**
    *   `a. Configuration:`
        *   Define `LabelPlacementOperationConfig(BaseOperationConfig)`:
            *   `source_layer: Optional[str]` (if None, operates on features from previous op)
            *   `output_label_layer_name: str`
            *   `label_settings: LabelSettings` (see below)
        *   Define `LabelSettings(BaseModel)`:
            *   `label_attribute: Optional[str]` (attribute field for label text)
            *   `fixed_label_text: Optional[str]` (alternative to `label_attribute`)
            *   `text_height: float` (default, e.g., 2.5) -> Moved to `TextStylePropertiesConfig`
            *   `offset_x: float` (default 0)
            *   `offset_y: float` (default 0, or auto based on text height)
            *   `point_position_preference: Optional[str]` (e.g., "top-right", "middle-center")
            *   `line_placement_strategy: Optional[str]` (e.g., "center_segment", "curved", "horizontal_near_segment")
            *   `polygon_placement_strategy: Optional[str]` (e.g., "centroid", "pole_of_inaccessibility", "horizontal_in_polygon")
            *   `text_style_preset_name: Optional[str]` (references `AppConfig.style_presets`) - Implemented
            *   `text_style_inline: Optional[TextStylePropertiesConfig]` (direct style definition) - Implemented
            *   `label_alignment_point: Optional[int]` (DXF MTEXT attachment point: 1-9) - Implemented
            *   `min_feature_size_pixels: Optional[float]` (for label culling, if view context known) -> Deferred
            *   `label_must_touch_boundary: Optional[bool]` (for polygon labels, if they must touch/cross boundary) - Implemented in LabelPlacementService
            *   `min_label_area_inside_percent: Optional[float]` (0-100, for polygon labels) - Implemented in LabelPlacementService
    *   `b. Style Integration:`
        *   Ensure `LabelSettings` can specify text style via preset name or inline definition (as above). - Done
        *   Consider adding `labeling: Optional[LabelSettings]` to `LayerConfig` as a direct way to configure labels for all features on a layer, complementing the `LabelPlacementOperation`. - Done
    *   `c. Style Service Interface (`IStyleService`):`
        *   Add method: `get_resolved_style_for_label_operation(config: LabelPlacementOperationConfig) -> TextStylePropertiesConfig`
            *   This method resolves `config.label_settings.text_style_preset_name` or `config.label_settings.text_style_inline` against `AppConfig.style_presets`.
            *   Returns a fully resolved `TextStylePropertiesConfig`. - Done
    *   `d. Style Service Implementation (`StyleServiceImpl`):`
        *   Implement the `get_resolved_style_for_label_operation` method. - Done
    *   `e. LabelPlacementOperation Update:`
        *   `LabelPlacementOperation.execute` should use `IStyleService.get_resolved_style_for_label_operation` to get `TextStylePropertiesConfig`.
        *   It should then pass this `TextStylePropertiesConfig` to `ILabelPlacementService.place_labels_for_features`.
        *   The resulting `GeoFeature` for the label should store the resolved `TextStylePropertiesConfig` in its attributes (e.g., `feature.attributes["text_style_properties"] = text_style_props.model_dump()`). - Done
    *   `f. LabelPlacementService (`ILabelPlacementService` / `LabelPlacementServiceImpl`):`
        *   Interface `ILabelPlacementService.place_labels_for_features` should accept the resolved `TextStylePropertiesConfig` as a parameter. - Done
        *   Implementation `LabelPlacementServiceImpl` should use this `TextStylePropertiesConfig` for its internal logic (e.g., when calculating text dimensions for collision boxes or estimating placement candidates). It should NOT try to re-resolve styles or use `LabelSettings.text_height` directly if full style properties are available. - Done
*   **Resolution Summary (NEW):**
    *   `LabelPlacementOperationConfig` and `LabelSettings` models were defined in `schemas.py`, including text style preset/inline options.
    *   `LayerConfig` was updated with an optional `labeling: LabelSettings` field.
    *   `IStyleService` interface and `StyleServiceImpl` implementation were updated with `get_resolved_style_for_label_operation`.
    *   `LabelPlacementOperation` was updated to use this style service method and pass the resolved `TextStylePropertiesConfig` to the label placement service. The output label `GeoFeature` now stores these style properties.
    *   `ILabelPlacementService` interface's `place_labels_for_features` method was updated to accept `TextStylePropertiesConfig`.
    *   `LabelPlacementServiceImpl` was updated to:
        *   Match the new interface signature.
        *   Refactor its internal `_get_text_dimensions` helper to primarily use the passed `TextStylePropertiesConfig` (height, width_factor) for calculating text dimensions, instead of looking up styles or using hardcoded values.
        *   Update calls to internal helpers (like `_evaluate_candidate_position`, `get_point_label_position`) to propagate and use the `TextStylePropertiesConfig` or its derived values (like text height).
    *   This ensures that label styles are resolved once by the `StyleService` and then used consistently throughout the label placement process.

### Gap 5: Operation Error Handling & Reporting
#// ... existing code ...
