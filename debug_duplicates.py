#!/usr/bin/env python3
"""
Debug which segments are being marked as duplicates
"""

import geopandas as gpd
from shapely.geometry import LineString, Point
import sys

sys.path.insert(0, '/home/g/dev/Gunther-Schulz/Python-ACAD-Tools')

from src.operations.extract_boundary_operation import create_extract_boundary_layer
from src.operations.break_at_intersections_operation import create_break_at_intersections_layer

shapefile_dir = '/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/GIS/debug'

# Load and process
orig = gpd.read_file(f'{shapefile_dir}/Gemeinde Original.shp')
all_layers = {'Gemeinde Original': orig}

# Step 1: Extract
step1 = create_extract_boundary_layer(all_layers, {}, orig.crs, 'Test', {'layers': ['Gemeinde Original']})

# Step 2: Break
all_layers['Test'] = step1
step2 = create_break_at_intersections_layer(all_layers, {}, orig.crs, 'Test', {'tolerance': 0.001})

print(f"After breaking: {len(step2)} segments")
print()

# Now manually check for duplicates
tolerance = 0.01
segments = list(step2.geometry)

print("Segment lengths:")
for i, seg in enumerate(segments):
    print(f"  {i:2d}: {seg.length:10.1f}m")

print()
print("Checking for duplicates (length ratio > 0.999, endpoints within 1m):")

duplicates = []
for i in range(len(segments)):
    for j in range(i+1, len(segments)):
        line1, line2 = segments[i], segments[j]
        
        # Length check
        length_ratio = min(line1.length, line2.length) / max(line1.length, line2.length)
        if length_ratio < 0.999:
            continue
        
        # Endpoints check
        coords1 = list(line1.coords)
        coords2 = list(line2.coords)
        
        if len(coords1) < 2 or len(coords2) < 2:
            continue
        
        start1, end1 = Point(coords1[0]), Point(coords1[-1])
        start2, end2 = Point(coords2[0]), Point(coords2[-1])
        
        same_dir = (start1.distance(start2) < 1.0 and end1.distance(end2) < 1.0)
        opp_dir = (start1.distance(end2) < 1.0 and end1.distance(start2) < 1.0)
        
        if same_dir or opp_dir:
            hausdorff = line1.hausdorff_distance(line2)
            if hausdorff < 1.0:
                direction = "same" if same_dir else "opposite"
                duplicates.append((i, j, line1.length, line2.length, hausdorff, direction))
                print(f"  {i:2d} <-> {j:2d}: {line1.length:8.1f}m vs {line2.length:8.1f}m, hausdorff={hausdorff:.3f}m ({direction})")

print()
print(f"Found {len(duplicates)} duplicate pairs")
print(f"Total length to remove: {sum(d[3] for d in duplicates):.1f}m")

