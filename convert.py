import os
import sys
import geopandas as gpd
import matplotlib.pyplot as plt
from osgeo import ogr
import ezdxf


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
    if 'parcels' not in doc.layers:
        parcels_layer = doc.layers.new('parcels')
    else:
        parcels_layer = doc.layers.get('parcels')

    msp = doc.modelspace()

    for feature in layer:
        geometry = feature.GetGeometryRef()
        if geometry.GetGeometryType() == ogr.wkbPolygon:
            ring = geometry.GetGeometryRef(0)
            points = ring.GetPoints()
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               'layer': 'parcels'})

            # Manually calculate the centroid of the polygon
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            centroid_x = sum(x_coords) / len(x_coords)
            centroid_y = sum(y_coords) / len(y_coords)

            # Add a point at the centroid
            msp.add_point((centroid_x, centroid_y), dxfattribs={
                          'layer': 'parcels', 'color': 2})

    doc.saveas(output_dwg)


if __name__ == "__main__":
    plot = False
    # if "-p" in sys.argv:
    #     plot = True
    #     # Remove the plot option to simplify further argument processing
    #     sys.argv.remove("-p")

    # if len(sys.argv) != 3:
    #     print("Usage: python convert.py <input_shapefile> <output_dwg> [-p]")
    #     sys.exit(1)

    # input_shapefile = sys.argv[1]
    # output_dwg = sys.argv[2]
    input_shapefile = "./data/Plasten Nr1 Flurstücke.shp"
    output_dwg = "/Users/guntherschulz/IONOS HiDrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/Zeichnung/parcels.dxf"
    shape_to_dwg(input_shapefile, output_dwg, plot)
