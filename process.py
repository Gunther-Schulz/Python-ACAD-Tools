import geopandas as gpd
import ezdxf
import matplotlib.pyplot as plt
import sys
import json


def load_project_settings(project_name):
    with open('projects.json', 'r') as file:
        projects = json.load(file)['projects']
        project = next(
            (project for project in projects if project['name'] == project_name), None)
        return project


def load_shapefile(file_path):
    gdf = gpd.read_file(file_path)
    gdf = gdf.set_crs(CRS, allow_override=True)
    return gdf

# Filter parcels


def filter_parcels(parcel, flur, parcel_list, flur_list):
    buffered_flur = flur[flur[FLUR_LABEL].isin(
        flur_list)].unary_union.buffer(-10)
    return parcel[(parcel[PARCEL_LABEL].isin(parcel_list)) & (parcel.intersects(buffered_flur))]

# Conditional buffer


def conditional_buffer(source_geom, target_geom, distance):
    if any(source_geom.intersects(geom) for geom in target_geom['geometry']):
        return source_geom.buffer(-distance)
    else:
        return source_geom.buffer(distance)

# Apply conditional buffering to flur geometries


def apply_conditional_buffering(source_geom, target_geom, distance):
    source_geom['geometry'] = source_geom['geometry'].apply(
        lambda x: conditional_buffer(x, target_geom, distance))
    return source_geom


def labeled_centroid_points(source_geom, label):
    # Use representative_point() to get a point within the polygon
    points_within = source_geom.representative_point()
    return gpd.GeoDataFrame(geometry=points_within, data={"label": source_geom[label]})


def setup_textt_style(doc, text_style_name):
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


def add_text_to_centroids(msp, labeled_centroid_points_df, layer_name, style_name=None):
    if style_name is None:
        style_name = layer_name
    for index, row in labeled_centroid_points_df.iterrows():
        x, y = row['geometry'].coords[0]
        add_text(msp, row['label'], x, y, layer_name, style_name)

    # Create DXF document


# Add geometries to DXF


def add_geometries_to_dxf(msp, geometries, layer_name):
    for geom in geometries:
        if geom.geom_type == 'Polygon':
            points = [(x, y) for x, y in geom.exterior.coords]
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               'layer': layer_name})
        elif geom.geom_type == 'MultiPolygon':
            for polygon in geom.geoms:
                points = [(x, y) for x, y in polygon.exterior.coords]
                msp.add_lwpolyline(points, close=True, dxfattribs={
                                   'layer': layer_name})


def add_points_to_dxf(msp, points, layer_name):
    for point in points:
        msp.add_point(point, dxfattribs={'layer': layer_name})


# Main function


def main():
    parcels = load_shapefile(PARCEL_SHAPEFILE)
    flur = load_shapefile(FLUR_SHAPEFILE)
    parcel_list = ["1", "2", "4", "6", "7"]
    flur_list = ["Flur 1"]
    target_parcels = filter_parcels(parcels, flur, parcel_list, flur_list)
    flur = apply_conditional_buffering(flur, target_parcels, 2)
    parcel_points = labeled_centroid_points(parcels, PARCEL_LABEL)

    doc = ezdxf.new('R2010', setup=True)

    doc.layers.new(name='Flur', dxfattribs={'color': 2})
    doc.layers.new(name='Parcel', dxfattribs={'color': 3})
    doc.layers.new(name='Geltungsbereich', dxfattribs={'color': 10})
    setup_textt_style(doc, 'Parcel Number')

    msp = doc.modelspace()

    add_geometries_to_dxf(
        msp, [target_parcels['geometry'].unary_union], 'Geltungsbereich')
    add_geometries_to_dxf(msp, flur['geometry'], 'Flur')
    add_geometries_to_dxf(msp, parcels['geometry'], 'Parcel')
    add_text_to_centroids(msp, parcel_points, 'Parcel Number')

    doc.saveas(DXF_FILENAME)
    print(f"Saved {DXF_FILENAME}")


if __name__ == "__main__":
    if len(sys.argv) < 1:
        print("Usage: python process.py <project_name>")

    project_settings = load_project_settings(sys.argv[1])
    if project_settings:
        CRS = project_settings['crs']
        DXF_FILENAME = project_settings['dxfFilename']
        FLUR_SHAPEFILE = next(
            (layer['shapeFile'] for layer in project_settings['layers'] if layer['name'] == "Flur"), None)
        FLUR_LABEL = next(
            (layer['label'] for layer in project_settings['layers'] if layer['name'] == "Flur"), None)
        PARCEL_SHAPEFILE = next(
            (layer['shapeFile'] for layer in project_settings['layers'] if layer['name'] == "Parcel"), None)
        PARCEL_LABEL = next(
            (layer['label'] for layer in project_settings['layers'] if layer['name'] == "Parcel"), None)
    # Add your processing logic here

    else:
        print(f"Project {sys.argv[1]} not found.")

    main()
