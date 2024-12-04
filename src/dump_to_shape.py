import argparse
import os
import ezdxf
import shapefile
from ezdxf.entities import LWPolyline, Polyline
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
import pyproj
import re
import yaml
from src.utils import resolve_path, ensure_path_exists, log_warning, log_error, log_debug, log_info

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
    log_info("CRS not found in DXF file. Using default EPSG:25833 (ETRS89 / UTM zone 33N).")
    return pyproj.CRS.from_epsg(25833), "Default EPSG:25833 (ETRS89 / UTM zone 33N) used"

def write_prj_file(output_path, crs):
    prj_path = output_path.replace('.shp', '.prj')
    
    # Use a known, valid WKT string for EPSG:25833
    wkt = 'PROJCS["ETRS89 / UTM zone 33N",GEOGCS["ETRS89",DATUM["European_Terrestrial_Reference_System_1989",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],TOWGS84[0,0,0,0,0,0,0],AUTHORITY["EPSG","6258"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4258"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",15],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","25833"]]'

    with open(prj_path, 'w') as prj_file:
        prj_file.write(wkt)

def merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities, crs):
    points = []
    lines = []
    polygons = []

    log_info(f"Processing DXF layer to shapefile {layer_name}")
    
    for entity in entities:
        log_debug(f"Processing entity: {entity}")
        if isinstance(entity, (LWPolyline, Polyline)):
            points_list = list(entity.vertices())
            log_debug(f"Entity vertices: {points_list}")
            if len(points_list) >= 2:
                # Always treat as polygon if entity has closed property set to True
                if hasattr(entity, 'closed') and entity.closed and len(points_list) >= 3:
                    try:
                        # Ensure the polygon is closed by adding first point if needed
                        if points_list[0] != points_list[-1]:
                            points_list.append(points_list[0])
                        poly = Polygon(points_list)
                        log_debug(f"Created polygon: {poly}")
                        if poly.is_valid and not poly.is_empty:
                            polygons.append(poly)
                    except Exception as e:
                        log_warning(f"Invalid polygon in layer {layer_name}: {e}")
                else:
                    try:
                        line = LineString(points_list)
                        log_debug(f"Created line: {line}")
                        if line.is_valid and not line.is_empty and line.length > 0:
                            lines.append(line)
                    except Exception as e:
                        log_warning(f"Invalid line in layer {layer_name}: {e}")
        elif isinstance(entity, (ezdxf.entities.Point)):
            try:
                point = Point(entity.dxf.location[:2])
                log_debug(f"Created point: {point}")
                if point.is_valid and not point.is_empty:
                    points.append(point)
            except Exception as e:
                log_warning(f"Invalid point in layer {layer_name}: {e}")

    log_debug(f"Total valid points: {len(points)}, lines: {len(lines)}, polygons: {len(polygons)}")

    # Add warning if no valid geometries found
    if not points and not lines and not polygons:
        log_warning(f"No valid geometries found in layer {layer_name}. No shapefile will be created.")

    # Create appropriate shapefile based on geometry type, only if we have valid geometries
    if points:
        valid_points = [p for p in points if p.is_valid and not p.is_empty]
        log_debug(f"Valid points: {valid_points}")
        if valid_points:
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POINT) as shp:
                shp.field('Layer', 'C', 40)
                for point in valid_points:
                    shp.point(point.x, point.y)
                    shp.record(Layer=layer_name)
            write_prj_file(shp_path, crs)
        else:
            log_warning(f"No valid points found in layer {layer_name}")
        
    if lines:
        valid_lines = [l for l in lines if l.is_valid and not l.is_empty and l.length > 0]
        log_debug(f"Valid lines: {valid_lines}")
        if valid_lines:
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POLYLINE) as shp:
                shp.field('Layer', 'C', 40)
                for line in valid_lines:
                    shp.line([list(line.coords)])
                    shp.record(Layer=layer_name)
            write_prj_file(shp_path, crs)
        else:
            log_warning(f"No valid lines found in layer {layer_name}")

    if polygons:
        valid_polygons = [p for p in polygons if p.is_valid and not p.is_empty and p.area > 0]
        log_debug(f"Valid polygons: {valid_polygons}")
        if valid_polygons:
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POLYGON) as shp:
                shp.field('Layer', 'C', 40)
                for poly in valid_polygons:
                    if poly.is_valid and not poly.is_empty and poly.area > 0:
                        shp.poly([list(poly.exterior.coords)] + [list(interior.coords) for interior in poly.interiors])
                        shp.record(Layer=layer_name)
            write_prj_file(shp_path, crs)
        else:
            log_warning(f"No valid polygons found in layer {layer_name}")

    log_info(f"Finished processing DXF layer to shapefile {layer_name}")

def dxf_to_shapefiles(dxf_path, output_folder):
    # Clear the contents of the output folder
    if os.path.exists(output_folder):
        for filename in os.listdir(output_folder):
            file_path = os.path.join(output_folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    os.rmdir(file_path)
            except Exception as e:
                log_info(f'Failed to delete {file_path}. Reason: {e}')
    else:
        os.makedirs(output_folder)

    crs, crs_source = get_crs_from_dxf(dxf_path)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    layers = doc.layers

    error_summary = {}

    for layer in layers:
        layer_name = layer.dxf.name
        entities = msp.query(f'*[layer=="{layer_name}"]')
        
        polygons = []
        for entity in entities:
            if isinstance(entity, (LWPolyline, Polyline)):
                points = list(entity.vertices())
                if len(points) >= 3:
                    if points[0] != points[-1]:
                        points.append(points[0])
                    polygons.append(points)

        if polygons:
            largest_polygon = max(polygons, key=polygon_area)
            largest_polygon_shape = Polygon(largest_polygon)

            holes = [Polygon(poly) for poly in polygons if poly != largest_polygon and Polygon(poly).within(largest_polygon_shape)]
            error_count = 0
            for hole in holes:
                try:
                    largest_polygon_shape = largest_polygon_shape.difference(hole)
                except Exception:
                    error_count += 1

            if error_count > 0:
                error_summary[layer_name] = error_count

            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POLYGON) as shp:
                shp.field('Layer', 'C', 40)
                shp.poly([list(largest_polygon_shape.exterior.coords)] + [list(interior.coords) for interior in largest_polygon_shape.interiors])
                shp.record(Layer=layer_name)

            write_prj_file(shp_path, crs)

            merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities, crs)

    if error_summary:
        log_info("\nError Summary:")
        for layer, count in error_summary.items():
            log_info(f"  Layer '{layer}': {count} errors while processing holes")
        log_info("These errors are typically due to invalid geometries or topology conflicts")

    log_info(f"\nCRS being used: {crs}")
    log_info(f"CRS source: {crs_source}")

def load_project_config(project_name):
    project_file = os.path.join('projects', f'{project_name}.yaml')
    if not os.path.exists(project_file):
        return None
        
    with open(project_file, 'r') as file:
        return yaml.safe_load(file)

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
            dxf_filename = resolve_path(project_config.get('dxfFilename', ''), folder_prefix)
            dump_output_dir = resolve_path(project_config.get('dxfDumpOutputDir', ''), folder_prefix)
            
            if not os.path.exists(dxf_filename):
                log_error(f"DXF file not found: {dxf_filename}")
                return
                
            if not ensure_path_exists(dump_output_dir):
                log_warning(f"Dump output directory does not exist: {dump_output_dir}")
                return
                
            dxf_to_shapefiles(dxf_filename, dump_output_dir)
        else:
            log_info(f"Error: Project '{args.project_name}' not found in projects.yaml")
    elif args.dxf_file and args.output_folder:
        dxf_to_shapefiles(args.dxf_file, args.output_folder)
    else:
        log_info("Error: Please provide either a project name or both DXF file and output folder.")

if __name__ == "__main__":
    main()