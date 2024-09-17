import argparse
import os
import ezdxf
import shapefile
from ezdxf.entities import LWPolyline, Polyline
from shapely.geometry import Polygon, MultiPolygon
import pyproj
import re
import yaml

def polygon_area(polygon):
    """Calculate the area of a polygon."""
    return Polygon(polygon).area

def get_crs_from_dxf(dxf_path):
    # Read the entire DXF file as text
    with open(dxf_path, 'r', errors='ignore') as file:
        dxf_content = file.read()

    # Search for the EPSG code in the entire file content
    match = re.search(r'<Alias id="(\d+)" type="CoordinateSystem">', dxf_content)
    if match:
        epsg = int(match.group(1))
        return pyproj.CRS.from_epsg(epsg), f"EPSG:{epsg} found in DXF file"

    # If not found, return the default EPSG:25833 (ETRS89 / UTM zone 33N)
    print("Warning: CRS not found in DXF file. Using default EPSG:25833 (ETRS89 / UTM zone 33N).")
    return pyproj.CRS.from_epsg(25833), "Default EPSG:25833 (ETRS89 / UTM zone 33N) used"

def write_prj_file(output_path, crs):
    prj_path = output_path.replace('.shp', '.prj')
    
    # Use a known, valid WKT string for EPSG:25833
    wkt = 'PROJCS["ETRS89 / UTM zone 33N",GEOGCS["ETRS89",DATUM["European_Terrestrial_Reference_System_1989",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],TOWGS84[0,0,0,0,0,0,0],AUTHORITY["EPSG","6258"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4258"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",15],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","25833"]]'

    with open(prj_path, 'w') as prj_file:
        prj_file.write(wkt)

def merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities, crs):
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

        # Write the .prj file
        write_prj_file(shp_path, crs)

        print(f"Created merged shapefile for layer: {layer_name}")

def dxf_to_shapefiles(dxf_path, output_folder):
    # Get the CRS from the DXF file
    crs, crs_source = get_crs_from_dxf(dxf_path)
    print(f"CRS being used: {crs}")
    print(f"CRS source: {crs_source}")

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

            # Write the .prj file
            write_prj_file(shp_path, crs)

            print(f"Created shapefile for layer: {layer_name}")

        # Create the merged shapefile for this layer
        merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities, crs)

    # Print CRS information at the end
    print(f"\nCRS being used: {crs}")
    print(f"CRS source: {crs_source}")

def load_project_config(project_name):
    with open('projects.yaml', 'r') as file:
        config = yaml.safe_load(file)
    
    for project in config['projects']:
        if project['name'] == project_name:
            return project
    
    return None

def main():
    parser = argparse.ArgumentParser(description="Convert DXF layers to shapefiles with holes cut out by inner polygons")
    parser.add_argument("--dxf_file", help="Path to the input DXF file")
    parser.add_argument("--output_folder", help="Path to the output folder for shapefiles")
    parser.add_argument("--project_name", help="Name of the project in projects.yaml")
    args = parser.parse_args()

    if args.project_name:
        project_config = load_project_config(args.project_name)
        if project_config:
            folder_prefix = project_config.get('folderPrefix', '')
            dxf_filename = os.path.expanduser(os.path.join(folder_prefix, project_config.get('dxfFilename', '')))
            dump_output_dir = os.path.expanduser(os.path.join(folder_prefix, project_config.get('dumpOutputDir', '')))
            
            if os.path.exists(dxf_filename) and dump_output_dir:
                dxf_to_shapefiles(dxf_filename, dump_output_dir)
            else:
                print("Error: DXF file not found or dump output directory not specified in project configuration.")
        else:
            print(f"Error: Project '{args.project_name}' not found in projects.yaml")
    elif args.dxf_file and args.output_folder:
        dxf_to_shapefiles(args.dxf_file, args.output_folder)
    else:
        print("Error: Please provide either a project name or both DXF file and output folder.")

if __name__ == "__main__":
    main()