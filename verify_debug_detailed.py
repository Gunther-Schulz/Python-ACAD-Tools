#!/usr/bin/env python3
"""
Detailed verification - check length at each processing step
"""

import geopandas as gpd
from shapely.geometry import LineString
import sys

# Add project to path
sys.path.insert(0, '/home/g/dev/Gunther-Schulz/Python-ACAD-Tools')

from src.operations.extract_boundary_operation import create_extract_boundary_layer
from src.operations.break_at_intersections_operation import create_break_at_intersections_layer
from src.operations.remove_duplicate_lines_operation import create_remove_duplicate_lines_layer

def test_pipeline():
    """Test the full pipeline step by step"""
    
    shapefile_dir = '/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/GIS/debug'
    
    # Load original
    orig = gpd.read_file(f'{shapefile_dir}/Gemeinde Original.shp')
    
    print("="*60)
    print("STEP-BY-STEP VERIFICATION: Gemeinde")
    print("="*60)
    
    # Calculate expected length
    expected_length = 0
    for geom in orig.geometry:
        if geom.geom_type == 'Polygon':
            expected_length += geom.exterior.length
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                expected_length += poly.exterior.length
    
    print(f"\n0. Original polygons: {len(orig)}")
    print(f"   Total boundary length: {expected_length:.2f}m")
    
    # Step 1: Extract boundary
    all_layers = {'Gemeinde Original': orig}
    operation1 = {'layers': ['Gemeinde Original']}
    
    step1 = create_extract_boundary_layer(all_layers, {}, orig.crs, 'Test', operation1)
    step1_length = sum(line.length for line in step1.geometry)
    
    print(f"\n1. After extractBoundary: {len(step1)} lines")
    print(f"   Total length: {step1_length:.2f}m")
    print(f"   Difference: {expected_length - step1_length:.2f}m ({100*(expected_length-step1_length)/expected_length:.1f}%)")
    
    # Step 2: Break at intersections
    all_layers['Test'] = step1
    operation2 = {'tolerance': 0.001}
    
    step2 = create_break_at_intersections_layer(all_layers, {}, orig.crs, 'Test', operation2)
    step2_length = sum(line.length for line in step2.geometry)
    
    print(f"\n2. After breakAtIntersections: {len(step2)} lines")
    print(f"   Total length: {step2_length:.2f}m")
    print(f"   Difference: {step1_length - step2_length:.2f}m ({100*(step1_length-step2_length)/step1_length:.1f}%)")
    
    # Step 3: Remove duplicates
    all_layers['Test'] = step2
    operation3 = {'tolerance': 0.01}
    
    step3 = create_remove_duplicate_lines_layer(all_layers, {}, orig.crs, 'Test', operation3)
    step3_length = sum(line.length for line in step3.geometry)
    
    print(f"\n3. After removeDuplicateLines: {len(step3)} lines")
    print(f"   Total length: {step3_length:.2f}m")
    print(f"   Difference: {step2_length - step3_length:.2f}m ({100*(step2_length-step3_length)/step2_length:.1f}%)")
    
    print(f"\n" + "="*60)
    print(f"TOTAL LOSS: {expected_length - step3_length:.2f}m ({100*(expected_length-step3_length)/expected_length:.1f}%)")
    print("="*60)
    
    if abs(expected_length - step3_length) / expected_length > 0.01:
        print("\n❌ FAIL: More than 1% data lost!")
        return False
    else:
        print("\n✅ PASS: Data preserved!")
        return True

if __name__ == '__main__':
    success = test_pipeline()
    sys.exit(0 if success else 1)

