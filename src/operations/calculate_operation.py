import geopandas as gpd
from src.utils import log_info, log_warning, log_error, log_debug
import decimal
from decimal import Decimal, ROUND_HALF_UP

def create_calculate_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating calculate layer: {layer_name}")
    
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
                source_gdf[column_name] = source_gdf[column_name].apply(
                    lambda x: float(Decimal(str(x)).quantize(
                        Decimal('1e-{}'.format(decimal_places)), 
                        rounding=ROUND_HALF_UP
                    ))
                )
                
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
                
        # Handle percentage calculations
        elif calc_type == 'percentage':
            numerator = calc.get('numerator')
            denominator = calc.get('denominator')
            column_name = calc.get('as', f"{numerator}_percent")
            decimal_places = calc.get('decimalPlaces', 2)
            
            if numerator not in source_gdf.columns or denominator not in source_gdf.columns:
                log_warning(f"Layer '{layer_name}': One or both columns not found for percentage: {numerator}, {denominator}")
                continue
            
            # Calculate percentage, handle division by zero
            source_gdf[column_name] = source_gdf.apply(
                lambda row: round((row[numerator] / row[denominator] * 100), decimal_places) 
                if row[denominator] > 0 else 0.0,
                axis=1
            )
            
        # Handle coverage status (complete/partial) based on percentage or absolute tolerance
        elif calc_type == 'coverage_status':
            column_name = calc.get('as', 'coverage_status')
            complete_label = calc.get('completeLabel', 'vollständig')
            partial_label = calc.get('partialLabel', 'teilweise')
            
            # Support two modes: percentage threshold OR absolute area tolerance
            percentage_column = calc.get('percentageColumn')
            percentage_threshold = calc.get('threshold')
            
            area_tolerance = calc.get('areaTolerance')
            total_area_column = calc.get('totalAreaColumn')
            intersection_area_column = calc.get('intersectionAreaColumn')
            
            # Mode 1: Percentage-based (original)
            if percentage_column and percentage_threshold is not None:
                if percentage_column not in source_gdf.columns:
                    log_warning(f"Layer '{layer_name}': Percentage column not found: {percentage_column}")
                    continue
                
                source_gdf[column_name] = source_gdf[percentage_column].apply(
                    lambda pct: complete_label if pct >= percentage_threshold else partial_label
                )
            
            # Mode 2: Absolute area tolerance (new)
            # Default to 0 (strict) if areaTolerance is not explicitly set
            elif total_area_column and intersection_area_column:
                if area_tolerance is None:
                    area_tolerance = 0  # Strict by default - no tolerance unless explicitly set
                    
                if total_area_column not in source_gdf.columns or intersection_area_column not in source_gdf.columns:
                    log_warning(f"Layer '{layer_name}': Required columns not found: {total_area_column}, {intersection_area_column}")
                    continue
                
                def check_coverage(row):
                    total = row[total_area_column]
                    intersection = row[intersection_area_column]
                    difference = abs(total - intersection)
                    return complete_label if difference <= area_tolerance else partial_label
                
                source_gdf[column_name] = source_gdf.apply(check_coverage, axis=1)
            
            else:
                log_warning(f"Layer '{layer_name}': coverage_status requires either (percentageColumn + threshold) or (areaTolerance + totalAreaColumn + intersectionAreaColumn)")
                continue
        else:
            log_warning(f"Unknown calculation type: {calc_type}")
            continue
    
    all_layers[layer_name] = source_gdf
    return source_gdf