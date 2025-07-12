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

        # ARCHITECTURAL FIX: Only filter if explicit column is provided
        if values and column_name:
            # Explicit column filtering - column must exist
            if column_name in source_gdf.columns:
                log_debug(f"Using explicit column '{column_name}' for filtering layer '{source_layer_name}'")

                # DETAILED DEBUGGING: Print all unique values with types
                unique_vals = source_gdf[column_name].unique()
                unique_str_vals = [str(val) for val in unique_vals]
                log_debug(f"Unique values in '{column_name}': {unique_str_vals}")
                log_debug(f"Types of unique values: {[type(val) for val in unique_vals[:10]]}")

                # Convert target values to strings for comparison
                str_values = [str(v) for v in values]
                log_debug(f"Values converted to strings: {str_values}")
                log_debug(f"Types of search values: {[type(v) for v in values]}")

                # EXTREME DEBUGGING: Check each value individually
                for target_val in str_values:
                    matches = []
                    for idx, val in enumerate(source_gdf[column_name]):
                        str_val = str(val).strip()
                        if str_val == target_val:
                            matches.append((idx, val, type(val)))
                            log_debug(f"Found exact match for '{target_val}' at index {idx}: value='{val}', type={type(val)}")
                        elif str_val.startswith(target_val) or target_val.startswith(str_val):
                            log_debug(f"Found partial match for '{target_val}' at index {idx}: value='{val}', type={type(val)}")
                    log_debug(f"Value '{target_val}' found in {len(matches)} features: {matches[:5]}")

                # Try different matching approaches
                filtered_gdf = source_gdf[source_gdf[column_name].astype(str).isin(str_values)]
                log_debug(f"Standard string matching found {len(filtered_gdf)} features for values {str_values}")

                # Try strip() approach
                filtered_gdf2 = source_gdf[source_gdf[column_name].astype(str).str.strip().isin(str_values)]
                log_debug(f"Stripped string matching found {len(filtered_gdf2)} features for values {str_values}")

                # Try contains approach
                filtered_gdf3 = source_gdf[source_gdf[column_name].astype(str).str.contains('|'.join(str_values), regex=True)]
                log_debug(f"Contains matching found {len(filtered_gdf3)} features for values {str_values}")

                # Use standard method for the actual filtering
                filtered_gdf = source_gdf[source_gdf[column_name].astype(str).isin(str_values)]
                log_debug(f"Filtered {source_layer_name} using column '{column_name}': {len(filtered_gdf)} features remaining")

                if filtered_gdf.empty:
                    log_warning(f"After filtering, source layer '{source_layer_name}' is empty")
                    continue
            else:
                log_error(f"Explicit column '{column_name}' not found in layer '{source_layer_name}'. Available columns: {list(source_gdf.columns)}")
                continue
        elif values and not column_name:
            # Values provided but no column specified - ignore values, take everything
            log_debug(f"Values provided for {source_layer_name} but no column specified - ignoring values and taking all data")
            filtered_gdf = source_gdf.copy()
        else:
            # No values or no column - take everything
            log_debug(f"No filtering specified for {source_layer_name} - taking all data")
            filtered_gdf = source_gdf.copy()

        # Add the filtered geometry to the combined geometry
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
