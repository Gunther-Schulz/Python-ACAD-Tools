import os
import sys
import geopandas as gpd
import matplotlib.pyplot as plt
from osgeo import ogr
import ezdxf
from shapely.geometry import Polygon, LineString
from shapely.affinity import translate


parcel_list = ["1", "2", "4", "6", "7"]


def plot_shapefile(input_shapefile):
    # Load the shapefile
    gdf = gpd.read_file(input_shapefile)
    # Plot the shapefile
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
    # Define a text style that can be modified in AutoCAD
    text_style_name = 'Parcel Number'
    if text_style_name not in doc.styles:
        doc.styles.new(name=text_style_name, dxfattribs={
                       'font': 'Arial.ttf', 'height': 0.1})

    if 'Parcels' not in doc.layers:
        parcels_layer = doc.layers.new('Parcels')
    if 'Parcel Number' not in doc.layers:
        parcels_number_layer = doc.layers.new('Parcel Number')
    if 'Flur' not in doc.layers:
        flur_layer = doc.layers.new('Flur')

    msp = doc.modelspace()

    # Process parcels
    process_layer(layer, msp, 'Parcels', text_style_name)

    # Load and process Flur shapefile
    flur_shapefile = './data/flur.shp'
    if not os.path.exists(flur_shapefile) or os.path.getsize(flur_shapefile) == 0:
        print(f"Error: The file {flur_shapefile} was not found or is empty.")
    if os.path.exists(flur_shapefile):
        flur_data_source = driver.Open(flur_shapefile, 0)
        flur_layer = flur_data_source.GetLayer()
        process_layer(flur_layer, msp, 'Flur', text_style_name, offset=True)

    doc.saveas(output_dwg)


def process_layer(layer, msp, layer_name, text_style_name, offset=False):
    label_field_name = "label" if layer_name == "Parcels" else "flurname" if layer_name == "Flur" else "label"
    for feature in layer:
        geometry = feature.GetGeometryRef()
        if geometry.GetGeometryType() == ogr.wkbPolygon:
            ring = geometry.GetGeometryRef(0)
            points = ring.GetPoints()
            if offset:
                points = apply_offset(points, 2)  # Apply an offset of 2 units
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               'layer': layer_name})

            # Manually calculate the centroid of the polygon
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            centroid_x = sum(x_coords) / len(x_coords)
            centroid_y = sum(y_coords) / len(y_coords)

            # Add a point at the centroid on the 'parcels' layer
            msp.add_point((centroid_x, centroid_y), dxfattribs={
                          'layer': 'Parcels', 'color': 2})

            # Draw an X at the centroid on the 'X' layer
            size = 0.1  # Size of the X, adjust as needed
            msp.add_line((centroid_x - size, centroid_y - size), (centroid_x +
                         size, centroid_y + size), dxfattribs={'layer': 'X', 'color': 1})
            msp.add_line((centroid_x - size, centroid_y + size), (centroid_x +
                         size, centroid_y - size), dxfattribs={'layer': 'X', 'color': 1})
            field_count = feature.GetFieldCount()

            # Get the label value from the feature
            label_value = feature.GetField(label_field_name)

            # Add TEXT with the label value at the centroid on the 'O' layer
            msp.add_text(label_value, dxfattribs={
                         'style': text_style_name, 'layer': 'Parcel Number', 'insert': (centroid_x, centroid_y)})


def apply_offset(points, offset_distance):
    # Create a polygon from the points
    polygon = Polygon(points)

    # Simplify the polygon to avoid overly complex offsets
    simplified_polygon = polygon.simplify(0.1, preserve_topology=True)

    # Create an offset polygon, positive distance for outward, negative for inward
    offset_polygon = simplified_polygon.buffer(offset_distance)

    # Extract the exterior points of the offset polygon
    if offset_polygon.is_empty:
        return points  # Return original if offset results in an empty polygon
    else:
        return list(offset_polygon.exterior.coords)


if __name__ == "__main__":
    plot = False
    parcel_shapefile = "./data/Plasten Nr1 Flurstücke.shp"
    output_dwg = "/Users/guntherschulz/IONOS HiDrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/Zeichnung/parcels.dxf"
    shape_to_dwg(parcel_shapefile, output_dwg, plot)
