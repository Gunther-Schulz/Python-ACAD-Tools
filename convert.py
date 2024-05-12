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
        # Display the shapefile before converting
        plot_shapefile(input_shapefile)

    # Open the shapefile
    driver = ogr.GetDriverByName('ESRI Shapefile')
    dataSource = driver.Open(input_shapefile, 0)  # 0 means read-only
    layer = dataSource.GetLayer()

    # Create a new DXF document with a specific version
    doc = ezdxf.new(dxfversion='AC1027')  # Example: 'AC1027' for AutoCAD 2013

    # Create or get the 'parcels' layer
    if 'parcels' not in doc.layers:
        parcels_layer = doc.layers.new('parcels')
    else:
        parcels_layer = doc.layers.get('parcels')

    msp = doc.modelspace()

    # Iterate through features in the layer
    for feature in layer:
        geometry = feature.GetGeometryRef()
        if geometry.GetGeometryType() == ogr.wkbPolygon:
            # Convert polygon to polyline
            ring = geometry.GetGeometryRef(0)
            points = ring.GetPoints()  # Get points of the outer ring
            # Add polyline to the DXF file on the 'parcels' layer
            msp.add_lwpolyline(points, close=True, dxfattribs={'layer': 'parcels'})

    # Save the DXF file
    doc.saveas(output_dwg)

if __name__ == "__main__":
    plot = False
    if "-p" in sys.argv:
        plot = True
        sys.argv.remove("-p")  # Remove the plot option to simplify further argument processing

    if len(sys.argv) != 3:
        print("Usage: python convert.py <input_shapefile> <output_dwg> [-p]")
        sys.exit(1)
    
    input_shapefile = sys.argv[1]
    output_dwg = sys.argv[2]
    shape_to_dwg(input_shapefile, output_dwg, plot)