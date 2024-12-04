import geopandas as gpd
import json
import os
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
    
    # Use calculate operation to compute metrics
    if calculate_columns:
        calculations = []
        for calc in calculate_columns:
            calculations.append({
                'type': calc,
                'decimalPlaces': decimal_places.get(calc)
            })
        
        calculate_operation = {
            'calculations': calculations
        }
        source_gdf = create_calculate_layer(all_layers, project_settings, crs, layer_name, calculate_operation)
    
    # Create report data and summary data
    features_data = []
    summary = {}
    
    # Initialize summary accumulators for each calculated column
    for calc in calculate_columns:
        if calc in ['area', 'perimeter']:  # Only summarize numeric calculations
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
            if calc in ['area', 'perimeter'] and calc in row.index:
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
    
    # Write report to file
    if ensure_path_exists(output_file):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            log_debug(f"Report written to {output_file}")
        except Exception as e:
            log_error(f"Error writing report to {output_file}: {str(e)}")
    else:
        log_warning(f"Directory for {output_file} does not exist. Skipping report generation.")
    
    return all_layers[layer_name]