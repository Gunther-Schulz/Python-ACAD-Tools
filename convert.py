import geopandas as gpd
import ezdxf
import matplotlib.pyplot as plt
import sys
import json
import os

import yaml  # Import the yaml module

def load_project_settings(project_name: str):
    with open('projects.yaml', 'r') as file:
        data = yaml.safe_load(file)
        projects = data['projects']
        folder_prefix = data.get('folderPrefix', '')  # Get folderPrefix or default to empty string
        return next((project for project in projects if project['name'] == project_name), None), folder_prefix

def resolve_full_path(path: str, prefix: str) -> str:
    """Resolve the full path, expanding user directory if necessary, and adding the folder prefix."""
    return os.path.abspath(os.path.expanduser(os.path.join(prefix, path)))

def get_layer_info(project_settings, layer_name):
    shapefile = next((layer['shapeFile']
                     for layer in project_settings['layers'] if layer['name'] == layer_name), None)
    label = next((layer['label'] for layer in project_settings['layers']
                 if layer['name'] == layer_name), None)
    return shapefile, label


def load_template(project_settings):
    template_path = project_settings.get('template')  # Use get to handle missing template key
    if template_path:
        full_template_path = resolve_full_path(template_path)
        doc = ezdxf.readfile(full_template_path)
        return doc
    return None  # Return None if no template path is provided


def load_shapefile(file_path):
    gdf = gpd.read_file(file_path)
    gdf = gdf.set_crs(CRS, allow_override=True)
    return gdf


def geoms_missing(gdf: gpd.GeoDataFrame, coverage: dict) -> set:
    return set(coverage["parcelList"]).difference(gdf[PARCEL_LABEL])

# Filter parcels


def filter_parcels(parcel, flur, gemarkung, gemeinde, coverage):

    parcels_missing = geoms_missing(parcel, coverage)

    if not parcels_missing:
        print("All parcels found.")

    buffered_flur = flur[flur[FLUR_LABEL].isin(
        coverage["flurList"])].unary_union.buffer(-10)
    buffered_gemeinde = gemeinde[gemeinde[GEMEINDE_LABEL].isin(
        coverage["gemeindeList"])].unary_union.buffer(-10)
    buffered_gemarkung = gemarkung[gemarkung[GEMARKUNG_LABEL].isin(
        coverage["gemarkungList"])].unary_union.buffer(-10)

    selected_parcels = parcel[parcel[PARCEL_LABEL].isin(
        coverage["parcelList"])]

    selected_parcels_mask = parcel.index.isin(selected_parcels.index)

    # Create a boolean mask for parcels that intersect with buffered_flur
    flur_mask = parcel.intersects(buffered_flur)
    gemeinde_mask = parcel.intersects(buffered_gemeinde)
    gemarkung_mask = parcel.intersects(buffered_gemarkung)

    # Use logical AND between two boolean masks for indexing
    result = parcel[selected_parcels_mask &
                    flur_mask & gemeinde_mask & gemarkung_mask]

    # fig, ax = plt.subplots()
    # result.plot(ax=ax, color='green')
    # plt.show()

    return result


# Conditional buffer


def conditional_buffer(source_geom, target_geom, distance):
    if any(source_geom.intersects(geom) for geom in target_geom['geometry']):
        return source_geom.buffer(-distance)
    else:
        return source_geom.buffer(distance)

# Apply conditional buffering to flur geometries


def apply_conditional_buffering(source_geom, target_geom, distance):
    # TODO: If it crosses Geltungsbereich, increase distance by x. Try by using a combination of target_parcels and geltungsbereich
    source_geom['geometry'] = source_geom['geometry'].apply(
        lambda x: conditional_buffer(x, target_geom, distance))
    return source_geom  # This now ensures it returns a GeoDataFrame


def labeled_center_points(source_geom, label):
    # Use representative_point() to get a point within the polygon
    points_within = source_geom.representative_point()
    return gpd.GeoDataFrame(geometry=points_within, data={"label": source_geom[label]})


def add_text_style(doc, text_style_name):
    if text_style_name not in doc.styles:
        doc.styles.new(name=text_style_name, dxfattribs={
                       'font': 'Arial.ttf', 'height': 0.1})


def add_text(msp, text, x, y, layer_name, style_name):
    msp.add_text(text, dxfattribs={
                 'style': style_name,
                 'layer': layer_name,
                 # Initial insertion point, might not be used depending on alignment
                 'insert': (x, y),
                 'align_point': (x, y),  # Actual point for alignment
                 'halign': 1,  # Center alignment
                 'valign': 1   # Middle alignment
                 })


def add_text_to_center(msp, labeled_centroid_points_df, layer_name, style_name=None):
    if style_name is None or not msp.styles.has_entry(style_name):
        style_name = "default"
    for index, row in labeled_centroid_points_df.iterrows():
        x, y = row['geometry'].coords[0]
        add_text(msp, row['label'], x, y, layer_name, style_name)


# Add geometries to DXF


def add_geometries(msp, geometries, layer_name, close=False):
    for geom in geometries:
        if geom is None:
            print(f"Warning: None geometry encountered in layer '{layer_name}'")
        elif geom.geom_type == 'Polygon':
            points = [(x, y) for x, y in geom.exterior.coords]
            msp.add_lwpolyline(points, close=True, dxfattribs={'layer': layer_name})  # Close for polygons
        elif geom.geom_type == 'MultiPolygon':
            for polygon in geom.geoms:
                points = [(x, y) for x, y in polygon.exterior.coords]
                msp.add_lwpolyline(points, close=True, dxfattribs={'layer': layer_name})  # Close for polygons
        elif geom.geom_type == 'LineString':
            points = [(x, y) for x, y in geom.coords]
            msp.add_lwpolyline(points, close=False, dxfattribs={'layer': layer_name})  # Do not close for line strings
        elif geom.geom_type == 'MultiLineString':
            for line in geom.geoms:
                points = [(x, y) for x, y in line.coords]
                msp.add_lwpolyline(points, close=False, dxfattribs={'layer': layer_name})  # Do not close for line strings


def add_points_to_dxf(msp, points, layer_name):
    for point in points:
        msp.add_point(point, dxfattribs={'layer': layer_name})


def add_from_template(msp, template_dxf):
    doc = ezdxf.readfile(template_dxf)
    # msp.add_entities(doc.modelspace())
    # add Layout1
    msp.add_entities(doc.modelspace().get_layout('Layout1'))

# Main function


def add_layer(doc, layer_name, color):
    if not doc.layers.has_entry(layer_name):
        doc.layers.new(name=layer_name, dxfattribs={'color': color})

from shapely.ops import nearest_points
import shapely.geometry

from shapely.geometry import Point

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, LineString

from shapely.ops import linemerge, unary_union
import geopandas as gpd
import matplotlib.pyplot as plt
import random

def select_parcel_edges(geom):

    # Initialize a list to hold the edges derived from the input geometry
    edge_lines = []
    
    # Loop through each polygon in the input geometry collection
    for poly in geom.geometry:
        # Extract the boundary of the polygon, converting it to a linestring
        boundary_line = poly.boundary
        
        # Create an outward buffer of 10 units from the boundary line
        buffered_line_out = boundary_line.buffer(10, join_style=2)  # Outward buffer with a mitered join
        # Create an inward buffer of 10 units from the boundary line
        buffered_line_in = boundary_line.buffer(-10, join_style=2)  # Inward buffer with a mitered join
        
        # Handle MultiPolygon and Polygon cases for outward buffer
        if buffered_line_out.geom_type == 'MultiPolygon':
            for part in buffered_line_out.geoms:  # Iterate over geoms attribute
                edge_lines.append(part.exterior)
        elif buffered_line_out.geom_type == 'Polygon':
            edge_lines.append(buffered_line_out.exterior)
        
        # Handle MultiPolygon and Polygon cases for inward buffer
        if buffered_line_in.geom_type == 'MultiPolygon':
            for part in buffered_line_in.geoms:  # Iterate over geoms attribute
                edge_lines.append(part.exterior)
        elif buffered_line_in.geom_type == 'Polygon':
            edge_lines.append(buffered_line_in.exterior)

    # Plot each edge line in the edge_lines list
    fig, ax = plt.subplots()
    for edge in edge_lines:
        gpd.GeoSeries([edge]).plot(ax=ax, linewidth=1.5)
    ax.set_title('Edge Lines Visualization')
    plt.show()
    
    # Merge and simplify the collected edge lines into a single geometry
    merged_edges = linemerge(unary_union(edge_lines))
    
    # Create a GeoDataFrame to hold the merged edges, preserving the original CRS
    result_gdf = gpd.GeoDataFrame(geometry=[merged_edges], crs=geom.crs)
    
    # Output the type of geometry contained in the resulting GeoDataFrame
    print(f"The type of geometry in result_gdf is: {type(result_gdf.geometry.iloc[0])}")
    
    # Set up a plot to visually compare the original and modified geometries
    fig, ax = plt.subplots()
    # Plot the original geometry boundary with a blue line
    geom.boundary.plot(ax=ax, color='blue', linewidth=5, label='Original Geometry')
    # Plot each segment of the merged edges in a randomly chosen color
    if not result_gdf.empty:
        for line in merged_edges.geoms:
            # Generate a random color for each segment
            random_color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            # Plot the segment with the randomly chosen color
            gpd.GeoSeries([line]).plot(ax=ax, color=random_color, linewidth=1.5)
    # Set the title of the plot and display the legend
    ax.set_title('Comparison of Original and Offset Geometries')
    ax.legend()
    # Display the plot
    plt.show()

    # Return the GeoDataFrame containing the processed geometry
    return result_gdf


def main():
    project_settings, folder_prefix = load_project_settings(sys.argv[1])
    if project_settings:
        CRS = project_settings['crs']
        DXF_FILENAME = resolve_full_path(project_settings['dxfFilename'], folder_prefix)
        TEMPLATE_DXF = resolve_full_path(project_settings.get('template', ''), folder_prefix) if project_settings.get('template') else None
        GEMEINDE_SHAPEFILE, GEMEINDE_LABEL = get_layer_info(
            project_settings, "Gemeinde")
        GEMARKUNG_SHAPEFILE, GEMARKUNG_LABEL = get_layer_info(
            project_settings, "Gemarkung")
        FLUR_SHAPEFILE, FLUR_LABEL = get_layer_info(project_settings, "Flur")
        PARCEL_SHAPEFILE, PARCEL_LABEL = get_layer_info(
            project_settings, "Parcel")
        WALD_SHAPEFILE, WALD_LABEL = get_layer_info(
            project_settings, "Wald")  # Added Wald
        BIOTOPE_SHAPEFILE, BIOTOPE_LABEL = get_layer_info(
            project_settings, "Biotope")  # Added Biotope
        COLORS = {layer['name']: layer['color']
                  for layer in project_settings['layers']}
        COVERAGE = project_settings['coverage']
    else:
        print(f"Project {sys.argv[1]} not found.")

    parcels = load_shapefile(resolve_full_path(PARCEL_SHAPEFILE, folder_prefix))
    flur = load_shapefile(resolve_full_path(FLUR_SHAPEFILE, folder_prefix))
    orig_flur = load_shapefile(resolve_full_path(FLUR_SHAPEFILE, folder_prefix))
    gemarkung = load_shapefile(resolve_full_path(GEMARKUNG_SHAPEFILE, folder_prefix))
    gemeinde = load_shapefile(resolve_full_path(GEMEINDE_SHAPEFILE, folder_prefix))
    wald = load_shapefile(resolve_full_path(WALD_SHAPEFILE, folder_prefix))  # Added Wald
    biotope = load_shapefile(resolve_full_path(BIOTOPE_SHAPEFILE, folder_prefix))  # Added Biotope

    target_parcels = filter_parcels(
        parcels, flur, gemarkung, gemeinde, COVERAGE)
    # check if this actually works by switching sides
    # flur = apply_conditional_buffering(flur, target_parcels, 2)
    geltungsbereich = target_parcels['geometry'].unary_union

    # Buffer the wald geometries by 30 units
    wald_buffered = wald.buffer(30)

    # Reduce geltungsbereich by where it overlays the buffered wald
    geltungsbereich = geltungsbereich.difference(wald_buffered.unary_union)

    parcel_points = labeled_center_points(parcels, PARCEL_LABEL)
    # flur_points = labeled_center_points(flur, FLUR_LABEL)
    gemeinde_points = labeled_center_points(gemeinde, GEMEINDE_LABEL)
    gemarkung_points = labeled_center_points(gemarkung, GEMARKUNG_LABEL)
    # wald_points = labeled_center_points(wald, WALD_LABEL)  # Added Wald
    # biotope_points = labeled_center_points(biotope, BIOTOPE_LABEL)  # Added Biotope

    TEMPLATE_DXF = resolve_full_path(project_settings.get('template'), folder_prefix) if project_settings.get('template') else None
    if project_settings['useTemplate'] and TEMPLATE_DXF:
        doc = load_template(project_settings)
    else:
        doc = ezdxf.new('R2010', setup=True)

    # Add defaults
    add_text_style(doc, 'default')

    # This is optional and only useful if we want to set some attributes to the layer. Otherwise defaults are used
    add_layer(doc, 'Flur', COLORS['Flur'])
    add_layer(doc, 'FlurOrig', 3)
    add_layer(doc, 'Gemeinde', COLORS['Gemeinde'])
    add_layer(doc, 'Gemarkung', COLORS['Gemarkung'])
    add_layer(doc, 'Parcel', COLORS['Parcel'])
    add_layer(doc, 'Parcel Number', COLORS['Parcel'])
    add_layer(doc, 'Flur Number', COLORS['Flur'])
    add_layer(doc, 'Wald', COLORS['Wald'])  # Added Wald
    add_layer(doc, 'Biotope', COLORS['Biotope'])  # Added Biotope
    # add_layer(doc, 'Gemeinde Name', COLORS['Gemeinde'])
    # add_layer(doc, 'Gemarkung Name', COLORS['Gemarkung'])

    add_layer(doc, 'Geltungsbereich', 10)
    add_text_style(doc, 'Parcel Number')
    add_text_style(doc, 'Flur Number')
    add_text_style(doc, 'Gemeinde Name')
    add_text_style(doc, 'Gemarkung Name')

    msp = doc.modelspace()

    flur = select_parcel_edges(flur)
    # add_geometries(msp, flur['geometry'], 'Flur', True)

    # add_geometries(msp, parcels['geometry'], 'Parcel', True)
    add_geometries(
        msp, [geltungsbereich], 'Geltungsbereich', True)
    # add_geometries(msp, orig_flur['geometry'], 'Flur', True)
    # add_geometries(msp, flur['geometry'], 'Flur', True)
    # add_geometries(msp, gemeinde['geometry'], 'Gemeinde', True)
    # add_geometries(msp, gemarkung['geometry'], 'Gemarkung', True)
    # add_geometries(msp, wald['geometry'], 'Wald', True)  # Added Wald
    # add_geometries(msp, biotope['geometry'], 'Biotope', True)  # Added Biotope
    # add_text_to_center(msp, parcel_points, 'Parcel Number')
    # add_text_to_center(msp, flur_points, 'Flur Number')
    # add_text_to_center(msp, gemeinde_points, 'Gemeinde Name')
    # add_text_to_center(msp, gemarkung_points, 'Gemarkung Name')
    # add_text_to_center(msp, wald_points, 'Wald Name')  # Added Wald
    # add_text_to_center(msp, biotope_points, 'Biotope Name')  # Added Biotope

    doc.saveas(DXF_FILENAME)
    print(f"Saved {DXF_FILENAME}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process.py <project_name>")
        sys.exit(1)

    # project_settings, folder_prefix = load_project_settings(sys.argv[1])
    # print(project_settings)
    # if project_settings:
    #     CRS = project_settings['crs']
    #     DXF_FILENAME = resolve_full_path(project_settings['dxfFilename'], folder_prefix)
    #     TEMPLATE_DXF = resolve_full_path(project_settings.get('template', ''), folder_prefix) if project_settings.get('template') else None
    #     GEMEINDE_SHAPEFILE, GEMEINDE_LABEL = get_layer_info(project_settings, "Gemeinde")
    #     GEMARKUNG_SHAPEFILE, GEMARKUNG_LABEL = get_layer_info(project_settings, "Gemarkung")
    #     FLUR_SHAPEFILE, FLUR_LABEL = get_layer_info(project_settings, "Flur")
    #     PARCEL_SHAPEFILE, PARCEL_LABEL = get_layer_info(project_settings, "Parcel")
    #     COLORS = {layer['name']: layer['color'] for layer in project_settings['layers']}
    #     COVERAGE = project_settings['coverage']
    #     main()
    # else:
    #     print(f"Project {sys.argv[1]} not found.")

