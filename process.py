import os
import geopandas as gpd
import ezdxf
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
import matplotlib.pyplot as plt

# Constants
CRS = "EPSG:25833"
PARCEL_LABEL = "label"
PARCEL_SHAPEFILE = "./data/Plasten Nr1 Flurstücke.shp"
FLUR_SHAPEFILE = "./data/flur.shp"
FLUR_LABEL = "flurname"
DXF_FILENAME = "/Users/guntherschulz/IONOS HiDrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/Zeichnung/combined.dxf"

# Load shapefile


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
    centroids = source_geom.centroid
    return gpd.GeoDataFrame(geometry=centroids, data={"label": source_geom[label]})


def setup_document_style(doc, text_style_name):
    if text_style_name not in doc.styles:
        doc.styles.new(name=text_style_name, dxfattribs={
                       'font': 'Arial.ttf', 'height': 0.1})


def add_text(msp, text, x, y, layer_name, style_name):
    msp.add_text(text, dxfattribs={'style': style_name,
                 'layer': layer_name, 'insert': (x, y)})


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
    msp = doc.modelspace()
    setup_document_style(doc, 'Parcel Number')
    add_geometries_to_dxf(
        msp, [target_parcels['geometry'].unary_union], 'Geltungsbereich')
    add_geometries_to_dxf(msp, flur['geometry'], 'Flur')
    add_geometries_to_dxf(msp, parcels['geometry'], 'Parcel')
    add_text_to_centroids(msp, parcel_points, 'Parcel Number')

    doc.saveas(DXF_FILENAME)


if __name__ == "__main__":
    main()
