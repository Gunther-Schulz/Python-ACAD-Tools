import geopandas as gpd
from src.utils import log_info, log_warning, log_error

def create_calculate_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating calculate layer: {layer_name}")
    
    if layer_name not in all_layers:
        log_warning(f"Layer '{layer_name}' not found for calculation")
        return None

    source_gdf = all_layers[layer_name].copy()
    calculations = operation.get('calculations', [])
    
    for calc in calculations:
        calc_type = calc.get('type')
        if not calc_type:
            log_warning(f"Missing calculation type in operation for layer '{layer_name}'")
            continue
            
        # Handle basic calculations
        if calc_type == 'area':
            column_name = calc.get('as', 'area')
            source_gdf[column_name] = source_gdf.geometry.area
            decimal_places = calc.get('decimalPlaces')
            if decimal_places is not None:
                source_gdf[column_name] = source_gdf[column_name].round(decimal_places)
                
        elif calc_type == 'perimeter':
            column_name = calc.get('as', 'perimeter')
            source_gdf[column_name] = source_gdf.geometry.length
            decimal_places = calc.get('decimalPlaces')
            if decimal_places is not None:
                source_gdf[column_name] = source_gdf[column_name].round(decimal_places)
                
        # Handle comparisons
        elif calc_type == 'compare':
            value1 = calc.get('value1')
            value2 = calc.get('value2')
            operator = calc.get('operator', 'eq')
            margin = calc.get('margin', 0)
            column_name = calc.get('as', f"{value1}_{operator}_{value2}")
            
            if value1 not in source_gdf.columns or value2 not in source_gdf.columns:
                log_warning(f"Layer '{layer_name}': One or both columns not found for comparison: {value1}, {value2}")
                continue
                
            if operator == 'eq':
                source_gdf[column_name] = (source_gdf[value1] - source_gdf[value2]).abs() <= margin
            elif operator == 'lt':
                source_gdf[column_name] = source_gdf[value1] < (source_gdf[value2] - margin)
            elif operator == 'gt':
                source_gdf[column_name] = source_gdf[value1] > (source_gdf[value2] + margin)
            elif operator == 'lte':
                source_gdf[column_name] = source_gdf[value1] <= (source_gdf[value2] + margin)
            elif operator == 'gte':
                source_gdf[column_name] = source_gdf[value1] >= (source_gdf[value2] - margin)
        else:
            log_warning(f"Unknown calculation type: {calc_type}")
            continue
    
    all_layers[layer_name] = source_gdf
    return source_gdf