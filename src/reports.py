import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from typing import List, Dict, Any
import csv
import os

def generate_area_report(base_layer: gpd.GeoDataFrame, cover_layer: gpd.GeoDataFrame, 
                         output_file: str, include_labels: bool = True, 
                         include_total_area: bool = True) -> None:
    """
    Generate an area report based on the coverage of the base layer by the cover layer.
    
    :param base_layer: GeoDataFrame containing the base polygons (e.g., Parcel)
    :param cover_layer: GeoDataFrame containing the cover polygons (e.g., Geltungsbereich NW)
    :param output_file: Path to the output CSV file
    :param include_labels: Whether to include labels from the base layer in the report
    :param include_total_area: Whether to include the total covered area in the report
    """
    results = []
    total_area = 0

    for _, base_feature in base_layer.iterrows():
        base_geom = base_feature.geometry
        if not isinstance(base_geom, (Polygon, MultiPolygon)):
            continue

        intersection = base_geom.intersection(cover_layer.unary_union)
        if not intersection.is_empty:
            area = intersection.area
            total_area += area
            
            result = {
                'Area': area,
                'Geometry': intersection
            }
            
            if include_labels and 'label' in base_feature:
                result['Label'] = base_feature['label']
            
            results.append(result)

    # Create a GeoDataFrame from the results
    result_gdf = gpd.GeoDataFrame(results, geometry='Geometry', crs=base_layer.crs)

    # Save to CSV
    result_gdf.drop('Geometry', axis=1).to_csv(output_file, index=False)

    # Append total area if requested
    if include_total_area:
        with open(output_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([])
            writer.writerow(['Total Area', total_area])

    print(f"Area report saved to {output_file}")

def process_area_report(report_config: Dict[str, Any], all_layers: Dict[str, gpd.GeoDataFrame]) -> None:
    """
    Process an area report based on the configuration.
    
    :param report_config: Dictionary containing the report configuration
    :param all_layers: Dictionary containing all available layers
    """
    base_layer_name = report_config['baseLayer']
    cover_layer_name = report_config['coverLayer']
    output_file = report_config['output']['file']
    include_labels = report_config.get('includeLabels', True)
    include_total_area = report_config.get('includeTotalArea', True)

    if base_layer_name not in all_layers or cover_layer_name not in all_layers:
        print(f"Error: One or both layers not found for report {report_config['name']}")
        return

    base_layer = all_layers[base_layer_name]
    cover_layer = all_layers[cover_layer_name]

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    generate_area_report(base_layer, cover_layer, output_file, include_labels, include_total_area)

def process_all_reports(project_settings: Dict[str, Any], all_layers: Dict[str, gpd.GeoDataFrame]) -> None:
    """
    Process all reports defined in the project settings.
    
    :param project_settings: Dictionary containing the current project's settings
    :param all_layers: Dictionary containing all available layers
    """
    if 'reports' not in project_settings:
        print("No reports defined in project settings")
        return

    for report_config in project_settings['reports']:
        if report_config['type'] == 'area':
            process_area_report(report_config, all_layers)
        else:
            print(f"Unknown report type: {report_config['type']}")