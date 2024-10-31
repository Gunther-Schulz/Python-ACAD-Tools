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
    
    # Get additional columns to calculate
    calculate_columns = operation.get('calculate', [])
    
    # Create report data
    features_data = []
    
    for idx, row in source_gdf.iterrows():
        feature_data = {}
        
        # Add all existing columns
        for column in row.index:
            if column != 'geometry':
                feature_data[column] = row[column]
        
        # Calculate additional columns
        if 'area' in calculate_columns and hasattr(row.geometry, 'area'):
            feature_data['area'] = round(row.geometry.area, 2)
            
        if 'perimeter' in calculate_columns and hasattr(row.geometry, 'length'):
            feature_data['perimeter'] = round(row.geometry.length, 2)
            
        if 'centroid' in calculate_columns and hasattr(row.geometry, 'centroid'):
            centroid = row.geometry.centroid
            feature_data['centroid'] = {
                'x': round(centroid.x, 6),
                'y': round(centroid.y, 6)
            }
            
        if 'bounds' in calculate_columns:
            bounds = row.geometry.bounds
            feature_data['bounds'] = {
                'minx': round(bounds[0], 6),
                'miny': round(bounds[1], 6),
                'maxx': round(bounds[2], 6),
                'maxy': round(bounds[3], 6)
            }
            
        features_data.append(feature_data)
    
    # Create report object
    report = {
        'layer_name': layer_name,
        'crs': str(crs),
        'feature_count': len(features_data),
        'features': features_data
    }
    
    # Check if directory exists before writing - use the full resolved path
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