import random
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
from src.utils import log_info, log_warning, log_error
import geopandas as gpd
import os

class DXFExporter:
    def __init__(self, project_loader, layer_processor):
        self.project_loader = project_loader
        self.layer_processor = layer_processor
        self.project_settings = project_loader.project_settings
        self.dxf_filename = project_loader.dxf_filename
        self.all_layers = layer_processor.all_layers
        self.update_layers_list = layer_processor.update_layers_list
        self.layer_properties = {}
        self.colors = {}
        self.name_to_aci = project_loader.name_to_aci
        self.setup_layers()

    def setup_layers(self):
        self.layer_properties = {}
        self.colors = {}

        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)
            color_code = self.get_color_code(layer['color'])
            text_color_code = self.get_color_code(layer.get('textColor', layer['color']))
            self.colors[layer['name']] = color_code
            
            # Only add label layer if it's not a WMTS layer
            if not self.is_wmts_layer(layer):
                self.colors[f"{layer['name']} Label"] = text_color_code

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
        
        # Check if a DXF file already exists
        if os.path.exists(self.dxf_filename):
            doc = ezdxf.readfile(self.dxf_filename)
            log_info(f"Loaded existing DXF file: {self.dxf_filename}")
        else:
            doc = ezdxf.new(dxfversion=dxf_version)
            log_info(f"Created new DXF file with version: {dxf_version}")
        
        msp = doc.modelspace()

        # Set drawing properties only if it's a new file
        if not os.path.exists(self.dxf_filename):
            doc.header['$INSUNITS'] = 6  # Meters
            doc.header['$LUNITS'] = 2    # Decimal
            doc.header['$LUPREC'] = 4    # Linear display precision
            doc.header['$AUPREC'] = 4    # Angular display precision
            doc.header['$MEASUREMENT'] = 1

            # Set drawing units using acad_units method
            doc.units = 6
            msp.units = 6

        for layer_name, geo_data in self.all_layers.items():
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

            # Check if the layer should be included
            layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
            if layer_info is None or layer_info.get('include', True) == False:
                log_info(f"Skipping layer {layer_name} as it is set to not be included")
                continue

            # Check if the layer already exists
            if layer_name in doc.layers:
                log_info(f"Layer {layer_name} already exists. Updating geometry and labels only.")
                self.update_layer_geometry(msp, layer_name, geo_data)
            else:
                log_info(f"Creating new layer: {layer_name}")
                self.create_new_layer(doc, msp, layer_name, geo_data)

        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")

        loaded_doc = ezdxf.readfile(self.dxf_filename)
        loaded_msp = loaded_doc.modelspace()

        # Print out the settings to verify
        print(f"INSUNITS after load: {loaded_doc.header['$INSUNITS']}")
        print(f"LUNITS after load: {loaded_doc.header['$LUNITS']}")
        print(f"LUPREC after load: {loaded_doc.header['$LUPREC']}")
        print(f"AUPREC after load: {loaded_doc.header['$AUPREC']}")

    def update_layer_geometry(self, msp, layer_name, geo_data):
        # Remove existing entities for this layer
        for entity in msp.query(f'*[layer=="{layer_name}"]'):
            msp.delete_entity(entity)
        for entity in msp.query(f'*[layer=="{layer_name} Label"]'):
            msp.delete_entity(entity)

        # Add new geometry and labels
        if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
            self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
        else:
            self.add_geometries_to_dxf(msp, geo_data, layer_name)

    def create_new_layer(self, doc, msp, layer_name, geo_data):
        layer_properties = self.layer_properties.get(layer_name, {})
        color = layer_properties.get('color', 7)  # Default to white if color not specified
        linetype = 'CONTINUOUS'
        
        # Create the layer if it doesn't exist
        if layer_name not in doc.layers:
            layer = doc.layers.new(name=layer_name)
            layer.color = color
            layer.linetype = linetype

        # Create the text layer only if it's not a WMTS layer and doesn't already exist
        if not self.is_wmts_layer(layer_name):
            text_layer_name = f"{layer_name} Label"
            if text_layer_name not in doc.layers:
                text_layer = doc.layers.new(name=text_layer_name)
                text_layer.color = color
                text_layer.linetype = linetype

        # Add geometry and labels
        if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
            self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
        else:
            self.add_geometries_to_dxf(msp, geo_data, layer_name)

    def add_wmts_xrefs_to_dxf(self, msp, tile_data, layer_name):
        log_info(f"Adding WMTS xrefs to DXF for layer: {layer_name}")
        
        for image_path, world_file_path in tile_data:
            self.add_image_with_worldfile(msp, image_path, world_file_path, layer_name)

        log_info(f"Added {len(tile_data)} WMTS xrefs to layer: {layer_name}")

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
        log_info(f"Adding image with worldfile for layer: {layer_name}")
        log_info(f"Image path: {image_path}")
        log_info(f"World file path: {world_file_path}")

        # Ensure the layer exists with proper properties
        if layer_name not in self.layer_properties:
            self.add_layer_properties(layer_name, {
                'color': "White",
                'locked': False,
                'close': True
            })

        # Convert Unix-style path to Windows-style path
        def convert_to_windows_path(path):
            return path.replace('/', '\\')

        # Create a relative path for the image and convert to Windows style
        relative_image_path = os.path.relpath(
            image_path, os.path.dirname(self.dxf_filename))
        relative_image_path = convert_to_windows_path(relative_image_path)
        log_info(f"Relative image path: {relative_image_path}")

        # Create the image definition with the relative Windows-style path
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
        log_info(f"World file parameters: a={a}, d={d}, b={b}, e={e}, c={c}, f={f}")

        # Calculate the insertion point and size
        insert_point = (c, f - abs(e) * 256)
        size_in_units = (a * 256, abs(e) * 256)
        log_info(f"Insertion point: {insert_point}")
        log_info(f"Size in units: {size_in_units}")

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
        
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), {})
        
        if self.is_wmts_layer(layer_name):
            self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
            return

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
            self.add_geometry_to_dxf(msp, geometry, layer_name)
            
            if labels is not None:
                self.add_label_to_dxf(msp, geometry, labels.iloc[idx], layer_name)
            elif self.is_generated_layer(layer_name):
                self.add_label_to_dxf(msp, geometry, layer_name, layer_name)

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

    def initialize_layer_properties(self):
        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)

    def add_layer_properties(self, layer_name, layer_info):
        color = self.get_color_code(layer_info.get('color', 'White'))
        text_color = self.get_color_code(layer_info.get('textColor', layer_info.get('color', 'White')))
        self.layer_properties[layer_name] = {
            'color': color,
            'textColor': text_color,
            'locked': layer_info.get('locked', False),
            'close': layer_info.get('close', True)
        }
        
        # Only add label layer properties if it's not a WMTS layer
        if not self.is_wmts_layer(layer_name):
            text_layer_name = f"{layer_name} Label"
            self.layer_properties[text_layer_name] = {
                'color': text_color,
                'textColor': text_color,  # Ensure textColor is set for label layers
                'locked': layer_info.get('locked', False),
                'close': True
            }

    def is_wmts_layer(self, layer_name):
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
        if layer_info and 'operations' in layer_info:
            return any(op['type'] == 'wmts' for op in layer_info['operations'])
        return False
    
    def is_generated_layer(self, layer_name):
        # Check if the layer is generated (has an operation) and not loaded from a shapefile
        for layer in self.project_settings['dxfLayers']:
            if layer['name'] == layer_name:
                return 'operation' in layer and 'shapeFile' not in layer
        return False
    
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
        
    def get_label_column(self, layer_name):
        for layer in self.project_settings['dxfLayers']:
            if layer['name'] == layer_name and 'label' in layer:
                return layer['label']
        return None
    
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
        text_layer_name = f"{layer_name} Label"
        text_color = self.layer_properties[layer_name].get('textColor', self.layer_properties[layer_name]['color'])
        msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': text_layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1,
            'color': text_color
        })

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