import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from typing import List, Dict, Any
import csv
import os

from src.project_loader import ProjectLoader

def generate_area_report(base_layer: gpd.GeoDataFrame, cover_layer: gpd.GeoDataFrame, 
                         output_file: str, report_name: str, project_loader: ProjectLoader,
                         include_labels: bool = True, include_total_area: bool = True, 
                         min_overlap_area: float = 0.01) -> None:
    """
    Generate an area report based on the coverage of the base layer by the cover layer.
    
    :param base_layer: GeoDataFrame containing the base polygons (e.g., Parcel)
    :param cover_layer: GeoDataFrame containing the cover polygons (e.g., Geltungsbereich NW)
    :param output_file: Path to the output file (without extension)
    :param report_name: Name of the report to be used as title
    :param project_loader: ProjectLoader instance to resolve full paths
    :param include_labels: Whether to include labels from the base layer in the report
    :param include_total_area: Whether to include the total covered area in the report
    :param min_overlap_area: Minimum overlap area to consider (to avoid floating point errors)
    """
    results = []
    total_area = 0

    for _, base_feature in base_layer.iterrows():
        base_geom = base_feature.geometry
        if not isinstance(base_geom, (Polygon, MultiPolygon)):
            continue

        intersection = base_geom.intersection(cover_layer.unary_union)
        if not intersection.is_empty and intersection.area > min_overlap_area:
            area = round(intersection.area, 2)
            total_area += area
            
            result = {
                'Area': area,
                'Geometry': intersection
            }
            
            if include_labels and 'label' in base_feature:
                result['Label'] = base_feature['label']
            
            results.append(result)

    # Sort results by area in descending order
    results.sort(key=lambda x: x['Area'], reverse=True)

    # Create a GeoDataFrame from the results
    result_gdf = gpd.GeoDataFrame(results, geometry='Geometry', crs=base_layer.crs)

    # Save to CSV
    csv_file = project_loader.resolve_full_path(f"{output_file}.csv")
    result_gdf.drop('Geometry', axis=1).to_csv(csv_file, index=False, float_format='%.2f')

    # Save to Excel
    excel_file = project_loader.resolve_full_path(f"{output_file}.xlsx")
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df = result_gdf.drop('Geometry', axis=1)
        df.to_excel(writer, sheet_name='Area Report', index=False, startrow=1)
        
        # Add title
        workbook = writer.book
        worksheet = writer.sheets['Area Report']
        worksheet.cell(row=1, column=1, value=report_name)
        
        # Add total area if requested
        if include_total_area:
            total_row = len(df) + 3
            worksheet.cell(row=total_row, column=1, value='Total Area')
            worksheet.cell(row=total_row, column=2, value=round(total_area, 2))

    print(f"Area report saved to {csv_file} and {excel_file}")

def process_area_report(report_config: Dict[str, Any], all_layers: Dict[str, gpd.GeoDataFrame], project_loader: ProjectLoader) -> None:
    """
    Process an area report based on the configuration.
    
    :param report_config: Dictionary containing the report configuration
    :param all_layers: Dictionary containing all available layers
    :param project_loader: ProjectLoader instance to resolve full paths
    """
    base_layer_name = report_config['baseLayer']
    cover_layer_name = report_config['coverLayer']
    output_file = report_config['output']['file']
    report_name = report_config['name']
    include_labels = report_config.get('includeLabels', True)
    include_total_area = report_config.get('includeTotalArea', True)

    if base_layer_name not in all_layers or cover_layer_name not in all_layers:
        print(f"Error: One or both layers not found for report {report_name}")
        return

    base_layer = all_layers[base_layer_name]
    cover_layer = all_layers[cover_layer_name]

    # Ensure output directory exists
    os.makedirs(os.path.dirname(project_loader.resolve_full_path(output_file)), exist_ok=True)

    generate_area_report(base_layer, cover_layer, output_file, report_name, project_loader, include_labels, include_total_area)

def process_all_reports(project_settings: Dict[str, Any], all_layers: Dict[str, gpd.GeoDataFrame], project_loader: ProjectLoader) -> None:
    """
    Process all reports defined in the project settings.
    
    :param project_settings: Dictionary containing the current project's settings
    :param all_layers: Dictionary containing all available layers
    :param project_loader: ProjectLoader instance to resolve full paths
    """
    if 'reports' not in project_settings:
        print("No reports defined in project settings")
        return

    for report_config in project_settings['reports']:
        if report_config['type'] == 'area':
            process_area_report(report_config, all_layers, project_loader)
        else:
            print(f"Unknown report type: {report_config['type']}")