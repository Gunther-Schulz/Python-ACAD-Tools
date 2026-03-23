"""Generate synthetic shapefiles for the Test project."""
import geopandas as gpd
from shapely.geometry import Polygon, LineString, box
import os

output_dir = os.path.join(os.path.dirname(__file__), 'input')
os.makedirs(output_dir, exist_ok=True)
crs = "EPSG:25833"

# Parcels: 3 rectangles side by side
parcels = gpd.GeoDataFrame({
    'label': ['1', '2', '3'],
    'geometry': [
        box(0, 0, 100, 200),
        box(100, 0, 200, 200),
        box(200, 0, 300, 200),
    ]
}, crs=crs)
parcels.to_file(os.path.join(output_dir, 'parcels.shp'))

# Forest: a polygon overlapping parcels 2 and 3
forest = gpd.GeoDataFrame({
    'geometry': [box(180, 150, 280, 220)]
}, crs=crs)
forest.to_file(os.path.join(output_dir, 'forest.shp'))

# Utility line crossing all parcels
utility = gpd.GeoDataFrame({
    'geometry': [LineString([(10, 100), (290, 100)])]
}, crs=crs)
utility.to_file(os.path.join(output_dir, 'utility_line.shp'))

# Exclude zone: small polygon in parcel 1
exclude = gpd.GeoDataFrame({
    'geometry': [box(20, 20, 50, 50)]
}, crs=crs)
exclude.to_file(os.path.join(output_dir, 'exclude.shp'))

print(f"Created test shapefiles in {output_dir}")
