import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

# Load both layers
geltung_input = gpd.read_file('/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/GIS/generated/Geltungsbereich Input.shp')
zuwegung = gpd.read_file('/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/GIS/generated/Zuwegung.shp')

print('=== INPUT LAYERS ===')
print(f'Geltungsbereich Input - Shape: {geltung_input.shape}, Area: {geltung_input.geometry.area.sum():.2f}')
print(f'Zuwegung - Shape: {zuwegung.shape}, Area: {zuwegung.geometry.area.sum():.2f}')
print()

# Test manual dissolve
print('=== MANUAL DISSOLVE TEST ===')
combined_gdf = pd.concat([geltung_input, zuwegung], ignore_index=True)
print(f'Combined GDF shape: {combined_gdf.shape}')
print(f'Combined GDF area: {combined_gdf.geometry.area.sum():.2f}')
print(f'Combined bounds: {combined_gdf.total_bounds}')
print()

# Try unary_union
dissolved_geom = unary_union(combined_gdf.geometry)
dissolved = gpd.GeoDataFrame(geometry=[dissolved_geom])
print(f'Dissolved shape: {dissolved.shape}')
print(f'Dissolved area: {dissolved.geometry.area.sum():.2f}')
print(f'Dissolved bounds: {dissolved.total_bounds}')
print(f'Dissolved geom type: {dissolved.geom_type.iloc[0]}')
print()

# Compare with actual generated result
actual_result = gpd.read_file('/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/GIS/generated/Geltungsbereich.shp')
print('=== ACTUAL GENERATED RESULT ===')
print(f'Actual result shape: {actual_result.shape}')
print(f'Actual result area: {actual_result.geometry.area.sum():.2f}')
print(f'Actual result bounds: {actual_result.total_bounds}')

# Check if actual result matches only Zuwegung
zuwegung_area = zuwegung.geometry.area.sum()
actual_area = actual_result.geometry.area.sum()
print(f'Does actual result match Zuwegung area? {abs(actual_area - zuwegung_area) < 1.0}')
print(f'Area difference: {abs(actual_area - zuwegung_area):.2f}')
