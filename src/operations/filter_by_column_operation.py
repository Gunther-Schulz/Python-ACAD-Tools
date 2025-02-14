# src/operations/filter_by_column_operation.py
import geopandas as gpd
from src.core.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import format_operation_warning, ensure_geodataframe

def create_filtered_by_column_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Filter a layer based on column values.
    
    Operation parameters:
    - column: str - The column name to filter on
    - value: any - The value to filter for
    - operator: str - The comparison operator ('eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'in', 'contains')
    - caseSensitive: bool - Whether string comparisons should be case sensitive (default: True)
    """
    log_debug(f"Creating column-filtered layer: {layer_name}")
    
    if layer_name not in all_layers:
        log_warning(format_operation_warning(
            layer_name,
            "filterByColumn",
            "Source layer not found"
        ))
        return None
    
    # Get the source GeoDataFrame
    source_gdf = all_layers[layer_name].copy()
    
    # Get filter parameters
    column = operation.get('column')
    value = operation.get('value')
    operator = operation.get('operator', 'eq')
    case_sensitive = operation.get('caseSensitive', True)
    
    if not column:
        log_warning(format_operation_warning(
            layer_name,
            "filterByColumn",
            "No column specified for filtering"
        ))
        return None
        
    if column not in source_gdf.columns:
        log_warning(format_operation_warning(
            layer_name,
            "filterByColumn",
            f"Column '{column}' not found in layer"
        ))
        return None
    
    try:
        # Apply the filter based on the operator
        if operator == 'eq':
            mask = source_gdf[column] == value
        elif operator == 'neq':
            mask = source_gdf[column] != value
        elif operator == 'gt':
            mask = source_gdf[column] > value
        elif operator == 'gte':
            mask = source_gdf[column] >= value
        elif operator == 'lt':
            mask = source_gdf[column] < value
        elif operator == 'lte':
            mask = source_gdf[column] <= value
        elif operator == 'in':
            if not isinstance(value, list):
                value = [value]
            mask = source_gdf[column].isin(value)
        elif operator == 'contains':
            if not case_sensitive and isinstance(value, str):
                mask = source_gdf[column].str.lower().str.contains(value.lower())
            else:
                mask = source_gdf[column].str.contains(value)
        else:
            log_warning(format_operation_warning(
                layer_name,
                "filterByColumn",
                f"Unknown operator: {operator}"
            ))
            return None
        
        # Apply the filter
        filtered_gdf = source_gdf[mask]
        
        if filtered_gdf.empty:
            log_warning(format_operation_warning(
                layer_name,
                "filterByColumn",
                "No features match the filter criteria"
            ))
            all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        else:
            all_layers[layer_name] = filtered_gdf
            log_debug(f"Filtered layer {layer_name}: {len(filtered_gdf)} features remaining")
        
        return all_layers[layer_name]
        
    except Exception as e:
        log_error(format_operation_warning(
            layer_name,
            "filterByColumn",
            f"Error during filtering: {str(e)}"
        ))
        return None