import os
import sys
import yaml
import geopandas as gpd
import ezdxf
from shapely.ops import unary_union
from wmts_downloader import download_wmts_tiles
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
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
        self.load_color_mapping()
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
        self.template_dxf = self.resolve_full_path(self.project_settings.get('template', '')) if self.project_settings.get('template') else None
        self.export_format = self.project_settings.get('exportFormat', 'dxf')
        self.dxf_version = self.project_settings.get('dxfVersion', 'R2010')

    def setup_layers(self):
        self.layer_properties = {}
        self.colors = {}

        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)
            color_code = self.get_color_code(layer['color'])
            self.colors[layer['name']] = color_code
            self.colors[f"{layer['name']} Label"] = color_code

    def setup_wmts_layers(self):
        for wmts in self.wmts:
            layer_name = wmts['name']
            if layer_name not in self.layer_properties:
                self.add_layer_properties(layer_name, {
                    'color': "White",
                    'locked': True
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
        
        text_layer_name = f"{layer_name} Label"
        self.layer_properties[text_layer_name] = {
            'color': color,
            'locked': layer_info.get('locked', False),
            'close': True
        }

    def create_geltungsbereich_layer(self, layer_name, operation):
        log_info(f"Creating Geltungsbereich layer: {layer_name}")
        combined_geometry = None

        for layer in operation['layers']:
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

            if combined_geometry is None:
                combined_geometry = filtered_gdf.geometry.unary_union
            else:
                combined_geometry = combined_geometry.intersection(filtered_gdf.geometry.unary_union)

        if combined_geometry:
            if 'clipToLayers' in operation:
                for clip_layer_name in operation['clipToLayers']:
                    if clip_layer_name in self.all_layers:
                        clip_geometry = self.all_layers[clip_layer_name].geometry.unary_union
                        combined_geometry = combined_geometry.difference(clip_geometry)
                    else:
                        log_warning(f"Clip layer '{clip_layer_name}' not found for Geltungsbereich")

            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[combined_geometry], crs=self.crs)
            log_info(f"Created Geltungsbereich layer: {layer_name}")
        else:
            log_warning(f"No geometry created for Geltungsbereich layer: {layer_name}")


    def create_clip_distance_layer(self, layer_name, operation):
        log_info(f"Creating clip distance layer: {layer_name}")
        buffer_distance = operation['distance']
        source_layer = operation['sourceLayer']
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
            
    def create_buffer_layer(self, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layer = operation['sourceLayer']
        buffer_distance = operation['distance']
        buffer_mode = operation.get('mode', 'both')
        clip_to_layers = operation.get('clipToLayers', [])

        if source_layer in self.all_layers:
            original_geometry = self.all_layers[source_layer]
            
            if buffer_mode == 'outer':
                buffered = original_geometry.buffer(buffer_distance, join_style=2)
                result = buffered.difference(original_geometry)
            elif buffer_mode == 'inner':
                result = original_geometry.buffer(-buffer_distance, join_style=2)
            else:  # 'both'
                result = original_geometry.buffer(buffer_distance, join_style=2)

            # Clip the buffer to the specified layers
            if clip_to_layers:
                clip_geometry = None
                for clip_layer in clip_to_layers:
                    if clip_layer in self.all_layers:
                        if clip_geometry is None:
                            clip_geometry = self.all_layers[clip_layer]
                        else:
                            clip_geometry = clip_geometry.union(self.all_layers[clip_layer])
                    else:
                        log_warning(f"Warning: Clip layer '{clip_layer}' not found for buffer layer '{layer_name}'")
                
                if clip_geometry is not None:
                    result = result.intersection(clip_geometry)

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

    def create_exclusion_layer(self, layer_name, operation):
        log_info(f"Creating exclusion layer: {layer_name}")
        scope_layer = operation['scopeLayer']
        exclude_layers = operation['excludeLayers']

        log_info(f"  Scope layer: {scope_layer}")
        log_info(f"  Exclude layers: {exclude_layers}")

        if scope_layer in self.all_layers:
            scope_geometry = self.all_layers[scope_layer]
            excluded_geometry = scope_geometry

            for exclude_layer in exclude_layers:
                if exclude_layer in self.all_layers:
                    log_info(f"  Excluding {exclude_layer}")
                    excluded_geometry = excluded_geometry.difference(self.all_layers[exclude_layer])
                else:
                    log_warning(f"Warning: Exclude layer '{exclude_layer}' not found for exclusion layer '{layer_name}'")

            self.all_layers[layer_name] = excluded_geometry
            log_info(f"Created exclusion layer: {layer_name}")
        else:
            log_warning(f"Warning: Scope layer '{scope_layer}' not found for exclusion layer '{layer_name}'")

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
                    self.create_clip_distance_layer(layer_name, operation)
                elif op_type == 'geltungsbereich':
                    self.create_geltungsbereich_layer(layer_name, operation)
                elif op_type == 'exclusion':
                    self.create_exclusion_layer(layer_name, operation)
                elif op_type == 'wmts':
                    self.process_wmts_layer(layer_name, operation)
                else:
                    log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
            elif 'shapeFile' in layer:
                # This is a shapefile layer, already loaded in setup_shapefiles()
                pass
            else:
                # This is a layer without operation or shapefile
                self.all_layers[layer_name] = None
                log_info(f"Added layer {layer_name} without data")

        log_info("Finished processing layers.")


    def process_wmts_layer(self, layer_name, operation):
        log_info(f"Processing WMTS layer: {layer_name}")
        
        wmts_layers = operation.get('layers', [])
        
        if not wmts_layers:
            log_warning(f"No layers specified for WMTS download of {layer_name}")
            return

        combined_geometry = None
        for layer in wmts_layers:
            if layer in self.all_layers:
                layer_geometry = self.all_layers[layer]
                if isinstance(layer_geometry, gpd.GeoDataFrame):
                    layer_geometry = layer_geometry.geometry.unary_union
                if combined_geometry is None:
                    combined_geometry = layer_geometry
                else:
                    combined_geometry = combined_geometry.union(layer_geometry)
            else:
                log_warning(f"Layer {layer} not found for WMTS download of {layer_name}")

        if combined_geometry is None:
            log_warning(f"No valid layers found for WMTS download of {layer_name}")
            return

        buffer_distance = operation.get('buffer', 100)
        target_folder = self.resolve_full_path(operation['targetFolder'])
        wmts_info = {
            'url': operation['url'],
            'layer': operation['layer'],
            'zoom': operation['zoom'],
            'proj': operation['proj'],
            'format': operation.get('format', 'image/png'),
        }

        zoom_folder = os.path.join(target_folder, f"zoom_{wmts_info['zoom']}")
        
        if os.path.exists(zoom_folder) and os.path.isdir(zoom_folder):
            log_info(f"Zoom folder for {layer_name} (zoom level {wmts_info['zoom']}) exists. Checking for existing tiles.")
            existing_tiles = self.find_existing_tiles(zoom_folder)

            if existing_tiles:
                self.all_layers[layer_name] = existing_tiles
                log_info(f"Loaded {len(existing_tiles)} existing tiles for layer: {layer_name} (zoom level {wmts_info['zoom']})")
                self.log_tile_info(existing_tiles)
            else:
                log_info(f"No existing tiles found in {zoom_folder} for layer: {layer_name}. Will download tiles.")
                downloaded_tiles = download_wmts_tiles(wmts_info, combined_geometry, buffer_distance, target_folder)
                self.all_layers[layer_name] = downloaded_tiles
                self.log_tile_info(downloaded_tiles)
        else:
            log_info(f"Zoom folder {zoom_folder} does not exist. Will download tiles.")
            os.makedirs(target_folder, exist_ok=True)
            downloaded_tiles = download_wmts_tiles(wmts_info, combined_geometry, buffer_distance, target_folder)
            self.all_layers[layer_name] = downloaded_tiles
            self.log_tile_info(downloaded_tiles)

    def find_existing_tiles(self, folder):
        existing_tiles = []
        image_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff']
        world_file_extensions = ['.jgw', '.jpgw', '.pgw', '.pngw', '.tfw', '.tifw']

        for file in os.listdir(folder):
            file_lower = file.lower()
            if any(file_lower.endswith(ext) for ext in image_extensions):
                image_path = os.path.join(folder, file)
                base_name = os.path.splitext(image_path)[0]
                
                world_file = next((base_name + wf_ext for wf_ext in world_file_extensions 
                                if os.path.exists(base_name + wf_ext)), None)
                
                if world_file:
                    existing_tiles.append((image_path, world_file))

        return existing_tiles

    def log_tile_info(self, tiles):
        for idx, (image_path, world_file_path) in enumerate(tiles[:5]):  # Log only first 5 for brevity
            log_info(f"  Tile {idx + 1}: Image: {os.path.basename(image_path)}, World file: {os.path.basename(world_file_path)}")
        if len(tiles) > 5:
            log_info(f"  ... and {len(tiles) - 5} more tiles")

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
        doc = ezdxf.new(dxfversion=dxf_version)
        msp = doc.modelspace()

        for layer_name, geo_data in self.all_layers.items():
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

            layer_properties = self.layer_properties.get(layer_name, {})
            color = layer_properties.get('color', 7)  # Default to white if color not specified
            linetype = 'CONTINUOUS'
            
            # Create the layer
            layer = doc.layers.new(name=layer_name)
            layer.color = color
            layer.linetype = linetype

            # Create the text layer
            text_layer_name = f"{layer_name} Label"
            text_layer = doc.layers.new(name=text_layer_name)
            text_layer.color = color
            text_layer.linetype = linetype

            log_info(f"Exporting layer: {layer_name}")
            
            if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
                # This is a WMTS layer with downloaded tiles
                self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
            else:
                self.add_geometries_to_dxf(msp, geo_data, layer_name)

        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")

    def add_wmts_xrefs_to_dxf(self, msp, tile_data, layer_name):
        log_info(f"Adding WMTS xrefs to DXF for layer: {layer_name}")
        
        for image_path, world_file_path in tile_data:
            self.add_image_with_worldfile(msp, image_path, world_file_path, layer_name)

        log_info(f"Added {len(tile_data)} WMTS xrefs to layer: {layer_name}")

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
        # Ensure the layer exists with proper properties
        if layer_name not in self.layer_properties:
            self.add_layer_properties(layer_name, {
                'color': "White",
                'locked': False,
                'close': True
            })

        # Create a relative path for the image
        relative_image_path = os.path.relpath(
            image_path, os.path.dirname(self.dxf_filename))

        # Create the image definition with the relative path
        image_def = msp.doc.add_image_def(
            filename=relative_image_path, size_in_pixel=(256, 256))

        # Read the world file to get the transformation parameters
        with open(world_file_path, 'r') as wf:
            a = float(wf.readline().strip())
            d = float(wf.readline().strip())
            b = float(wf.readline().strip())
            e = float(wf.readline().strip())
            c = float(wf.readline().strip())
            f = float(wf.readline().strip())

        # Calculate the insertion point and size
        insert_point = (c, f - abs(e) * 256)
        size_in_units = (a * 256, abs(e) * 256)

        # Add the image with relative path
        image = msp.add_image(
            insert=insert_point,
            size_in_units=size_in_units,
            image_def=image_def,
            rotation=0,
            dxfattribs={'layer': layer_name}
        )

        # Set the image path as a relative path
        image.dxf.image_def_handle = image_def.dxf.handle
        image.dxf.flags = 3  # Set bit 0 and 1 to indicate relative path

        # Set the $PROJECTNAME header variable to an empty string
        msp.doc.header['$PROJECTNAME'] = ''

    def add_geometries_to_dxf(self, msp, geo_data, layer_name):
        log_info(f"Adding geometries to DXF for layer: {layer_name}")
        
        if geo_data is None:
            log_info(f"No geometry data available for layer: {layer_name}")
            return

        if isinstance(geo_data, gpd.GeoDataFrame):
            geometries = geo_data.geometry
            label_column = self.get_label_column(layer_name)
            if label_column and label_column in geo_data.columns:
                labels = geo_data[label_column]
            else:
                labels = None
        elif isinstance(geo_data, gpd.GeoSeries):
            geometries = geo_data
            labels = None
        else:
            log_warning(f"Unexpected data type for layer {layer_name}: {type(geo_data)}")
            return

        for idx, geometry in enumerate(geometries):
            if isinstance(geometry, (Polygon, MultiPolygon)):
                self.add_polygon_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, (LineString, MultiLineString)):
                self.add_linestring_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, GeometryCollection):
                for geom in geometry.geoms:
                    self.add_geometry_to_dxf(msp, geom, layer_name)
            else:
                log_warning(f"Unsupported geometry type for layer {layer_name}: {type(geometry)}")
            
            if labels is not None:
                self.add_label_to_dxf(msp, geometry, labels.iloc[idx], layer_name)
            elif self.is_generated_layer(layer_name):
                # Add label for generated layers using the layer name
                self.add_label_to_dxf(msp, geometry, layer_name, layer_name)

    def is_generated_layer(self, layer_name):
        # Check if the layer is generated (has an operation) and not loaded from a shapefile
        for layer in self.project_settings['dxfLayers']:
            if layer['name'] == layer_name:
                return 'operation' in layer and 'shapeFile' not in layer
        return False

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

    def get_label_column(self, layer_name):
        for layer in self.project_settings['dxfLayers']:
            if layer['name'] == layer_name and 'label' in layer:
                return layer['label']
        return None

    def add_label_to_dxf(self, msp, geometry, label, layer_name):
        centroid = self.get_geometry_centroid(geometry)
        if centroid is None:
            log_warning(f"Could not determine centroid for geometry in layer {layer_name}")
            return

        text_layer_name = f"{layer_name} Label"
        self.add_text(
            msp,
            str(label),
            centroid.x,
            centroid.y,
            text_layer_name,
            'Standard',
            self.colors[text_layer_name]
        )

    def get_text_height(self, geometry):
        # Calculate text height based on geometry size
        bounds = geometry.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        max_dimension = max(width, height)
        return max_dimension * 0.05  # Adjust this factor as needed

    def get_geometry_centroid(self, geometry):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            return geometry.centroid
        elif isinstance(geometry, (LineString, MultiLineString)):
            return geometry.interpolate(0.5, normalized=True)
        elif isinstance(geometry, Point):
            return geometry
        elif isinstance(geometry, GeometryCollection):
            # For GeometryCollection, we'll use the centroid of the first geometry
            if len(geometry.geoms) > 0:
                return self.get_geometry_centroid(geometry.geoms[0])
        return None

    def add_text(self, msp, text, x, y, layer_name, style_name, color):
        msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1,
            'color': color
        })

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