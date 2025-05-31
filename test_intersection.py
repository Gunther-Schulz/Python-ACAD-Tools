import geopandas as gpd

# Load both layers
geltung = gpd.read_file('/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/GIS/generated/Geltungsbereich.shp')
graben = gpd.read_file('/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/GIS/input/Graben_edit.shp')

print('=== INTERSECTION TEST ===')
print(f'Geltungsbereich bounds: {geltung.total_bounds}')
print(f'Graben bounds: {graben.total_bounds}')

# Check distance between geometries
from shapely.geometry import box
geltung_box = box(*geltung.total_bounds)
graben_box = box(*graben.total_bounds)
distance = geltung_box.distance(graben_box)
print(f'Distance between bounding boxes: {distance:.2f} meters')

# Try intersection
try:
    intersection = gpd.overlay(graben, geltung, how='intersection')
    print(f'Intersection result shape: {intersection.shape}')
    print(f'Intersection is empty: {intersection.empty}')
    if not intersection.empty:
        print(f'Intersection area: {intersection.geometry.area.sum():.2f}')
except Exception as e:
    print(f'Intersection failed: {e}')
