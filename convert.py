import os
import sys
import yaml
import geopandas as gpd
import ezdxf
import matplotlib.pyplot as plt
from shapely.ops import linemerge, unary_union
from wmts_downloader import download_wmts_tiles
from shapely.geometry import Point, Polygon, LineString, MultiPolygon, MultiLineString
import random
from ezdxf.addons import odafc
import argparse
import colorama
import logging
import pyproj
from pyproj import CRS

# Setup logging first
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

# Unset potentially conflicting environment variables
if 'PROJ_DATA' in os.environ:
    log_info(f"Unsetting PROJ_DATA (was set to: {os.environ['PROJ_DATA']})")
    del os.environ['PROJ_DATA']

# List of common PROJ data directories
proj_data_dirs = [
    '/usr/share/proj',
    '/usr/local/share/proj',
    '/opt/homebrew/share/proj',
    'C:\\Program Files\\PROJ\\share',
    os.path.join(sys.prefix, 'share', 'proj'),
]

# Find the first directory that contains proj.db
for directory in proj_data_dirs:
    if os.path.exists(os.path.join(directory, 'proj.db')):
        os.environ['PROJ_LIB'] = directory
        log_info(f"Set PROJ_LIB to: {directory}")
        break
else:
    log_warning("Could not find proj.db in any of the standard locations.")

# Disable network access for PROJ
os.environ['PROJ_NETWORK'] = 'OFF'
log_info("Set PROJ_NETWORK to OFF")

log_info(f"Current PROJ_LIB: {os.environ.get('PROJ_LIB', 'Not set')}")
log_info(f"Current PATH: {os.environ.get('PATH', 'Not set')}")

pyproj.datadir.set_data_dir(os.environ['PROJ_LIB'])
log_info(f"PyProj data directory: {pyproj.datadir.get_data_dir()}")
log_info(f"PyProj version: {pyproj.__version__}")

# Try to create a CRS object
try:
    crs = CRS("EPSG:4326")
    log_info(f"Successfully created CRS object: {crs}")
except Exception as e:
    log_error(f"Error creating CRS object: {str(e)}")

# Try to perform a simple transformation
try:
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    result = transformer.transform(0, 0)
    log_info(f"Successfully performed transformation: {result}")
except Exception as e:
    log_error(f"Error performing transformation: {str(e)}")

# Try to get the PROJ version from pyproj
try:
    proj_version = pyproj.__proj_version__
    log_info(f"PROJ version (from pyproj): {proj_version}")
except Exception as e:
    log_error(f"Error getting PROJ version: {str(e)}")

colorama.init()

class ProjectProcessor:
    def __init__(self, project_name: str, update_layers_list: list = None):
        # Load the color mapping from the YAML file
        with open('colors.yaml', 'r') as file:
            color_data = yaml.safe_load(file)
            self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
            self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}

        self.project_settings, self.folder_prefix, self.log_file = self.load_project_settings(project_name)
        if not self.project_settings:
            raise ValueError(f"Project {project_name} not found.")

        self.exclusions = self.project_settings.get('exclusions', [])

        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(
            self.project_settings['dxfFilename'])
        self.wmts = self.project_settings.get('wmts', [])
        self.clip_distance_layers = self.project_settings.get('clipDistanceLayers', [])
        self.buffer_distance_layers = self.project_settings.get('bufferDistanceLayers', [])
        self.geltungsbereich_layers = self.project_settings.get('geltungsbereichLayers', [])
        log_info(f"Loaded {len(self.geltungsbereich_layers)} Geltungsbereich layers:")
        for layer in self.geltungsbereich_layers:
            log_info(f"  - {layer['layerName']}")
        self.offset_layers = self.project_settings.get('offsetLayers', [])

        self.template_dxf = self.resolve_full_path(self.project_settings.get(
            'template', '')) if self.project_settings.get('template') else None

        # Initialize dictionaries to store shapefile paths and labels
        self.shapefile_paths = {}
        self.shapefile_labels = {}

        # Load shapefile paths and labels from dxfLayers
        for layer in self.project_settings['dxfLayers']:
            if 'shapeFile' in layer:
                layer_name = layer['name']
                self.shapefile_paths[layer_name] = self.resolve_full_path(layer['shapeFile'])
                self.shapefile_labels[layer_name] = layer.get('label')

        # Load shapefiles
        self.shapefiles = {}
        for layer_name, shapefile_path in self.shapefile_paths.items():
            try:
                self.shapefiles[layer_name] = self.load_shapefile(shapefile_path)
                log_info(f"Loaded shapefile for layer: {layer_name}")
            except Exception as e:
                log_warning(f"Failed to load shapefile for layer '{layer_name}': {str(e)}")

        self.colors = {}
        for layer in self.project_settings['dxfLayers']:
            color_code = self.get_color_code(layer['color'])
            self.colors[layer['name']] = color_code
            self.colors[f"{layer['name']} Number"] = color_code  # Add color for label layer

        # Modify this part to use the actual WMTS layer name
        self.wmts_layers = {
            wmts['name']: wmts['name'] for wmts in self.wmts
        }

        self.export_format = self.project_settings.get('exportFormat', 'dxf')

        if sys.platform == "darwin" and os.path.exists("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"):
            odafc.unix_exec_path = "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"

        self.update_layers_list = update_layers_list

        # Add layer definitions for all layers, including buffer distance layers
        self.layer_properties = {}
        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)

        for buffer_layer in self.buffer_distance_layers:
            layer_name = buffer_layer['name']
            if layer_name not in self.layer_properties:
                self.add_layer_properties(layer_name, {
                    'color': "Light Green",
                    'close': True,
                    'locked': False
                })

        # Handle WMTS layers
        for wmts in self.wmts:
            layer_name = wmts['dxfLayer']
            if layer_name not in self.layer_properties:
                self.add_layer_properties(layer_name, {
                    'color': "White",
                    'locked': wmts.get('locked', False)
                })

        # Handle exclusion layers
        for exclusion in self.exclusions:
            layer_info = self.find_layer_by_name(exclusion['name'])
            if layer_info:
                self.layer_properties[exclusion['name']] = {
                    'color': self.get_color_code(layer_info['color']),
                    'locked': layer_info.get('locked', False),
                    'close': layer_info.get('close', True)
                }
            else:
                log_warning(f"Layer '{exclusion['name']}' not found in project settings.")

        # Handle buffer distance layers
        for buffer_layer in self.buffer_distance_layers:
            # Use the shapefile name (without extension) as the layer name if not provided
            layer_name = buffer_layer.get('name', os.path.splitext(os.path.basename(buffer_layer['shapeFile']))[0])
            buffer_layer['name'] = layer_name  # Add the name to the buffer_layer dict
            self.add_layer_properties(layer_name, buffer_layer)

        # Create clip distance layers
        self.create_clip_distance_layers()

        # Create buffer distance layers
        self.create_buffer_distance_layers()

        # Create Geltungsbereich layers
        self.create_geltungsbereich_layers()

        # Load geometries for all layers
        all_geometries = {}
        for layer in self.project_settings['dxfLayers']:
            if 'shapeFile' in layer:
                shapefile_path = self.resolve_full_path(layer['shapeFile'])
                if os.path.exists(shapefile_path):
                    gdf = gpd.read_file(shapefile_path)
                    all_geometries[layer['name']] = gdf.geometry.tolist()
                else:
                    log_warning(f"Shapefile not found for layer '{layer['name']}': {shapefile_path}")

        # Create offset layers
        self.create_offset_layers(all_geometries)


    def find_layer_by_name(self, layer_name):
        """Find a layer in the project settings by its name."""
        for layer in self.project_settings['dxfLayers']:
            if layer['name'] == layer_name:
                return layer
        return None

    def load_project_settings(self, project_name: str):
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            projects = data['projects']
            folder_prefix = data.get('folderPrefix', '')
            log_file = data.get('logFile', './log.txt')
            return next((project for project in projects if project['name'] == project_name), None), folder_prefix, log_file

    def resolve_full_path(self, path: str) -> str:
        return os.path.abspath(os.path.expanduser(os.path.join(self.folder_prefix, path)))

    def load_shapefile(self, file_path: str) -> gpd.GeoDataFrame:
        gdf = gpd.read_file(file_path)
        gdf = gdf.set_crs(self.crs, allow_override=True)
        return gdf

    def parcel_missing(self, gdf: gpd.GeoDataFrame, coverage: dict) -> set:
        return set(coverage["parcelList"]).difference(gdf[self.shapefile_labels['Parcel']])

    def filter_parcels(self, coverage):
        parcels_missing = self.parcel_missing(self.shapefiles['Parcel'], coverage)
        if not parcels_missing:
            log_info("All parcels found.")

        # Find the corresponding geltungsbereich layer
        geltungsbereich_layer = next((layer for layer in self.geltungsbereich_layers if layer['layerName'] == coverage['layerName']), None)
        
        if not geltungsbereich_layer:
            raise ValueError(f"Geltungsbereich layer '{coverage['layerName']}' not found in project settings.")

        buffer_distance = -10  # Default buffer distance, you might want to make this configurable

        # Infer layer names from dxfLayers
        relevant_layers = [layer['name'] for layer in self.project_settings['dxfLayers'] 
                           if 'shapeFile' in layer]

        buffered_layers = {}
        for i, layer_name in enumerate(relevant_layers):
            if i >= len(coverage['valueLists']):
                log_warning(f"Warning: No values provided for layer {layer_name}")
                continue

            layer_data = self.shapefiles.get(layer_name)
            if layer_data is None:
                log_warning(f"Warning: Layer '{layer_name}' not found in shapefiles.")
                continue
            
            layer_label = self.shapefile_labels.get(layer_name)
            if layer_label is None:
                log_warning(f"Warning: Label for layer '{layer_name}' not found.")
                continue
            
            filtered_data = layer_data[layer_data[layer_label].isin(coverage['valueLists'][i])]
            if not filtered_data.empty:
                buffered_layers[layer_name] = filtered_data.unary_union.buffer(buffer_distance)
            else:
                log_warning(f"Warning: No data found for layer '{layer_name}' after filtering.")

        # Use the first layer (assumed to be 'Parcel') for selected parcels
        parcel_layer_name = relevant_layers[0]
        selected_parcels = self.shapefiles[parcel_layer_name][self.shapefiles[parcel_layer_name][self.shapefile_labels[parcel_layer_name]].isin(coverage['valueLists'][0])]
        selected_parcels_mask = self.shapefiles[parcel_layer_name].index.isin(selected_parcels.index)

        # Create masks for each buffered layer
        masks = [selected_parcels_mask]
        for buffered_layer in buffered_layers.values():
            masks.append(self.shapefiles[parcel_layer_name].intersects(buffered_layer))

        # Combine all masks
        final_mask = masks[0]
        for mask in masks[1:]:
            final_mask &= mask

        result = self.shapefiles[parcel_layer_name][final_mask]
        return result

    def select_parcel_edges(self, geom):
        # unused. see offsetLayers: in projects.yaml
        pass

    def load_template(self):
        if self.template_dxf:
            return ezdxf.readfile(self.template_dxf)
        return None

    def conditional_buffer(self, source_geom, target_geom, distance):
        if any(source_geom.intersects(geom) for geom in target_geom['geometry']):
            return source_geom.buffer(-distance, join_style=2)
        else:
            return source_geom.buffer(distance, join_style=2)

    def apply_conditional_buffering(self, source_geom, target_geom, distance):
        source_geom['geometry'] = source_geom['geometry'].apply(
            lambda x: self.conditional_buffer(x, target_geom, distance, join_style=2))
        return source_geom

    def labeled_center_points(self, source_geom, label):
        points_within = source_geom.representative_point()
        return gpd.GeoDataFrame(geometry=points_within, data={"label": source_geom[label]})

    def add_text_style(self, doc, text_style_name):
        if text_style_name not in doc.styles:
            doc.styles.new(name=text_style_name, dxfattribs={
                           'font': 'Arial.ttf', 'height': 0.1})

    def add_text(self, msp, text, x, y, layer_name, style_name, color):
        msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1,
            'color': color  # Set the color for the text
        })

    def add_text_to_center(self, msp, points, layer_name):
        text_layer_name = f"{layer_name} Number"
        self.add_layer(msp.doc, text_layer_name)
        self.add_text_style(msp.doc, 'Standard')
        
        # Get the color from the layer properties
        color = self.layer_properties[text_layer_name]['color']
        
        for idx, row in points.iterrows():
            if row.geometry.geom_type == 'Point':
                x, y = row.geometry.x, row.geometry.y
            elif row.geometry.geom_type in ['Polygon', 'MultiPolygon']:
                centroid = row.geometry.centroid
                x, y = centroid.x, centroid.y
            else:
                log_warning(f"Unsupported geometry type {row.geometry.geom_type} for label in layer {text_layer_name}")
                continue
            
            self.add_text(msp, str(row['label']), x, y, text_layer_name, 'Standard', color)

    def add_geometries(self, msp, geometries, layer_name, close=True):
        self.add_layer(msp.doc, layer_name)
        
        if isinstance(geometries, gpd.GeoSeries):
            geometries = geometries.tolist()
        elif not isinstance(geometries, (list, tuple)):
            geometries = [geometries]
        
        for geom in geometries:
            if geom.geom_type == 'GeometryCollection':
                for subgeom in geom.geoms:
                    self.add_single_geometry(msp, subgeom, layer_name, close)
            else:
                self.add_single_geometry(msp, geom, layer_name, close)

    def add_single_geometry(self, msp, geom, layer_name, close):
        if geom is None or geom.is_empty:
            log_warning(f"Empty geometry encountered for layer '{layer_name}'. Skipping.")
            return

        try:
            if geom.geom_type in ['LineString', 'MultiLineString']:
                lines = geom.geoms if geom.geom_type == 'MultiLineString' else [geom]
                for line in lines:
                    points = list(line.coords)
                    if close and points[0] != points[-1]:
                        points.append(points[0])  # Close the linestring if it's not already closed
                    self.add_polyline(msp, points, layer_name)
            elif geom.geom_type == 'Polygon':
                exterior_points = list(geom.exterior.coords)
                if close:
                    exterior_points.append(exterior_points[0])  # Close the polygon
                self.add_polyline(msp, exterior_points, layer_name)
                for interior in geom.interiors:
                    interior_points = list(interior.coords)
                    if close:
                        interior_points.append(interior_points[0])  # Close the interior ring
                    self.add_polyline(msp, interior_points, layer_name)
            elif geom.geom_type == 'MultiPolygon':
                for poly in geom.geoms:
                    self.add_single_geometry(msp, poly, layer_name, close)
            else:
                log_warning(f"Unsupported geometry type: {geom.geom_type}")
        except Exception as e:
            log_error(f"Error adding geometry to layer '{layer_name}': {str(e)}")

    def add_polyline(self, msp, points, layer_name):
        if not points:
            log_warning(f"No points provided for polyline in layer '{layer_name}'. Skipping.")
            return None

        # Create a new polyline
        polyline = msp.add_lwpolyline(points=points, dxfattribs={'layer': layer_name})
        
        return polyline

    def add_layer(self, doc, layer_name):
        base_layer = layer_name.split('_')[0]  # Get the base layer name (e.g., 'WMTS DOP' from 'WMTS DOP_Hauptgeltungsbereich')
        properties = self.layer_properties.get(base_layer, {'color': 7, 'locked': False})
        if layer_name not in doc.layers:
            new_layer = doc.layers.new(name=layer_name)
        else:
            new_layer = doc.layers.get(layer_name)
        
        new_layer.color = properties['color']
        new_layer.lock = properties['locked']

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

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
        self.add_layer(msp.doc, layer_name)
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

    def clip_with_distance_layer_buffers(self, geom_to_clip):
        for layer in self.clip_distance_layers:
            shapefile = self.resolve_full_path(layer['shapeFile'])
            buffer_distance = layer['bufferDistance']

            # Load the shapefile
            gdf = self.load_shapefile(shapefile)

            # Create buffer with square corners
            buffered = gdf.buffer(buffer_distance, join_style=2)

            # Reduce geltungsbereich
            geom_to_clip = geom_to_clip.difference(buffered.unary_union)

        return geom_to_clip
    
    def get_distance_layer_buffers(self, geom_to_buffer, distance, clipping_geom=None):
        # Ensure geom_to_buffer is a GeoDataFrame
        if isinstance(geom_to_buffer, gpd.GeoSeries):
            geom_to_buffer = gpd.GeoDataFrame(geometry=geom_to_buffer)

        # Create buffer with square corners
        combined_buffer = geom_to_buffer.buffer(distance, join_style=2)

        # If a clipping geometry is provided, intersect the combined buffer with it
        if clipping_geom is not None:
            combined_buffer = combined_buffer.intersection(clipping_geom)

        return combined_buffer
    
    def create_exclusion_polygon(self, exclusion):
        scope_layer = exclusion['scopeLayer']
        exclude_layers = exclusion['excludeLayers']
        new_layer_name = exclusion['name']

        # Get the scope geometry
        scope_geom = self.geltungsbereich_geometries.get(scope_layer)
        if scope_geom is None:
            log_warning(f"Scope layer '{scope_layer}' not found.")
            return None

        # Initialize the exclusion geometry with the scope geometry
        exclusion_geom = scope_geom

        for layer in exclude_layers:
            layer_info = self.find_layer_by_name(layer)
            if layer_info and 'shapeFile' in layer_info:
                shapefile_path = self.resolve_full_path(layer_info['shapeFile'])
                if os.path.exists(shapefile_path):
                    layer_gdf = self.load_shapefile(shapefile_path)
                    layer_geom = layer_gdf['geometry'].unary_union
                    exclusion_geom = exclusion_geom.difference(layer_geom)
                else:
                    log_warning(f"Shapefile for exclusion layer '{layer}' not found: {shapefile_path}")
            else:
                # Check if it's a buffer distance layer
                buffer_layer = next((bl for bl in self.buffer_distance_layers if bl['name'] == layer), None)
                if buffer_layer:
                    buffer_shapefile = self.resolve_full_path(buffer_layer['shapeFile']).replace('.shp', f'_buffer_{buffer_layer["bufferDistance"]}.shp')
                    if os.path.exists(buffer_shapefile):
                        buffer_gdf = self.load_shapefile(buffer_shapefile)
                        buffer_geom = buffer_gdf['geometry'].unary_union
                        exclusion_geom = exclusion_geom.difference(buffer_geom)
                    else:
                        log_warning(f"Buffer shapefile for layer '{layer}' not found: {buffer_shapefile}")
                else:
                    log_warning(f"Exclusion layer '{layer}' not found in project settings or buffer distance layers.")

        # Store the resulting geometry
        self.exclusion_geometries[new_layer_name] = exclusion_geom

        log_info(f"Created exclusion polygon: {new_layer_name}")
        return exclusion_geom

    def process_single_layer(self, msp, layer):
        # Check if the layer is a clip distance layer
        if layer in [clip_layer['name'] for clip_layer in self.clip_distance_layers]:
            if not self.has_corresponding_layer(layer):
                log_info(f"Skipping clip distance layer: {layer} as it has no corresponding entry in 'dxfLayers'")
                return
            log_info(f"Processing clip distance layer: {layer}")
            geometry = self.clip_geometries[layer]
            self.add_geometries(msp, [geometry], layer, close=True)
            return

        # Remove existing entities in the layer
        for entity in msp.query(f'*[layer=="{layer}"]'):
            msp.delete_entity(entity)

        # Check if the layer is a Geltungsbereich layer
        if layer in self.geltungsbereich_geometries:
            log_info(f"Processing Geltungsbereich layer: {layer}")
            geometry = self.geltungsbereich_geometries[layer]
            self.add_geometries(msp, [geometry], layer, close=True)
            return
        elif layer in self.exclusion_geometries:
            log_info(f"Processing exclusion layer: {layer}")
            geometry = self.exclusion_geometries[layer]
            self.add_geometries(msp, [geometry], layer, close=True)
        elif layer in [wmts['name'] for wmts in self.wmts]:
            log_info(f"Processing WMTS layer: {layer}")
            wmts_info = next(wmts for wmts in self.wmts if wmts['name'] == layer)
            target_folder = self.resolve_full_path(wmts_info['targetFolder'])
            os.makedirs(target_folder, exist_ok=True)
            log_info(f"Updating WMTS tiles for layer '{layer}'")
            
            # Combine all Geltungsbereich geometries
            combined_geometry = unary_union([geom for geom in self.geltungsbereich_geometries.values()])
            
            # Download tiles for the combined geometry
            tiles = download_wmts_tiles(wmts_info, combined_geometry, 500, target_folder, True)
            
            # Add all downloaded tiles to the DXF
            for tile_path, world_file_path in tiles:
                self.add_image_with_worldfile(msp, tile_path, world_file_path, layer)
        else:
            layer_info = self.find_layer_by_name(layer)
            if layer_info:
                if 'shapeFile' in layer_info:
                    shapefile_path = self.resolve_full_path(layer_info['shapeFile'])
                    if os.path.exists(shapefile_path):
                        gdf = gpd.read_file(shapefile_path)
                        self.add_geometries(msp, gdf['geometry'], layer, close=layer_info.get('close', True))
                        
                        # Add labels if 'label' is specified in layer_info
                        if 'label' in layer_info:
                            label_column = layer_info['label']
                            if label_column in gdf.columns:
                                gdf['label'] = gdf[label_column].astype(str)  # Ensure label is a string
                                self.add_text_to_center(msp, gdf, layer)  # Use the same layer for labels
                            else:
                                log_warning(f"Label column '{label_column}' not found in shapefile for layer '{layer}'")
                    else:
                        log_error(f"Shapefile for layer '{layer}' not found: {shapefile_path}")
                else:
                    # Layer without shapefile, possibly a dynamically created layer (like buffer layers)
                    log_info(f"Layer '{layer}' has no associated shapefile. It may be created dynamically.")
            else:
                log_warning(f"Layer '{layer}' not found in project settings")

        # Set layer properties
        self.add_layer(self.doc, layer)

        log_info(f"Finished processing layer: {layer}")


    def add_layer_properties(self, layer_name, layer_info):
        color = self.get_color_code(layer_info.get('color', 'White'))
        self.layer_properties[layer_name] = {
            'color': color,
            'locked': layer_info.get('locked', False),
            'close': layer_info.get('close', True)
        }
        
        # Add properties for the text/number layer
        text_layer_name = f"{layer_name} Number"
        self.layer_properties[text_layer_name] = {
            'color': color,  # Use the same color as the main layer
            'locked': layer_info.get('locked', False),
            'close': True
        }

    def has_corresponding_layer(self, layer_name):
        """Check if the given layer name has a corresponding entry in the 'dxfLayers' section."""
        return any(layer['name'] == layer_name for layer in self.project_settings['dxfLayers'])

    def create_clip_distance_layers(self):
        log_info("Starting to create clip distance layers...")
        self.clip_geometries = {}
        for layer in self.clip_distance_layers:
            input_shapefile = self.resolve_full_path(layer['shapeFile'])
            buffer_distance = layer['bufferDistance']
            layer_name = layer['name']

            # Only process if there's a corresponding layer in the 'dxfLayers' section
            if self.has_corresponding_layer(layer_name):
                log_info(f"Processing clip distance layer: {layer_name}")
                log_info(f"Input shapefile: {input_shapefile}")
                log_info(f"Buffer distance: {buffer_distance}")

                # Load the input shapefile
                gdf = gpd.read_file(input_shapefile)

                # Create buffer with square corners
                buffered = gdf.buffer(buffer_distance, join_style=2)

                # Store the buffered geometry
                self.clip_geometries[layer_name] = buffered.unary_union

                log_info(f"Created clip distance geometry for layer: {layer_name}")
            else:
                log_info(f"Skipping clip distance layer '{layer_name}' as it has no corresponding entry in 'dxfLayers'")

        log_info("Finished creating clip distance layers.")

    def create_buffer_distance_layers(self):
        log_info("Creating buffer distance layers...")
        self.buffer_geometries = {}
        for buffer_layer in self.buffer_distance_layers:
            input_shapefile = self.resolve_full_path(buffer_layer['shapeFile'])
            buffer_distance = buffer_layer['bufferDistance']
            layer_name = buffer_layer['name']

            # Only process if there's a corresponding layer in the 'dxfLayers' section
            if self.has_corresponding_layer(layer_name):
                try:
                    # Load the input shapefile
                    gdf = gpd.read_file(input_shapefile)
                    
                    # Create buffer with square corners
                    buffered = gdf.buffer(buffer_distance, join_style=2)
                    
                    # Get the combined Geltungsbereich geometry
                    geltungsbereich_geometry = self.get_combined_geltungsbereich()
                    
                    # Intersect the buffer with the Geltungsbereich
                    clipped_buffer = buffered.intersection(geltungsbereich_geometry)
                    
                    # Store the buffered geometry
                    self.buffer_geometries[layer_name] = clipped_buffer
                
                    log_info(f"Created buffer for layer: {layer_name}")
                except Exception as e:
                    log_error(f"Error creating buffer for layer {layer_name}: {str(e)}")
            else:
                log_info(f"Skipping buffer distance layer '{layer_name}' as it has no corresponding entry in 'dxfLayers'")

    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union

    def inner_buffer(geometry, distance):
        """
        Perform an inner buffer on a geometry, including holes.
        
        :param geometry: A Shapely geometry (Polygon or MultiPolygon)
        :param distance: The buffer distance (negative for inward buffer)
        :return: The buffered geometry
        """
        if not isinstance(geometry, (Polygon, MultiPolygon)):
            raise ValueError("Input geometry must be a Polygon or MultiPolygon")

        def buffer_polygon(poly):
            # Buffer the exterior
            exterior_ring = poly.exterior
            buffered_exterior = exterior_ring.buffer(distance, join_style=2)

            # Buffer each interior (hole) outwards
            buffered_interiors = [interior.buffer(-distance, join_style=2) for interior in poly.interiors]

            # Subtract the buffered interiors from the buffered exterior
            result = buffered_exterior.difference(unary_union(buffered_interiors))

            return result

        if isinstance(geometry, Polygon):
            return buffer_polygon(geometry)
        elif isinstance(geometry, MultiPolygon):
                buffered_polys = [buffer_polygon(poly) for poly in geometry.geoms]
                return unary_union(buffered_polys)

    def get_combined_geltungsbereich(self):
        if not hasattr(self, 'geltungsbereich_geometries'):
                self.create_geltungsbereich_layers()
        return unary_union(list(self.geltungsbereich_geometries.values()))

    def create_geltungsbereich_layers(self):
        log_info("Starting to create Geltungsbereich layers...")
        self.geltungsbereich_geometries = {}
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
                        coverage_geometry = filtered_gdf.unary_union
                    else:
                        coverage_geometry = coverage_geometry.intersection(filtered_gdf.unary_union)
                
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
                    clip_shapefile = self.resolve_full_path(clip_layer['shapeFile'])
                    clip_gdf = gpd.read_file(clip_shapefile)
                    
                    if clip_layer['bufferDistance'] > 0:
                        clip_geometry = clip_gdf.geometry.buffer(clip_layer['bufferDistance'], join_style=2).unary_union
                    else:
                        clip_geometry = clip_gdf.geometry.unary_union
                    
                    combined_geometry = combined_geometry.difference(clip_geometry)
                
                self.geltungsbereich_geometries[geltungsbereich['layerName']] = combined_geometry
                log_info(f"Created Geltungsbereich layer: {geltungsbereich['layerName']}")
            else:
                log_warning(f"Warning: No geometry created for Geltungsbereich layer: {geltungsbereich['layerName']}")
        
        log_info("Finished creating Geltungsbereich layers.")

    def create_offset_layers(self, base_geometries):
        log_info("Starting to create offset layers...")
        self.offset_geometries = {}
        for layer in self.offset_layers:
            layer_name = layer['name']
            layer_to_offset = layer['layerToOffset']
            offset_distance = layer['offsetDistance']

            if self.has_corresponding_layer(layer_name):
                log_info(f"Processing offset layer: {layer_name}")
                log_info(f"Layer to offset: {layer_to_offset}")
                log_info(f"Offset distance: {offset_distance}")

                if layer_to_offset not in base_geometries:
                    log_warning(f"Warning: Base layer '{layer_to_offset}' not found in loaded geometries")
                    continue

                offset_geometries = []
                for base_geometry in base_geometries[layer_to_offset]:
                    log_info(f"Processing geometry: {base_geometry.geom_type}")
                    try:
                        if isinstance(base_geometry, (Polygon, MultiPolygon)):
                            # Create positive and negative buffers
                            outer_buffer = base_geometry.buffer(offset_distance, join_style=2)
                            inner_buffer = base_geometry.buffer(-offset_distance, join_style=2)
                            
                            # Extract the boundaries
                            outer_boundary = outer_buffer.boundary
                            inner_boundary = inner_buffer.boundary if not inner_buffer.is_empty else None
                            
                            # Add boundaries to offset geometries
                            offset_geometries.append(outer_boundary)
                            if inner_boundary:
                                offset_geometries.append(inner_boundary)
                        elif isinstance(base_geometry, (LineString, MultiLineString)):
                            right_offset = base_geometry.parallel_offset(offset_distance, 'right', join_style=2)
                            left_offset = base_geometry.parallel_offset(offset_distance, 'left', join_style=2)
                            offset_geometries.extend([right_offset, left_offset])
                        else:
                            log_warning(f"Warning: Unsupported geometry type for offset: {base_geometry.geom_type}")
                    except Exception as e:
                        log_error(f"Error creating offset for geometry: {str(e)}")

                if offset_geometries:
                    # Combine all offset geometries into a single MultiLineString
                    combined_offset = unary_union(offset_geometries)
                    if not isinstance(combined_offset, MultiLineString):
                        combined_offset = MultiLineString([combined_offset])
                    self.offset_geometries[layer_name] = combined_offset
                    log_info(f"Created offset geometry for layer: {layer_name}")
                else:
                    log_warning(f"Warning: No valid offset geometries created for layer '{layer_name}'")
            else:
                log_info(f"Skipping offset layer '{layer_name}' as it has no corresponding entry in 'dxfLayers'")

        log_info("Finished creating offset layers.")

    def update_layer_info(self, layer_name, shapefile_path, layer_info):
        # Update project settings
        new_layer = {
            'name': layer_name,
            'shapeFile': shapefile_path,
            'color': layer_info.get('color', "Light Green"),
            'close': layer_info.get('close', True),
            'locked': layer_info.get('locked', False)
        }
        self.project_settings['dxfLayers'].append(new_layer)

        # Update layer properties
        self.add_layer_properties(layer_name, new_layer)

        log_info(f"Updated project settings and layer properties for: {layer_name}")

    def process_layers(self, layers_to_process=None):
        try:
            doc = ezdxf.readfile(self.dxf_filename)
            log_info(f"Opened existing DXF file: {self.dxf_filename}")
        except FileNotFoundError:
            log_info(f"DXF file not found. Creating a new file: {self.dxf_filename}")
            doc = ezdxf.new('R2018')  # Create a new DXF document
            doc.header['$INSUNITS'] = 6  # Set units to meters

        self.doc = doc  # Store the doc object in the class instance
        msp = doc.modelspace()

        # Update this part to use the actual WMTS layer names
        wmts_layers = [wmts['name'] for wmts in self.wmts]
        other_layers = [layer['name'] for layer in self.project_settings['dxfLayers']]
        
        # Only include exclusion layers that have corresponding entries in 'dxfLayers'
        exclusion_layers = [exc['name'] for exc in self.exclusions if self.has_corresponding_layer(exc['name'])]
    
        buffer_distance_layers = [layer['name'] for layer in self.buffer_distance_layers if self.has_corresponding_layer(layer['name'])]
        clip_distance_layers = [layer['name'] for layer in self.clip_distance_layers if self.has_corresponding_layer(layer['name'])]
        
        geltungsbereich_layers = [layer['layerName'] for layer in self.geltungsbereich_layers]
        offset_layers = [layer['name'] for layer in self.offset_layers if self.has_corresponding_layer(layer['name'])]
        
        all_layers = wmts_layers + other_layers + exclusion_layers + buffer_distance_layers + clip_distance_layers + geltungsbereich_layers + offset_layers

        layers_to_process = layers_to_process or all_layers

        log_info("Layers to process:", layers_to_process)

        # Process layers in the order they appear in all_layers
        for layer in all_layers:
            if layer in layers_to_process:
                log_info(f"Processing layer: {layer}")
                self.process_single_layer(msp, layer)

        # Add buffer geometries to their respective layers
        for layer_name, geometry in self.buffer_geometries.items():
            if self.has_corresponding_layer(layer_name):
                log_info(f"Adding buffer geometry to layer: {layer_name}")
                self.add_geometries(msp, geometry, layer_name, close=self.layer_properties[layer_name]['close'])

        # Add offset geometries to their respective layers
        for layer_name, geometry in self.offset_geometries.items():
            if layers_to_process is None or layer_name in layers_to_process:
                log_info(f"Processing offset layer: {layer_name}")
                log_info(f"Offset geometry type: {geometry.geom_type}")
                log_info(f"Offset geometry is valid: {geometry.is_valid}")
                log_info(f"Offset geometry is empty: {geometry.is_empty}")
                close = self.layer_properties[layer_name].get('close', True)
                self.add_geometries(msp, geometry, layer_name, close=close)

        return doc

    def main(self):
        log_info(f"Starting processing for project: {self.project_settings['name']}")
        self.create_geltungsbereich_layers()
        self.create_clip_distance_layers()
        self.create_buffer_distance_layers()
        
        # Dictionary to store geometries of all layers
        all_geometries = {}

        # Load geometries for all layers
        for layer in self.project_settings['dxfLayers']:
            if 'shapeFile' in layer:
                shapefile_path = self.resolve_full_path(layer['shapeFile'])
                if os.path.exists(shapefile_path):
                    gdf = gpd.read_file(shapefile_path)
                    all_geometries[layer['name']] = gdf.geometry.tolist()
                else:
                    log_warning(f"Warning: Shapefile not found for layer '{layer['name']}': {shapefile_path}")

        # Create offset layers using pre-loaded geometries
        self.create_offset_layers(all_geometries)
        
        # Process exclusions
        self.exclusion_geometries = {}
        for exclusion in self.exclusions:
            if self.has_corresponding_layer(exclusion['name']):
                self.create_exclusion_polygon(exclusion)
        
        doc = self.process_layers(self.update_layers_list)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.dxf_filename), exist_ok=True)

        if self.export_format == 'dwg':
            log_info(f"Exporting to DWG: {self.dxf_filename.replace('.dxf', '.dwg')}")
            doc.header['$PROJECTNAME'] = ''
            odafc.export_dwg(doc, self.dxf_filename.replace('.dxf', '.dwg'))
        else:
            log_info(f"Saving DXF file: {self.dxf_filename}")
            doc.saveas(self.dxf_filename)

        log_info("Processing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process project data.")
    parser.add_argument("project_name", help="Name of the project to process")
    parser.add_argument("-u", "--update", help="Update specific layers (comma-separated list)")
    args = parser.parse_args()

    try:
        processor = ProjectProcessor(args.project_name)
        processor.update_layers_list = args.update.split(',') if args.update else None
        processor.main()
    except ValueError as e:
        log_error(e)




