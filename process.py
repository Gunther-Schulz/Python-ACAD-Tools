import os
import geopandas as gpd
import ezdxf
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
import matplotlib.pyplot as plt


parcel_list = ["1", "2", "4", "6", "7"]
flur_list = ["Flur 1"]
plot = True
parcel_label_field = "label"
parcel_shapefile = "./data/Plasten Nr1 Flurstücke.shp"
flur_shapefile = "./data/flur.shp"
flur_label_field = "flurname"


def load_shapefile(file_path):
    return gpd.read_file(file_path)


parcel = load_shapefile(parcel_shapefile)
flur = load_shapefile(flur_shapefile)

# Filter parcels that are in the parcel_list and intersect with a negatively buffered version of flurs in the flur_list
buffered_flur = flur[flur[flur_label_field].isin(
    flur_list)].unary_union.buffer(-10)
target_parcels = parcel[(parcel[parcel_label_field].isin(parcel_list)) &
                        (parcel.intersects(buffered_flur))]
# print the parcel_label_field
print(target_parcels[parcel_label_field])

# use matplotlib to plot the parcels
print(plot)


# Create a single polygon that contains all target parcels
geltungsbereich_geom = target_parcels['geometry'].unary_union
# plot geltungsbereich_geom
# if isinstance(geltungsbereich_geom, (Polygon, MultiPolygon)):
#     gpd.GeoSeries([geltungsbereich_geom]).plot()
#     plt.show()


def conditional_buffer(flur_geom):
    if any(flur_geom.intersects(parcel_geom) for parcel_geom in target_parcels['geometry']):
        # Apply negative buffer if flur overlaps any target parcel
        return flur_geom.buffer(-2)
    else:
        return flur_geom.buffer(2)  # Otherwise, apply positive buffer


# Apply conditional buffering to each flur polygon
flur['geometry'] = flur['geometry'].apply(conditional_buffer)

# Create a new DXF document
doc = ezdxf.new('R2010', setup=True)
msp = doc.modelspace()

# Define layers
doc.layers.new(name='Flur', dxfattribs={'color': 2})
doc.layers.new(name='Parcel', dxfattribs={'color': 3})
doc.layers.new(name='Geltungsbereich', dxfattribs={
               'color': 4})  # New layer for Geltungsbereich

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

# Add Geltungsbereich geometry to the DXF
if geltungsbereich_geom.geom_type in ['Polygon', 'MultiPolygon']:
    if geltungsbereich_geom.geom_type == 'Polygon':
        points = [(x, y) for x, y in geltungsbereich_geom.exterior.coords]
        msp.add_lwpolyline(points, close=True, dxfattribs={
                           'layer': 'Geltungsbereich'})
    elif geltungsbereich_geom.geom_type == 'MultiPolygon':
        for polygon in geltungsbereich_geom.geoms:
            points = [(x, y) for x, y in polygon.exterior.coords]
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               'layer': 'Geltungsbereich'})

# Save the DXF file
dxf_filename = "/Users/guntherschulz/IONOS HiDrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/Zeichnung/combined.dxf"
doc.saveas(dxf_filename)
