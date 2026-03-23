"""Generate synthetic shapefiles for the Test project."""
import geopandas as gpd
from shapely.geometry import Polygon, LineString, box
import os

output_dir = os.path.join(os.path.dirname(__file__), 'input')
os.makedirs(output_dir, exist_ok=True)
crs = "EPSG:25833"

# Parcels: 4 rectangles in a 2x2 grid
parcels = gpd.GeoDataFrame({
    'label': ['1', '2', '3', '4'],
    'geometry': [
        box(0, 0, 150, 150),      # SW
        box(150, 0, 300, 150),     # SE
        box(0, 150, 150, 300),     # NW
        box(150, 150, 300, 300),   # NE
    ]
}, crs=crs)
parcels.to_file(os.path.join(output_dir, 'parcels.shp'))

# Flur: 2 areas covering left and right halves
flur = gpd.GeoDataFrame({
    'flurname': ['Flur 1', 'Flur 2'],
    'geometry': [
        box(-10, -10, 155, 310),   # Left half (parcels 1, 3)
        box(145, -10, 310, 310),   # Right half (parcels 2, 4)
    ]
}, crs=crs)
flur.to_file(os.path.join(output_dir, 'flur.shp'))

# Gemarkung: single area covering everything
gemarkung = gpd.GeoDataFrame({
    'gmkname': ['Testgemarkung'],
    'geometry': [box(-10, -10, 310, 310)]
}, crs=crs)
gemarkung.to_file(os.path.join(output_dir, 'gemarkung.shp'))

# Gemeinde: single area covering everything
gemeinde = gpd.GeoDataFrame({
    'gen': ['Testgemeinde'],
    'geometry': [box(-10, -10, 310, 310)]
}, crs=crs)
gemeinde.to_file(os.path.join(output_dir, 'gemeinde.shp'))

# Forest: a polygon overlapping parcels 3 and 4 (north side)
forest = gpd.GeoDataFrame({
    'geometry': [box(180, 220, 280, 320)]
}, crs=crs)
forest.to_file(os.path.join(output_dir, 'forest.shp'))

# Biotope: small protected area in parcel 1
biotope = gpd.GeoDataFrame({
    'geometry': [box(30, 30, 70, 70)]
}, crs=crs)
biotope.to_file(os.path.join(output_dir, 'biotope.shp'))

# Utility line crossing all parcels horizontally
utility = gpd.GeoDataFrame({
    'geometry': [LineString([(10, 150), (290, 150)])]
}, crs=crs)
utility.to_file(os.path.join(output_dir, 'utility_line.shp'))

# Exclude zone: small polygon in parcel 2
exclude = gpd.GeoDataFrame({
    'geometry': [box(200, 20, 250, 50)]
}, crs=crs)
exclude.to_file(os.path.join(output_dir, 'exclude.shp'))

print(f"Created test shapefiles in {output_dir}")
