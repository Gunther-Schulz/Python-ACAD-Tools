import geopandas as gpd
import json
import os
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists
from src.operations.common_operations import _process_layer_info, ensure_geodataframe

def create_report_layer(all_layers, project_settings, crs, layer_name, operation):
    log_info(f"Creating report for layer: {layer_name}")
    
    if layer_name not in all_layers:
        log_warning(f"Layer '{layer_name}' not found for reporting")
        return

    source_gdf = all_layers[layer_name]
    
    # Get output file path from operation
    output_file = operation.get('outputFile', f"{layer_name}_report.json")
    
    # Use resolve_path to get the full path
    folder_prefix = project_settings.get('folderPrefix', '')
    output_file = resolve_path(output_file, folder_prefix)
    
    # Get additional columns to calculate and decimal places configuration
    calculate_columns = operation.get('calculate', [])
    decimal_places = operation.get('decimalPlaces', {
        'area': 2,
        'perimeter': 2,
        'coordinates': 6  # For centroid and bounds
    })
    
    # Create report data and summary data
    features_data = []
    summary = {}
    
    # Initialize summary accumulators
    if 'area' in calculate_columns:
        summary['area'] = {
            'total': 0,
            'min': float('inf'),
            'max': float('-inf'),
            'count': 0
        }
    
    if 'perimeter' in calculate_columns:
        summary['perimeter'] = {
            'total': 0,
            'min': float('inf'),
            'max': float('-inf'),
            'count': 0
        }
    
    for idx, row in source_gdf.iterrows():
        feature_data = {}
        
        # Add all existing columns
        for column in row.index:
            if column != 'geometry':
                feature_data[column] = row[column]
        
        # Calculate additional columns and update summaries
        if 'area' in calculate_columns and hasattr(row.geometry, 'area'):
            area = round(row.geometry.area, decimal_places.get('area', 2))
            feature_data['area'] = area
            summary['area']['total'] += area
            summary['area']['min'] = min(summary['area']['min'], area)
            summary['area']['max'] = max(summary['area']['max'], area)
            summary['area']['count'] += 1
            
        if 'perimeter' in calculate_columns and hasattr(row.geometry, 'length'):
            perimeter = round(row.geometry.length, decimal_places.get('perimeter', 2))
            feature_data['perimeter'] = perimeter
            summary['perimeter']['total'] += perimeter
            summary['perimeter']['min'] = min(summary['perimeter']['min'], perimeter)
            summary['perimeter']['max'] = max(summary['perimeter']['max'], perimeter)
            summary['perimeter']['count'] += 1
            
        if 'centroid' in calculate_columns and hasattr(row.geometry, 'centroid'):
            centroid = row.geometry.centroid
            coord_decimals = decimal_places.get('coordinates', 6)
            feature_data['centroid'] = {
                'x': round(centroid.x, coord_decimals),
                'y': round(centroid.y, coord_decimals)
            }
            
        if 'bounds' in calculate_columns:
            bounds = row.geometry.bounds
            coord_decimals = decimal_places.get('coordinates', 6)
            feature_data['bounds'] = {
                'minx': round(bounds[0], coord_decimals),
                'miny': round(bounds[1], coord_decimals),
                'maxx': round(bounds[2], coord_decimals),
                'maxy': round(bounds[3], coord_decimals)
            }
            
        features_data.append(feature_data)
    
    # Calculate averages and clean up summaries
    for metric in ['area', 'perimeter']:
        if metric in summary:
            if summary[metric]['count'] > 0:
                summary[metric]['average'] = round(summary[metric]['total'] / summary[metric]['count'], 2)
                if summary[metric]['min'] == float('inf'):
                    summary[metric]['min'] = 0
                if summary[metric]['max'] == float('-inf'):
                    summary[metric]['max'] = 0
                summary[metric]['min'] = round(summary[metric]['min'], 2)
                summary[metric]['max'] = round(summary[metric]['max'], 2)
                summary[metric]['total'] = round(summary[metric]['total'], 2)
            else:
                summary[metric] = {
                    'total': 0,
                    'min': 0,
                    'max': 0,
                    'average': 0,
                    'count': 0
                }
    
    # Create report object
    report = {
        'layer_name': layer_name,
        'crs': str(crs),
        'feature_count': len(features_data),
        'summary': summary,
        'features': features_data
    }
    
    # Check if directory exists before writing
    if not ensure_path_exists(output_file):
        log_warning(f"Directory for {output_file} does not exist. Skipping report generation.")
        return all_layers[layer_name]
    
    # Write to JSON file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        log_info(f"Report written to {output_file}")
    except Exception as e:
        log_error(f"Error writing report to {output_file}: {str(e)}")
    
    # Return the original layer unchanged
    return all_layers[layer_name]