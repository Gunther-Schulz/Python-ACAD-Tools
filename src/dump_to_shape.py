import argparse
import os
import ezdxf
import shapefile
from ezdxf.entities import LWPolyline, Polyline
from shapely.geometry import Polygon, MultiPolygon

def is_clockwise(points):
    # Calculate the signed area
    area = sum((p2[0] - p1[0]) * (p2[1] + p1[1]) for p1, p2 in zip(points, points[1:] + [points[0]])) / 2
    return area > 0

def polygon_area(points):
    return abs(sum(x0*y1 - x1*y0 for ((x0, y0), (x1, y1)) in zip(points, points[1:] + [points[0]])) / 2)

def merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities):
    polygons = []
    for entity in entities:
        if isinstance(entity, (LWPolyline, Polyline)):
            points = list(entity.vertices())
            if len(points) >= 3:  # Ensure it's a valid polygon
                # Ensure the polygon is closed
                if points[0] != points[-1]:
                    points.append(points[0])
                polygons.append(Polygon(points))

    if polygons:
        # Merge all polygons into a MultiPolygon
        merged_polygons = MultiPolygon(polygons)

        # Create a shapefile for the merged result
        shp_path = os.path.join(output_folder, f"{layer_name}_merged.shp")
        with shapefile.Writer(shp_path, shapeType=shapefile.POLYGON) as shp:
            shp.field('Layer', 'C', 40)
            
            # Add each polygon separately
            for poly in merged_polygons.geoms:  # Use .geoms to iterate over individual polygons
                shp.poly([list(poly.exterior.coords)] + [list(interior.coords) for interior in poly.interiors])
                shp.record(Layer=layer_name)

        print(f"Created merged shapefile for layer: {layer_name}")

def dxf_to_shapefiles(dxf_path, output_folder):
    # Read the DXF file
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Get all layers in the DXF file
    layers = doc.layers

    for layer in layers:
        layer_name = layer.dxf.name
        entities = msp.query(f'*[layer=="{layer_name}"]')
        
        polygons = []
        for entity in entities:
            if isinstance(entity, (LWPolyline, Polyline)):
                points = list(entity.vertices())
                if len(points) >= 3:  # Ensure it's a valid polygon
                    # Ensure the polygon is closed
                    if points[0] != points[-1]:
                        points.append(points[0])
                    polygons.append(points)

        if polygons:
            # Find the largest polygon (assumed to be the outer ring)
            largest_polygon = max(polygons, key=polygon_area)
            largest_polygon_shape = Polygon(largest_polygon)

            # Use smaller polygons as holes
            holes = [Polygon(poly) for poly in polygons if poly != largest_polygon and Polygon(poly).within(largest_polygon_shape)]
            for hole in holes:
                largest_polygon_shape = largest_polygon_shape.difference(hole)

            # Create a shapefile for the layer
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POLYGON) as shp:
                shp.field('Layer', 'C', 40)
                
                # Add the largest polygon with holes
                shp.poly([list(largest_polygon_shape.exterior.coords)] + [list(interior.coords) for interior in largest_polygon_shape.interiors])
                shp.record(Layer=layer_name)

            print(f"Created shapefile for layer: {layer_name}")

            # Also create the merged shapefile for this layer
            merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities)

def main():
    parser = argparse.ArgumentParser(description="Convert DXF layers to shapefiles with holes cut out by inner polygons")
    parser.add_argument("dxf_file", help="Path to the input DXF file")
    parser.add_argument("output_folder", help="Path to the output folder for shapefiles")
    args = parser.parse_args()

    dxf_to_shapefiles(args.dxf_file, args.output_folder)

if __name__ == "__main__":
    main()