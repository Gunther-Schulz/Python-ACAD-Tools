import os
import sys
import yaml
import geopandas as gpd
import ezdxf
from shapely.ops import unary_union
from wmts_downloader import download_wmts_tiles
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
import random
from ezdxf.addons import odafc
import argparse
import colorama
import logging
import pyproj
from pyproj import CRS

# Setup logging
def setup_logging():
    logging.basicConfig(filename='convert.log', filemode='w', level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

def log_info(*messages):
    logging.info(' '.join(str(msg) for msg in messages))

def log_warning(message):
    logging.warning(f"\033[93mWarning: {message}\033[0m")

def log_error(message):
    logging.error(f"\033[91mError: {message}\033[0m")

# PROJ setup
def setup_proj():
    if 'PROJ_DATA' in os.environ:
        log_info(f"Unsetting PROJ_DATA (was set to: {os.environ['PROJ_DATA']})")
        del os.environ['PROJ_DATA']

    proj_data_dirs = [
        '/usr/share/proj',
        '/usr/local/share/proj',
        '/opt/homebrew/share/proj',
        'C:\\Program Files\\PROJ\\share',
        os.path.join(sys.prefix, 'share', 'proj'),
    ]

    for directory in proj_data_dirs:
        if os.path.exists(os.path.join(directory, 'proj.db')):
            os.environ['PROJ_LIB'] = directory
            log_info(f"Set PROJ_LIB to: {directory}")
            break
    else:
        log_warning("Could not find proj.db in any of the standard locations.")

    os.environ['PROJ_NETWORK'] = 'OFF'
    log_info("Set PROJ_NETWORK to OFF")

    pyproj.datadir.set_data_dir(os.environ['PROJ_LIB'])
    log_info(f"PyProj data directory: {pyproj.datadir.get_data_dir()}")
    log_info(f"PyProj version: {pyproj.__version__}")

    try:
        crs = CRS("EPSG:4326")
        log_info(f"Successfully created CRS object: {crs}")
    except Exception as e:
        log_error(f"Error creating CRS object: {str(e)}")

    try:
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        result = transformer.transform(0, 0)
        log_info(f"Successfully performed transformation: {result}")
    except Exception as e:
        log_error(f"Error performing transformation: {str(e)}")

    try:
        proj_version = pyproj.__proj_version__
        log_info(f"PROJ version (from pyproj): {proj_version}")
    except Exception as e:
        log_error(f"Error getting PROJ version: {str(e)}")

class ProjectProcessor:
    def __init__(self, project_name: str, update_layers_list: list = None):
        self.load_project_settings(project_name)
        self.load_color_mapping()  # Add this line
        self.setup_layers()
        self.update_layers_list = update_layers_list
        self.all_layers = {}

    def load_color_mapping(self):
        with open('colors.yaml', 'r') as file:
            color_data = yaml.safe_load(file)
            self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
            self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}

    def load_project_settings(self, project_name: str):
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            projects = data['projects']
            self.folder_prefix = data.get('folderPrefix', '')
            self.log_file = data.get('logFile', './log.txt')
            self.project_settings = next((project for project in projects if project['name'] == project_name), None)
            if not self.project_settings:
                raise ValueError(f"Project {project_name} not found.")

        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(self.project_settings['dxfFilename'])
        self.wmts = self.project_settings.get('wmts', [])
        self.exclusions = self.project_settings.get('exclusions', [])
        self.clip_distance_layers = self.project_settings.get('clipDistanceLayers', [])
        self.buffer_distance_layers = self.project_settings.get('bufferDistanceLayers', [])
        self.geltungsbereich_layers = self.project_settings.get('geltungsbereichLayers', [])
        self.offset_layers = self.project_settings.get('offsetLayers', [])
        self.inner_buffer_layers = self.project_settings.get('innerBufferLayers', [])
        self.template_dxf = self.resolve_full_path(self.project_settings.get('template', '')) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')

    def setup_layers(self):
        self.layer_properties = {}
        self.colors = {}

        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)
            color_code = self.get_color_code(layer['color'])
            self.colors[layer['name']] = color_code
            self.colors[f"{layer['name']} Number"] = color_code

        for buffer_layer in self.buffer_distance_layers:
            layer_name = buffer_layer['name']
            if layer_name not in self.layer_properties:
                self.add_layer_properties(layer_name, {
                    'color': "Light Green",
                    'close': True,
                    'locked': False
                })

        for wmts in self.wmts:
            layer_name = wmts['dxfLayer']
            if layer_name not in self.layer_properties:
                self.add_layer_properties(layer_name, {
                    'color': "White",
                    'locked': wmts.get('locked', False)
                    })
    def load_shapefile(self, file_path):
        try:
            gdf = gpd.read_file(file_path)
            gdf = self.standardize_layer_crs(file_path, gdf)
            return gdf
        except Exception as e:
            log_warning(f"Failed to load shapefile: {file_path}. Error: {str(e)}")
            return None

    def setup_shapefiles(self):
        for layer in self.project_settings['dxfLayers']:
            if 'shapeFile' in layer:
                layer_name = layer['name']
                shapefile_path = self.resolve_full_path(layer['shapeFile'])
                try:
                    gdf = gpd.read_file(shapefile_path)
                    gdf = self.standardize_layer_crs(layer_name, gdf)
                    if gdf is not None:
                        self.all_layers[layer_name] = gdf
                        log_info(f"Loaded shapefile for layer: {layer_name}")
                    else:
                        log_warning(f"Failed to load shapefile for layer: {layer_name}")
                except Exception as e:
                    log_warning(f"Failed to load shapefile for layer '{layer_name}': {str(e)}")

    def resolve_full_path(self, path: str) -> str:
        return os.path.abspath(os.path.expanduser(os.path.join(self.folder_prefix, path)))

    def load_shapefiles(self):
        for layer in self.project_settings['dxfLayers']:
            if 'shapeFile' in layer:
                self.load_shapefile(layer['name'], layer['shapeFile'])

    def standardize_layer_crs(self, layer_name, geometry_or_gdf):
        target_crs = self.crs
        log_info(f"Standardizing CRS for layer: {layer_name}")

        if isinstance(geometry_or_gdf, gpd.GeoDataFrame):
            log_info(f"Original CRS: {geometry_or_gdf.crs}")
            if geometry_or_gdf.crs is None:
                log_warning(f"Layer {layer_name} has no CRS. Setting to target CRS: {target_crs}")
                geometry_or_gdf.set_crs(target_crs, inplace=True)
            elif geometry_or_gdf.crs != target_crs:
                log_info(f"Transforming layer {layer_name} from {geometry_or_gdf.crs} to {target_crs}")
                geometry_or_gdf = geometry_or_gdf.to_crs(target_crs)
            log_info(f"Final CRS for layer {layer_name}: {geometry_or_gdf.crs}")
            return geometry_or_gdf
        elif isinstance(geometry_or_gdf, gpd.GeoSeries):
            return self.standardize_layer_crs(layer_name, gpd.GeoDataFrame(geometry=geometry_or_gdf))
        elif isinstance(geometry_or_gdf, (Polygon, MultiPolygon, LineString, MultiLineString)):
            log_info(f"Processing individual geometry for layer: {layer_name}")
            gdf = gpd.GeoDataFrame(geometry=[geometry_or_gdf], crs=target_crs)
            log_info(f"Created GeoDataFrame with CRS: {gdf.crs}")
            return gdf.geometry.iloc[0]
        else:
            log_warning(f"Unsupported type for layer {layer_name}: {type(geometry_or_gdf)}")
            return geometry_or_gdf

    def get_color_code(self, color):
        if isinstance(color, int):
            if 1 <= color <= 255:
                return color
            else:
                random_color = random.randint(1, 255)
                log_warning(f"Warning: Invalid color code {color}. Assigning random color: {random_color}")
                return random_color
        elif isinstance(color, str):
            color_lower = color.lower()
            if color_lower in self.name_to_aci:
                return self.name_to_aci[color_lower]
            else:
                random_color = random.randint(1, 255)
                log_warning(f"Warning: Color name '{color}' not found. Assigning random color: {random_color}")
                return random_color
        else:
            random_color = random.randint(1, 255)
            log_warning(f"Warning: Invalid color type. Assigning random color: {random_color}")
            return random_color

    def add_layer_properties(self, layer_name, layer_info):
        color = self.get_color_code(layer_info.get('color', 'White'))
        self.layer_properties[layer_name] = {
            'color': color,
            'locked': layer_info.get('locked', False),
            'close': layer_info.get('close', True)
        }
        
        text_layer_name = f"{layer_name} Number"
        self.layer_properties[text_layer_name] = {
            'color': color,
            'locked': layer_info.get('locked', False),
            'close': True
        }

    def create_geltungsbereich_layer(self, layer_name, operation):
        log_info(f"Creating Geltungsbereich layer: {layer_name}")
        combined_geometry = None

        for coverage in operation['coverages']:
            coverage_geometry = None
            for layer in coverage['layers']:
                source_layer_name = layer['name']
                value_list = layer['valueList']

                if source_layer_name not in self.all_layers:
                    log_warning(f"Source layer '{source_layer_name}' not found for Geltungsbereich")
                    continue

                source_gdf = self.all_layers[source_layer_name]
                
                label_column = next((l['label'] for l in self.project_settings['dxfLayers'] if l['name'] == source_layer_name), None)
                
                if label_column is None or label_column not in source_gdf.columns:
                    log_warning(f"Label column '{label_column}' not found in layer '{source_layer_name}'")
                    continue

                filtered_gdf = source_gdf[source_gdf[label_column].isin(value_list)]

                if coverage_geometry is None:
                    coverage_geometry = filtered_gdf.geometry.unary_union
                else:
                    coverage_geometry = coverage_geometry.intersection(filtered_gdf.geometry.unary_union)

            if coverage_geometry:
                if combined_geometry is None:
                    combined_geometry = coverage_geometry
                else:
                    combined_geometry = combined_geometry.union(coverage_geometry)

        if combined_geometry:
            if 'clipLayers' in operation:
                for clip_layer in operation['clipLayers']:
                    clip_layer_name = clip_layer['name']
                    if clip_layer_name in self.all_layers:
                        clip_geometry = self.all_layers[clip_layer_name].geometry.unary_union
                        combined_geometry = combined_geometry.difference(clip_geometry)
                    else:
                        log_warning(f"Clip layer '{clip_layer_name}' not found for Geltungsbereich")

            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[combined_geometry], crs=self.crs)
            log_info(f"Created Geltungsbereich layer: {layer_name}")
        else:
            log_warning(f"No geometry created for Geltungsbereich layer: {layer_name}")


    def create_clip_distance_layers(self, layer_name):
        log_info(f"Creating clip distance layer: {layer_name}")
        layer = next((l for l in self.clip_distance_layers if l['name'] == layer_name), None)
        if layer:
            buffer_distance = layer['bufferDistance']
            source_layer = layer['sourceLayer']
            if source_layer in self.all_layers:
                original_geometry = self.all_layers[source_layer]
                if buffer_distance > 0:
                    clipped = original_geometry.buffer(buffer_distance, join_style=2)
                else:
                    clipped = original_geometry
                self.all_layers[layer_name] = clipped
                log_info(f"Created clip distance layer: {layer_name}")
            else:
                log_warning(f"Warning: Source layer '{source_layer}' not found in all_layers for clip distance layer '{layer_name}'")
        else:
            log_warning(f"Warning: Clip distance layer '{layer_name}' not found in configuration")
            
    def create_buffer_layer(self, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layer = operation['sourceLayer']
        buffer_distance = operation['distance']
        buffer_mode = operation.get('mode', 'both')  # Default to 'both' if not specified

        if source_layer in self.all_layers:
            original_geometry = self.all_layers[source_layer]
            
            if buffer_mode == 'outer':
                buffered = original_geometry.buffer(buffer_distance, join_style=2)
                result = buffered.difference(original_geometry)
            elif buffer_mode == 'inner':
                result = original_geometry.buffer(-buffer_distance, join_style=2)
            else:  # 'both'
                result = original_geometry.buffer(buffer_distance, join_style=2)

            self.all_layers[layer_name] = result
            log_info(f"Created buffer layer: {layer_name}")
        else:
            log_warning(f"Warning: Source layer '{source_layer}' not found for buffer layer '{layer_name}'")


    def create_offset_layers(self, layers_to_offset):
        log_info("Starting to create offset layers...")
        for layer in layers_to_offset:
            layer_to_offset = layer['layerToOffset']
            offset_distance = layer['offsetDistance']
            layer_name = layer['name']

            if layer_to_offset in self.all_layers:
                log_info(f"Processing offset layer: {layer_name}")
                original_geometry = self.all_layers[layer_to_offset]
                offset_geometry = original_geometry.buffer(offset_distance, join_style=2).difference(original_geometry)
                self.all_layers[layer_name] = offset_geometry
                log_info(f"Created offset layer: {layer_name}")
            else:
                log_warning(f"Warning: Layer to offset '{layer_to_offset}' not found in all_layers for offset layer '{layer_name}'")

        log_info("Finished creating offset layers.")

    def create_inner_buffer_layers(self):
        log_info("Starting to create inner buffer layers...")
        for layer in self.inner_buffer_layers:
            layer_to_buffer = layer['layerToBuffer']
            buffer_distance = layer['bufferDistance']
            layer_name = layer['name']

            if layer_to_buffer in self.all_layers:
                log_info(f"Processing inner buffer layer: {layer_name}")
                original_geometry = self.all_layers[layer_to_buffer]
                inner_buffer_geometry = original_geometry.buffer(-buffer_distance, join_style=2)
                self.all_layers[layer_name] = inner_buffer_geometry
                log_info(f"Created inner buffer layer: {layer_name}")
            else:
                log_warning(f"Warning: Layer to buffer '{layer_to_buffer}' not found for inner buffer layer '{layer_name}'")

        log_info("Finished creating inner buffer layers.")

    def create_exclusion_layers(self):
        log_info("Starting to create exclusion layers...")
        for exclusion in self.exclusions:
            layer_name = exclusion['name']
            scope_layer = exclusion['scopeLayer']
            exclude_layers = exclusion['excludeLayers']

            if scope_layer in self.all_layers:
                log_info(f"Processing exclusion layer: {layer_name}")
                scope_geometry = self.all_layers[scope_layer]
                excluded_geometry = scope_geometry

                for exclude_layer in exclude_layers:
                    if exclude_layer in self.all_layers:
                        excluded_geometry = excluded_geometry.difference(self.all_layers[exclude_layer])
                    else:
                        log_warning(f"Warning: Exclude layer '{exclude_layer}' not found for exclusion layer '{layer_name}'")

                self.all_layers[layer_name] = excluded_geometry
                log_info(f"Created exclusion layer: {layer_name}")
            else:
                log_warning(f"Warning: Scope layer '{scope_layer}' not found for exclusion layer '{layer_name}'")

        log_info("Finished creating exclusion layers.")

    def process_layers(self):
        log_info("Starting to process layers...")
        
        # Step 1: Load all shapefiles
        self.setup_shapefiles()

        # Step 2: Process all layers in order
        for layer in self.project_settings['dxfLayers']:
            layer_name = layer['name']
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

            log_info(f"Processing layer: {layer_name}")
            if 'operation' in layer:
                operation = layer['operation']
                op_type = operation['type']

                if op_type == 'buffer':
                    self.create_buffer_layer(layer_name, operation)
                elif op_type == 'clip':
                    self.clip_distance_layers.append({
                        'name': layer_name,
                        'sourceLayer': operation['sourceLayer'],
                        'bufferDistance': operation['distance']
                    })
                    self.create_clip_distance_layers(layer_name)
                elif op_type == 'geltungsbereich':
                    self.create_geltungsbereich_layer(layer_name, operation)
                elif op_type == 'exclusion':
                    self.create_exclusion_layers()
                elif op_type == 'innerBuffer':
                    self.create_inner_buffer_layers()
                else:
                    log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
            elif layer_name not in self.all_layers:
                log_warning(f"Layer {layer_name} not found and has no operation defined.")

        log_info("Finished processing layers.")

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()

        for layer_name, gdf in self.all_layers.items():
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

            layer_properties = self.layer_properties.get(layer_name, {})
            color = layer_properties.get('color', 7)  # Default to white if color not specified
            linetype = 'CONTINUOUS'
            
            # Create the layer
            layer = doc.layers.new(name=layer_name)
            layer.color = color
            layer.linetype = linetype

            log_info(f"Exporting layer: {layer_name}")
            self.add_geometries_to_dxf(msp, gdf, layer_name)

        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")

    def add_geometries_to_dxf(self, msp, gdf, layer_name):
        log_info(f"Adding geometries to DXF for layer: {layer_name}")
        
        if not isinstance(gdf, gpd.GeoDataFrame):
            log_warning(f"Expected GeoDataFrame for layer {layer_name}, but got {type(gdf)}")
            return

        for geometry in gdf.geometry:
            self.add_geometry_to_dxf(msp, geometry, layer_name)

    def add_geometry_to_dxf(self, msp, geometry, layer_name):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            self.add_polygon_to_dxf(msp, geometry, layer_name)
        elif isinstance(geometry, (LineString, MultiLineString)):
            self.add_linestring_to_dxf(msp, geometry, layer_name)
        elif isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                self.add_geometry_to_dxf(msp, geom, layer_name)
        else:
            log_warning(f"Unsupported geometry type for layer {layer_name}: {type(geometry)}")

    def add_polygon_to_dxf(self, msp, geometry, layer_name):
        if isinstance(geometry, Polygon):
            polygons = [geometry]
        elif isinstance(geometry, MultiPolygon):
            polygons = list(geometry.geoms)
        else:
            return

        for polygon in polygons:
            exterior_coords = list(polygon.exterior.coords)
            if len(exterior_coords) > 2:
                msp.add_lwpolyline(exterior_coords, dxfattribs={'layer': layer_name, 'closed': self.layer_properties[layer_name]['close']})

            for interior in polygon.interiors:
                interior_coords = list(interior.coords)
                if len(interior_coords) > 2:
                    msp.add_lwpolyline(interior_coords, dxfattribs={'layer': layer_name, 'closed': self.layer_properties[layer_name]['close']})

    def add_linestring_to_dxf(self, msp, geometry, layer_name):
        if isinstance(geometry, LineString):
            linestrings = [geometry]
        elif isinstance(geometry, MultiLineString):
            linestrings = list(geometry.geoms)
        else:
            return

        for linestring in linestrings:
            coords = list(linestring.coords)
            if len(coords) > 1:
                msp.add_lwpolyline(coords, dxfattribs={'layer': layer_name, 'closed': self.layer_properties[layer_name]['close']})
    def run(self):
        self.process_layers()
        self.export_to_dxf()

def main():
    setup_logging()
    setup_proj()

    parser = argparse.ArgumentParser(description="Process and export project data to DXF.")
    parser.add_argument("project_name", help="Name of the project to process")
    parser.add_argument("--update", nargs='+', help="List of layers to update", default=None)
    args = parser.parse_args()

    processor = ProjectProcessor(args.project_name, args.update)
    processor.run()

    # try:
    #     processor = ProjectProcessor(args.project_name, args.update)
    #     processor.run()
    # except Exception as e:
    #     log_error(f"An error occurred: {str(e)}")
    #     sys.exit(1)

if __name__ == "__main__":
    main()