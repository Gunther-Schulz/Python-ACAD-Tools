import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import format_operation_warning, _process_layer_info, _get_filtered_geometry, explode_to_singlepart

def create_copy_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating copy layer: {layer_name}")
    log_debug(f"Copy operation details for {layer_name}: {operation}")

    copy_layers = operation.get('layers', [])

    if not copy_layers:
        log_warning(f"No copy layers specified for {layer_name}")
        return None

    combined_geometry = None

    for layer_info in copy_layers:
        source_layer_name, values, column_name = _process_layer_info(all_layers, project_settings, crs, layer_info)

        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(f"Source layer '{source_layer_name}' not found for copy operation")
            continue

        source_gdf = all_layers[source_layer_name]
        log_debug(f"Source layer '{source_layer_name}' columns: {source_gdf.columns.tolist()}")
        log_debug(f"Source layer '{source_layer_name}' has {len(source_gdf)} features")

        # Check if filtering is needed
        if values and len(values) > 0:
            # Value filtering is requested
            log_debug(f"Value filtering requested for layer '{source_layer_name}' with values: {values}")

            # First try to use the explicit column name from the operation if provided
            if column_name and column_name in source_gdf.columns:
                label_column = column_name
                log_debug(f"Using explicit column '{label_column}' for filtering layer '{source_layer_name}'")
            else:
                # Fall back to the label from project settings
                label_column = next((l.get('label') for l in project_settings['geomLayers'] if l['name'] == source_layer_name), None)
                log_debug(f"Using project settings column '{label_column}' for filtering layer '{source_layer_name}'")

            if label_column and label_column in source_gdf.columns:
                log_debug(f"Using column '{label_column}' for filtering layer '{source_layer_name}'")

                # DETAILED DEBUGGING: Print all unique values with types
                unique_vals = source_gdf[label_column].unique()
                unique_str_vals = [str(val) for val in unique_vals]
                log_debug(f"Unique values in '{label_column}': {unique_str_vals}")
                log_debug(f"Types of unique values: {[type(val) for val in unique_vals[:10]]}")

                # Convert target values to strings for comparison
                str_values = [str(v) for v in values]
                log_debug(f"Values converted to strings: {str_values}")
                log_debug(f"Types of search values: {[type(v) for v in values]}")

                # EXTREME DEBUGGING: Check each value individually
                for target_val in str_values:
                    matches = []
                    for idx, val in enumerate(source_gdf[label_column]):
                        str_val = str(val).strip()
                        if str_val == target_val:
                            matches.append((idx, val, type(val)))
                            log_debug(f"Found exact match for '{target_val}' at index {idx}: value='{val}', type={type(val)}")
                        elif str_val.startswith(target_val) or target_val.startswith(str_val):
                            log_debug(f"Found partial match for '{target_val}' at index {idx}: value='{val}', type={type(val)}")
                    log_debug(f"Value '{target_val}' found in {len(matches)} features: {matches[:5]}")

                # Try different matching approaches
                filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(str_values)]
                log_debug(f"Standard string matching found {len(filtered_gdf)} features for values {str_values}")

                # Try strip() approach
                filtered_gdf2 = source_gdf[source_gdf[label_column].astype(str).str.strip().isin(str_values)]
                log_debug(f"Stripped string matching found {len(filtered_gdf2)} features for values {str_values}")

                # Try contains approach
                filtered_gdf3 = source_gdf[source_gdf[label_column].astype(str).str.contains('|'.join(str_values), regex=True)]
                log_debug(f"Contains matching found {len(filtered_gdf3)} features for values {str_values}")

                # Use standard method for the actual filtering
                filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(str_values)]
                log_debug(f"Filtered {source_layer_name} using column '{label_column}': {len(filtered_gdf)} features remaining")

                if filtered_gdf.empty:
                    log_warning(f"After filtering, source layer '{source_layer_name}' is empty")
                    continue
            else:
                log_warning(f"Label column '{label_column}' not found in layer '{source_layer_name}' - skipping filtering")
                filtered_gdf = source_gdf.copy()
        else:
            # No filtering requested - copy all features
            log_debug(f"No value filtering requested for layer '{source_layer_name}' - copying all {len(source_gdf)} features")
            filtered_gdf = source_gdf.copy()

        # Add the (filtered or unfiltered) geometry to the combined geometry
        if combined_geometry is None:
            combined_geometry = filtered_gdf
        else:
            combined_geometry = pd.concat([combined_geometry, filtered_gdf], ignore_index=True)

    if combined_geometry is None or len(combined_geometry) == 0:
        log_warning(format_operation_warning(
            layer_name,
            "copy",
            "No valid source layers found"
        ))
        return None

    # Dissolve polygons if needed
    # process_dissolve = next((op for op in operation.get('operations', []) if op.get('type') == 'dissolve'), None)
    # if process_dissolve:
    #     combined_geometry = dissolve_geometry(combined_geometry)

    return combined_geometry
