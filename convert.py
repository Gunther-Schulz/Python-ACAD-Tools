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
        self.all_layers = {}
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

    def setup_shapefiles(self):
        self.shapefile_paths = {}
        self.shapefile_labels = {}
        self.shapefiles = {}
        self.all_layers = {}  # Make sure this is initialized

        for layer in self.project_settings['dxfLayers']:
            if 'shapeFile' in layer:
                layer_name = layer['name']
                self.shapefile_paths[layer_name] = self.resolve_full_path(layer['shapeFile'])
                self.shapefile_labels[layer_name] = layer.get('label')

                try:
                    gdf = self.load_shapefile(self.shapefile_paths[layer_name])
                    self.shapefiles[layer_name] = gdf
                    self.all_layers[layer_name] = gdf.geometry.unary_union
                    log_info(f"Loaded shapefile for layer: {layer_name}")
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

    def create_geltungsbereich_layers(self):
        log_info("Starting to create Geltungsbereich layers...")
        for geltungsbereich in self.geltungsbereich_layers:
            layer_name = geltungsbereich['layerName']
            log_info(f"Processing Geltungsbereich layer: {layer_name}")
            
            combined_geometry = None
            for coverage_index, coverage in enumerate(geltungsbereich['coverages']):
                log_info(f"  Processing coverage {coverage_index + 1}")
                coverage_geometry = None
                for layer in coverage['layers']:
                    layer_name = layer['name']
                    value_list = layer['valueList']
                    log_info(f"    Processing layer: {layer_name}")
                    log_info(f"    Value list: {value_list}")
                    
                    if layer_name not in self.shapefiles:
                        log_warning(f"    Warning: Layer '{layer_name}' not found in shapefiles.")
                        continue
                    
                    gdf = self.shapefiles[layer_name]
                    label_column = self.shapefile_labels.get(layer_name)
                    if not label_column:
                        log_warning(f"    Warning: Label column for layer '{layer_name}' not found.")
                        continue
                    
                    log_info(f"    Label column: {label_column}")
                    log_info(f"    Unique values in label column: {gdf[label_column].unique()}")
                    
                    filtered_gdf = gdf[gdf[label_column].isin(value_list)]
                    log_info(f"    Filtered GeoDataFrame size: {len(filtered_gdf)}")
                    
                    if coverage_geometry is None:
                        coverage_geometry = filtered_gdf.geometry.unary_union
                    else:
                        coverage_geometry = coverage_geometry.intersection(filtered_gdf.geometry.unary_union)
                
                if coverage_geometry:
                    if combined_geometry is None:
                        combined_geometry = coverage_geometry
                    else:
                        combined_geometry = combined_geometry.union(coverage_geometry)
                else:
                    log_warning(f"    Warning: No geometry created for coverage {coverage_index + 1}")
        
            if combined_geometry:
                # Clip with all layers in clipDistanceLayers
                for clip_layer in self.clip_distance_layers:
                    clip_layer_name = clip_layer['name']
                    if clip_layer_name in self.all_layers:
                        clip_geometry = self.all_layers[clip_layer_name]
                        
                        if clip_layer['bufferDistance'] > 0:
                            clip_geometry = clip_geometry.buffer(clip_layer['bufferDistance'], join_style=2)
                        
                        combined_geometry = combined_geometry.difference(clip_geometry)
                    else:
                        log_warning(f"Warning: Clip layer '{clip_layer_name}' not found in all_layers")
                
                self.all_layers[geltungsbereich['layerName']] = combined_geometry
                log_info(f"Created Geltungsbereich layer: {geltungsbereich['layerName']}")
            else:
                log_warning(f"Warning: No geometry created for Geltungsbereich layer: {geltungsbereich['layerName']}")
        
        log_info("Finished creating Geltungsbereich layers.")

    def create_clip_distance_layers(self, layer_name):
        log_info(f"Creating clip distance layer: {layer_name}")
        layer = next((l for l in self.clip_distance_layers if l['name'] == layer_name), None)
        if layer:
            buffer_distance = layer['bufferDistance']
            if layer_name in self.all_layers:
                original_geometry = self.all_layers[layer_name]
                if buffer_distance > 0:
                    clipped = original_geometry.buffer(buffer_distance, join_style=2)
                else:
                    clipped = original_geometry
                self.all_layers[layer_name] = clipped.unary_union
                log_info(f"Created clip distance layer: {layer_name}")
            else:
                log_warning(f"Warning: Layer '{layer_name}' not found in all_layers for clip distance layer")
        else:
            log_warning(f"Warning: Clip distance layer '{layer_name}' not found in configuration")
            
    def create_buffer_distance_layers(self):
        log_info("Starting to create buffer distance layers...")
        for layer in self.buffer_distance_layers:
            layer_name = layer['name']
            buffer_distance = layer['bufferDistance']

            if layer_name in self.all_layers:
                log_info(f"Processing buffer distance layer: {layer_name}")
                original_geometry = self.all_layers[layer_name]
                buffered = original_geometry.buffer(buffer_distance, join_style=2)
                self.all_layers[layer_name] = buffered.unary_union
                log_info(f"Created buffer distance layer: {layer_name}")
            else:
                log_warning(f"Warning: Layer '{layer_name}' not found in all_layers for buffer distance layer")

        log_info("Finished creating buffer distance layers.")

    def create_offset_layers(self):
        log_info("Starting to create offset layers...")
        for layer in self.offset_layers:
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

    def process_wmts_layers(self):
        log_info("Starting to process WMTS layers...")
        for wmts in self.wmts:
            layer_name = wmts['dxfLayer']
            log_info(f"Processing WMTS layer: {layer_name}")
            
            url = wmts['url']
            layer = wmts['layer']
            zoom = wmts['zoom']
            proj = wmts['proj']
            target_folder = self.resolve_full_path(wmts['targetFolder'])

            try:
                download_wmts_tiles(url, layer, zoom, proj, target_folder)
                log_info(f"Downloaded WMTS tiles for layer: {layer_name}")
            except Exception as e:
                log_error(f"Error downloading WMTS tiles for layer '{layer_name}': {str(e)}")

        log_info("Finished processing WMTS layers.")

    def has_corresponding_layer(self, layer_name):
        return layer_name in self.layer_properties

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
                    self.create_buffer_layer(layer_name, operation['sourceLayer'], operation['distance'])
                elif op_type == 'clip':
                    self.create_clip_layer(layer_name, operation['sourceLayer'], operation['distance'])
                elif op_type == 'offset':
                    self.create_offset_layer(layer_name, operation['sourceLayer'], operation['distance'])
                elif op_type == 'geltungsbereich':
                    self.create_geltungsbereich_layer(layer_name, operation['coverages'])
                elif op_type == 'exclusion':
                    self.create_exclusion_layer(layer_name, operation['scopeLayer'], operation['excludeLayers'])
                elif op_type == 'innerBuffer':
                    self.create_inner_buffer_layer(layer_name, operation['sourceLayer'], operation['distance'])
                else:
                    log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
            elif layer_name not in self.all_layers:
                log_warning(f"Layer {layer_name} not found and has no operation defined.")

        log_info("Finished processing layers.")

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()

        for layer_name, geometry in self.all_layers.items():
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

            layer_properties = self.layer_properties.get(layer_name, {})
            color = layer_properties.get('color', 7)  # Default to white if color not specified
            linetype = 'CONTINUOUS'
            doc.layers.new(name=layer_name, color=color, linetype=linetype)

            if isinstance(geometry, (Polygon, MultiPolygon)):
                self.add_polygon_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, (LineString, MultiLineString)):
                self.add_linestring_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, GeometryCollection):
                for geom in geometry.geoms:
                    if isinstance(geom, (Polygon, MultiPolygon)):
                        self.add_polygon_to_dxf(msp, geom, layer_name)
                    elif isinstance(geom, (LineString, MultiLineString)):
                        self.add_linestring_to_dxf(msp, geom, layer_name)

        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")

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