import os
import geopandas as gpd
import ezdxf
from shapely.geometry import Polygon

parcel_list = ["1", "2", "4", "6", "7"]
plot = False
parcel_shapefile = "./data/Plasten Nr1 Flurstücke.shp"
flur_shapefile = "./data/flur.shp"


def load_shapefile(file_path):
    return gpd.read_file(file_path)


parcel = load_shapefile(parcel_shapefile)
flur = load_shapefile(flur_shapefile)

# Filter parcels that are in the parcel_list
target_parcels = parcel[parcel['id'].isin(parcel_list)]

# Function to conditionally buffer each flur polygon


def conditional_buffer(flur_geom):
    positive_buffer = flur_geom.buffer(2)
    if any(positive_buffer.intersects(parcel_geom) for parcel_geom in target_parcels['geometry']):
        return flur_geom.buffer(-2)
    else:
        return positive_buffer


# Apply conditional buffering to each flur polygon
flur['geometry'] = flur['geometry'].apply(conditional_buffer)

# Create a new DXF document
doc = ezdxf.new('R2010', setup=True)
msp = doc.modelspace()

# Define layers
doc.layers.new(name='Flur', dxfattribs={'color': 2})
doc.layers.new(name='Parcel', dxfattribs={'color': 3})

# Add flur geometries to the DXF
for index, row in flur.iterrows():
    geom = row['geometry']
    if geom.geom_type == 'Polygon':
        points = [(x, y) for x, y in geom.exterior.coords]
        msp.add_lwpolyline(points, close=True, dxfattribs={'layer': 'Flur'})

# Add parcel geometries to the DXF
for index, row in parcel.iterrows():
    geom = row['geometry']
    if geom.geom_type == 'Polygon':
        points = [(x, y) for x, y in geom.exterior.coords]
        msp.add_lwpolyline(points, close=True, dxfattribs={'layer': 'Parcel'})

# Save the DXF file
dxf_filename = "/Users/guntherschulz/IONOS HiDrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/Zeichnung/combined.dxf"
doc.saveas(dxf_filename)
