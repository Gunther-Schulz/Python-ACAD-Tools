#!/usr/bin/env python3
"""
Verification script for debug boundary processing.
Compares original polygon boundaries vs processed cleaned boundaries.
"""

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point
import sys

def verify_layer(layer_name, shapefile_dir):
    """Verify one layer - compare original vs processed"""
    
    print(f"\n{'='*60}")
    print(f"Verifying: {layer_name}")
    print('='*60)
    
    # Load shapefiles
    try:
        original = gpd.read_file(f'{shapefile_dir}/{layer_name} Original.shp')
        processed = gpd.read_file(f'{shapefile_dir}/{layer_name}.shp')
    except Exception as e:
        print(f"ERROR loading shapefiles: {e}")
        return False
    
    print(f"Original: {len(original)} polygons")
    print(f"Processed: {len(processed)} lines")
    
    # Extract boundaries from originals
    orig_lines = []
    for geom in original.geometry:
        if geom.geom_type == 'Polygon':
            orig_lines.append(LineString(geom.exterior.coords))
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                orig_lines.append(LineString(poly.exterior.coords))
    
    print(f"Original boundaries: {len(orig_lines)} complete lines")
    
    # Calculate total lengths
    orig_total = sum(line.length for line in orig_lines)
    proc_total = sum(line.length for line in processed.geometry if line.geom_type == 'LineString')
    
    print(f"\nLength comparison:")
    print(f"  Original total: {orig_total:.2f}m")
    print(f"  Processed total: {proc_total:.2f}m")
    diff = orig_total - proc_total
    diff_pct = 100 * diff / orig_total if orig_total > 0 else 0
    print(f"  Difference: {diff:.2f}m ({diff_pct:.1f}%)")
    
    # Check if data is lost (allow 1% tolerance for rounding)
    if diff_pct > 1.0:
        print(f"\n❌ FAIL: {diff_pct:.1f}% of boundary data is LOST!")
        
        # Try to identify which parts are missing
        print("\nDiagnostics:")
        
        # Create a buffer union of all processed lines
        proc_union = processed.geometry.unary_union.buffer(0.1)  # 10cm buffer
        
        # Check which original lines are NOT covered by processed
        missing_count = 0
        missing_length = 0
        for orig_line in orig_lines:
            # Sample points along the line
            sample_points = [orig_line.interpolate(i/10.0, normalized=True) 
                           for i in range(11)]
            
            # Check if all sample points are covered
            covered = sum(1 for pt in sample_points if proc_union.contains(pt))
            coverage = covered / len(sample_points)
            
            if coverage < 0.8:  # Less than 80% covered
                missing_count += 1
                missing_length += orig_line.length
        
        if missing_count > 0:
            print(f"  - {missing_count} original lines have missing segments")
            print(f"  - Total missing length: {missing_length:.2f}m")
        
        return False
    else:
        print(f"\n✅ PASS: All boundary data preserved (within {diff_pct:.2f}% tolerance)")
        return True

def main():
    shapefile_dir = '/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/23-24 Maxsolar - Plasten/GIS/debug'
    
    print("\n" + "="*60)
    print("DEBUG BOUNDARY PROCESSING VERIFICATION")
    print("="*60)
    
    layers = ['Gemeinde', 'Gemarkung', 'Flur']
    
    results = {}
    for layer in layers:
        results[layer] = verify_layer(layer, shapefile_dir)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_pass = all(results.values())
    for layer, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{layer:15s} {status}")
    
    print("="*60)
    
    if all_pass:
        print("\n🎉 ALL TESTS PASSED! Boundary processing is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  SOME TESTS FAILED! Data is being lost during processing.")
        sys.exit(1)

if __name__ == '__main__':
    main()

