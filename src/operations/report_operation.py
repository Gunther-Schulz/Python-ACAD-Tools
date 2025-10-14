import geopandas as gpd
import pandas as pd
import json
import yaml
import os
import re
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists, log_debug
from src.operations.common_operations import _process_layer_info, ensure_geodataframe
from src.operations.calculate_operation import create_calculate_layer

def create_report_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating report for layer: {layer_name}")
    
    if layer_name not in all_layers:
        log_warning(f"Layer '{layer_name}' not found for reporting")
        return

    source_gdf = all_layers[layer_name].copy()
    
    # Get output file path from operation
    output_file = operation.get('outputFile', f"{layer_name}_report.json")
    folder_prefix = project_settings.get('folderPrefix', '')
    output_file = resolve_path(output_file, folder_prefix)
    
    # Get configuration
    calculate_columns = operation.get('calculate', [])
    feature_columns = operation.get('featureColumns', [])
    decimal_places = operation.get('decimalPlaces', {})
    
    # Use calculate operation to compute metrics FIRST (before sorting)
    # Only calculate fields that don't already exist and are valid calculation types
    if calculate_columns:
        valid_calc_types = ['area', 'perimeter', 'compare', 'percentage', 'coverage_status']
        calculations = []
        for calc in calculate_columns:
            # If the column already exists, skip recalculation
            if calc in source_gdf.columns:
                log_debug(f"Column '{calc}' already exists in layer '{layer_name}', skipping calculation")
                continue
            # Only create calculation if it's a valid type
            if calc in valid_calc_types:
                calculations.append({
                    'type': calc,
                    'decimalPlaces': decimal_places.get(calc)
                })
            else:
                log_debug(f"'{calc}' is not a valid calculation type, assuming it's a field reference")
        
        # Only call calculate if we have valid calculations to perform
        if calculations:
            calculate_operation = {
                'calculations': calculations
            }
            source_gdf = create_calculate_layer(all_layers, project_settings, crs, layer_name, calculate_operation)
    
    # Handle sorting AFTER calculations
    sort_by = operation.get('sortBy')
    if sort_by:
        try:
            # Support natural sorting for mixed numeric/alphanumeric values like "110/1", "45"
            def natural_sort_key(val):
                """Convert string to list of integers and strings for natural sorting"""
                if pd.isna(val):
                    return (0, [])  # Put NaN values first
                val_str = str(val)
                # Split on digits, keeping the digits as separate elements
                parts = re.split(r'(\d+)', val_str)
                result = []
                for p in parts:
                    if p:  # Skip empty strings
                        if p.isdigit():
                            result.append((0, int(p)))  # (0, number) for numeric parts
                        else:
                            result.append((1, p.lower()))  # (1, text) for text parts
                return (1, result)  # (1, ...) for non-NaN values
            
            # Debug: show values before sorting
            if sort_by in source_gdf.columns:
                log_debug(f"Before sorting by '{sort_by}': {source_gdf[sort_by].tolist()}")
            
            source_gdf = source_gdf.sort_values(
                by=sort_by, 
                key=lambda col: col.map(natural_sort_key),
                ascending=True,
                ignore_index=True  # Reset index automatically
            )
            
            # Debug: show values after sorting
            if sort_by in source_gdf.columns:
                log_debug(f"After sorting by '{sort_by}': {source_gdf[sort_by].tolist()}")
        except Exception as e:
            log_warning(f"Could not sort by '{sort_by}': {str(e)}")
    
    # Create report data and summary data
    features_data = []
    summary = {}
    
    # Initialize summary accumulators for each calculated column
    # Check if columns exist in the dataframe and are numeric
    for calc in calculate_columns:
        if calc in source_gdf.columns and pd.api.types.is_numeric_dtype(source_gdf[calc]):
            summary[calc] = {
                'total': 0, 'min': float('inf'), 'max': float('-inf'), 'count': 0
            }
    
    # Process each feature
    for idx, row in source_gdf.iterrows():
        feature_data = {}
        
        # Add specified columns or all columns except geometry
        if feature_columns:
            for column in feature_columns:
                if column in row.index and column != 'geometry':
                    feature_data[column] = row[column]
        else:
            for column in row.index:
                if column != 'geometry':
                    feature_data[column] = row[column]
        
        # Update summaries for numeric calculations
        for calc in calculate_columns:
            if calc in summary and calc in row.index:
                value = row[calc]
                summary[calc]['total'] += value
                summary[calc]['min'] = min(summary[calc]['min'], value)
                summary[calc]['max'] = max(summary[calc]['max'], value)
                summary[calc]['count'] += 1
        
        features_data.append(feature_data)
    
    # Calculate averages and clean up summaries
    for metric in summary:
        if summary[metric]['count'] > 0:
            summary[metric]['average'] = round(summary[metric]['total'] / summary[metric]['count'], 2)
            if summary[metric]['min'] == float('inf'):
                summary[metric]['min'] = 0
            if summary[metric]['max'] == float('-inf'):
                summary[metric]['max'] = 0
            for key in ['min', 'max', 'total']:
                summary[metric][key] = round(summary[metric][key], 2)
        else:
            summary[metric] = {
                'total': 0, 'min': 0, 'max': 0, 'average': 0, 'count': 0
            }
    
    # Create report object
    report = {
        'layer_name': layer_name,
        'crs': str(crs),
        'feature_count': len(features_data),
        'summary': summary,
        'features': features_data
    }
    
    # Add metadata if provided (e.g., tolerance settings)
    metadata = operation.get('metadata', {})
    if metadata:
        report['metadata'] = metadata
    
    # Write report to file
    if ensure_path_exists(output_file):
        try:
            # Change file extension to .yaml if it ends with .json
            if output_file.lower().endswith('.json'):
                output_file = output_file[:-5] + '.yaml'
            
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(report, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
            log_debug(f"Report written to {output_file}")
        except Exception as e:
            log_error(f"Error writing report to {output_file}: {str(e)}")
    else:
        log_warning(f"Directory for {output_file} does not exist. Skipping report generation.")
    
    return all_layers[layer_name]