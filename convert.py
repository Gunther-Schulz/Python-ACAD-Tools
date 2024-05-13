import os
import geopandas as gpd
import matplotlib.pyplot as plt
from osgeo import ogr
import ezdxf
from shapely.geometry import Polygon


plot = False
parcel_shapefile = "./data/Plasten Nr1 Flurstcke.shp"
flur_shapefile = "./data/flur.shp"
output_dwg = "/Users/guntherschulz/IONOS HiDrive/Öffentlich Planungsbro Schulz/Projekte/23-24 Maxsolar - Plasten/Zeichnung/parcels.dxf"


def plot_shapefile(input_shapefile):
    gdf = gpd.read_file(input_shapefile)
    gdf.plot()
    plt.show()


def shape_to_dwg(input_shapefile, output_dwg, plot=False):
    if not os.path.exists(input_shapefile):
        print(f"Error: The file {input_shapefile} does not exist.")
        return
    if plot:
        plot_shapefile(input_shapefile)
    driver = ogr.GetDriverByName('ESRI Shapefile')
    dataSource = driver.Open(input_shapefile, 0)  # 0 means read-only
    layer = dataSource.GetLayer()

    doc = ezdxf.new(dxfversion='AC1032')
    setup_document_styles_and_layers(doc)

    msp = doc.modelspace()

    # Process parcels
    process_features(layer, msp, 'Parcels', 'Parcel Number', 'label')

    # Load and process Flur shapefile
    if os.path.exists(flur_shapefile):
        flur_data_source = driver.Open(flur_shapefile, 0)
        flur_layer = flur_data_source.GetLayer()
        process_features(flur_layer, msp, 'Flur',
                         'Parcel Number', 'flurname', offset=True)

    doc.saveas(output_dwg)


def setup_document_styles_and_layers(doc):
    text_style_name = 'Parcel Number'
    if text_style_name not in doc.styles:
        doc.styles.new(name=text_style_name, dxfattribs={
                       'font': 'Arial.ttf', 'height': 0.1})

    for layer_name in ['Parcels', 'Parcel Number', 'Flur']:
        if layer_name not in doc.layers:
            doc.layers.new(layer_name)


def process_features(layer, msp, layer_name, text_style_name, label_field_name, offset=False):
    for feature in layer:
        geometry = feature.GetGeometryRef()
        if geometry.GetGeometryType() == ogr.wkbPolygon:
            points = geometry.GetGeometryRef(0).GetPoints()
            if offset:
                points = apply_offset(points, 2)  # Apply an offset of 2 units
            add_polygon(msp, points, layer_name)

            centroid_x, centroid_y = calculate_centroid(points)
            add_point(msp, centroid_x, centroid_y, 'Parcels', 2)

            label_value = feature.GetField(label_field_name)
            add_text(msp, label_value, centroid_x, centroid_y, text_style_name)


def apply_offset(points, offset_distance):
    polygon = Polygon(points)
    simplified_polygon = polygon.simplify(0.1, preserve_topology=True)
    offset_polygon = simplified_polygon.buffer(offset_distance)
    return list(offset_polygon.exterior.coords) if not offset_polygon.is_empty else points


def calculate_centroid(points):
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    return sum(x_coords) / len(x_coords), sum(y_coords) / len(y_coords)


def add_polygon(msp, points, layer_name):
    msp.add_lwpolyline(points, close=True, dxfattribs={'layer': layer_name})


def add_point(msp, x, y, layer_name, color):
    msp.add_point((x, y), dxfattribs={'layer': layer_name, 'color': color})


def add_text(msp, text, x, y, style):
    msp.add_text(text, dxfattribs={'style': style,
                 'layer': 'Parcel Number', 'insert': (x, y)})


if __name__ == "__main__":
    shape_to_dwg(parcel_shapefile, output_dwg, plot)
