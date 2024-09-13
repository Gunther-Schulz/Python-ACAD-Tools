import random
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
from src.utils import log_info, log_warning, log_error
import geopandas as gpd
import os
from ezdxf.lldxf.const import DXFValueError

class DXFExporter:
    def __init__(self, project_loader, layer_processor):
        self.project_loader = project_loader
        self.layer_processor = layer_processor
        self.project_settings = project_loader.project_settings
        self.dxf_filename = project_loader.dxf_filename
        self.all_layers = layer_processor.all_layers
        self.layer_properties = {}
        self.colors = {}
        self.name_to_aci = project_loader.name_to_aci
        self.script_identifier = "Created by DXFExporter"
        log_info(f"DXFExporter initialized with script identifier: {self.script_identifier}")
        self.setup_layers()

    def setup_layers(self):
        self.layer_properties = {}
        self.colors = {}

        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)
            color_code = self.get_color_code(layer.get('color', 'White'))  # Default to White if color is not specified
            text_color_code = self.get_color_code(layer.get('textColor', layer.get('color', 'White')))
            self.colors[layer['name']] = color_code
            
            # Only add label layer if it's not a WMTS layer
            if not self.is_wmts_layer(layer):
                self.colors[f"{layer['name']} Label"] = text_color_code

    def remove_unused_entities(self, msp, processed_layers):
        log_info("Removing unused entities...")
        removed_count = 0
        for entity in msp:
            if (entity.dxf.layer in processed_layers and 
                entity.dxf.layer not in self.layer_properties and
                self.is_created_by_script(entity)):
                msp.delete_entity(entity)
                removed_count += 1
        log_info(f"Removed {removed_count} unused entities from processed layers")

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
        
        # Load existing DXF file or create a new one
        if os.path.exists(self.dxf_filename):
            doc = ezdxf.readfile(self.dxf_filename)
            log_info(f"Loaded existing DXF file: {self.dxf_filename}")
            self.load_existing_layers(doc)
            self.check_existing_entities(doc)
        else:
            doc = ezdxf.new(dxfversion=dxf_version)
            log_info(f"Created new DXF file with version: {dxf_version}")
            self.set_drawing_properties(doc)
            self.load_standard_linetypes(doc)
        
        msp = doc.modelspace()

        # Process layers
        self.process_layers(doc, msp)

        # Get the list of layers we're processing
        processed_layers = [layer['name'] for layer in self.project_settings['dxfLayers']]

        # Remove unused entities only from processed layers
        self.remove_unused_entities(msp, processed_layers)

        # Save the DXF file
        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")

        # Verify settings
        self.verify_dxf_settings()

    def set_drawing_properties(self, doc):
        doc.header['$INSUNITS'] = 6  # Meters
        doc.header['$MEASUREMENT'] = 1  # Metric
        doc.header['$LUNITS'] = 2  # Decimal
        doc.header['$AUNITS'] = 0  # Degrees
        doc.header['$ANGBASE'] = 0  # 0 degrees

    def load_existing_layers(self, doc):
        for layer in doc.layers:
            layer_name = layer.dxf.name
            if layer_name not in self.all_layers:
                # Store the layer entity in all_layers
                self.all_layers[layer_name] = layer
                log_info(f"Loaded existing layer: {layer_name}")

    def process_layers(self, doc, msp):
        for layer_info in self.project_settings['dxfLayers']:
            layer_name = layer_info['name']
            
            # Only process layers that are explicitly set to be added or updated
            if layer_info.get('update', False):
                self.process_single_layer(doc, msp, layer_name, layer_info)

    def process_single_layer(self, doc, msp, layer_name, layer_info):
        update_flag = layer_info.get('update', False)
        log_info(f"Processing layer: {layer_name}")
        log_info(f"Update flag: {update_flag}")

        if not update_flag:
            log_info(f"Skipping layer {layer_name} as 'update' flag is not set")
            return

        if self.is_wmts_layer(layer_info):
            log_info(f"Processing WMTS layer: {layer_name}")
            self.create_new_layer(doc, msp, layer_name, layer_info)
        else:
            if layer_name not in doc.layers:
                log_info(f"Creating new layer: {layer_name}")
                self.create_new_layer(doc, msp, layer_name, layer_info, add_geometry=False)
            else:
                existing_layer = doc.layers.get(layer_name)
                self.update_layer_properties(existing_layer, layer_info)
                log_info(f"Layer {layer_name} already exists. Updating properties.")
            
            if layer_name in self.all_layers:
                self.update_layer_geometry(msp, layer_name, self.all_layers[layer_name], layer_info)

    def verify_dxf_settings(self):
        loaded_doc = ezdxf.readfile(self.dxf_filename)
        print(f"INSUNITS after load: {loaded_doc.header['$INSUNITS']}")
        print(f"LUNITS after load: {loaded_doc.header['$LUNITS']}")
        print(f"LUPREC after load: {loaded_doc.header['$LUPREC']}")
        print(f"AUPREC after load: {loaded_doc.header['$AUPREC']}")

    def update_layer_geometry(self, msp, layer_name, geo_data, layer_config):
        update_flag = layer_config.get('update', False)
        
        log_info(f"Updating layer geometry for {layer_name}. Update flag: {update_flag}")
        
        if not update_flag:
            log_info(f"Skipping geometry update for layer {layer_name} as 'update' flag is not set")
            return

        # Always remove existing entities if update flag is set
        log_info(f"Removing existing entities for layer {layer_name}")
        entities_to_delete = [entity for entity in msp.query(f'*[layer=="{layer_name}"]') if self.is_created_by_script(entity)]
        
        delete_count = 0
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
                delete_count += 1
            except Exception as e:
                log_error(f"Error deleting entity: {e}")
        
        log_info(f"Removed {delete_count} entities from layer {layer_name}")

        # Add new geometry and labels
        log_info(f"Adding new geometry to layer {layer_name}")
        if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
            self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
        else:
            self.add_geometries_to_dxf(msp, geo_data, layer_name)

        # Verify hyperlinks after adding new entities
        self.verify_entity_hyperlinks(msp, layer_name)

    def create_new_layer(self, doc, msp, layer_name, layer_info, existing_layer=None, add_geometry=True):
        if existing_layer:
            layer = existing_layer
            log_info(f"Using existing layer: {layer_name}")
        else:
            layer = doc.layers.new(name=layer_name)
            log_info(f"Created new layer: {layer_name}")
        
        self.update_layer_properties(layer, layer_info)
        
        log_info(f"Final layer properties: {layer.dxf.all_existing_dxf_attribs()}")

        if not self.is_wmts_layer(layer_name):
            text_layer_name = f"{layer_name} Label"
            if text_layer_name not in doc.layers:
                text_layer = doc.layers.new(name=text_layer_name)
                text_properties = self.layer_properties.get(text_layer_name, {})
                for key, value in text_properties.items():
                    setattr(text_layer, key, value)
                log_info(f"Created text layer: {text_layer_name}")
                log_info(f"  Text layer properties: {text_properties}")

        if add_geometry and (not existing_layer or layer_info.get('update', False)):
            geo_data = self.all_layers.get(layer_name)
            if geo_data is not None:
                self.add_geometries_to_dxf(msp, geo_data, layer_name)
            else:
                log_info(f"No geometry data available for layer: {layer_name}")

    def update_layer_properties(self, layer, layer_info):
        log_info(f"Updating properties for layer: {layer.dxf.name}")
        log_info(f"Layer info: {layer_info}")
        log_info(f"Current layer properties: {layer.dxf.all_existing_dxf_attribs()}")
        
        if 'color' in layer_info:
            layer.color = self.get_color_code(layer_info['color'])
            log_info(f"  Set color to: {layer.color}")
        if 'linetype' in layer_info:
            linetype_name = layer_info['linetype']
            if linetype_name not in layer.doc.linetypes:
                log_warning(f"  Linetype '{linetype_name}' not found. Using 'CONTINUOUS' instead.")
                linetype_name = 'CONTINUOUS'
            layer.dxf.linetype = linetype_name
            log_info(f"  Set linetype to: {linetype_name}")
        if 'lineweight' in layer_info:
            layer.dxf.lineweight = layer_info['lineweight']
            log_info(f"  Set lineweight to: {layer_info['lineweight']}")
        if 'plot' in layer_info:
            layer.dxf.plot = layer_info['plot']
            log_info(f"  Set plot to: {layer_info['plot']}")
        if 'locked' in layer_info:
            layer.dxf.flags = layer.dxf.flags | 4 if layer_info['locked'] else layer.dxf.flags & ~4
            log_info(f"  Set locked to: {layer_info['locked']}")
        if 'frozen' in layer_info:
            layer.dxf.flags = layer.dxf.flags | 1 if layer_info['frozen'] else layer.dxf.flags & ~1
            log_info(f"  Set frozen to: {layer_info['frozen']}")
        if 'is_on' in layer_info:
            layer.is_on = layer_info['is_on']
            log_info(f"  Set is_on to: {layer.is_on}")
        if 'vp_freeze' in layer_info:
            layer.dxf.flags = layer.dxf.flags | 8 if layer_info['vp_freeze'] else layer.dxf.flags & ~8
            log_info(f"  Set vp_freeze to: {layer_info['vp_freeze']}")
        if 'transparency' in layer_info:
            layer.transparency = int(layer_info['transparency'] * 100)
            log_info(f"  Set transparency to: {layer.transparency}")
        
        log_info(f"Final layer properties after update: {layer.dxf.all_existing_dxf_attribs()}")

    def load_standard_linetypes(self, doc):
        standard_linetypes = [
            'CONTINUOUS', 'CENTER', 'DASHED', 'PHANTOM', 'HIDDEN', 'DASHDOT',
            'BORDER', 'DIVIDE', 'DOT', 'ACAD_ISO02W100', 'ACAD_ISO03W100',
            'ACAD_ISO04W100', 'ACAD_ISO05W100', 'ACAD_ISO06W100', 'ACAD_ISO07W100',
            'ACAD_ISO08W100', 'ACAD_ISO09W100', 'ACAD_ISO10W100', 'ACAD_ISO11W100',
            'ACAD_ISO12W100', 'ACAD_ISO13W100', 'ACAD_ISO14W100', 'ACAD_ISO15W100'
        ]
        for lt in standard_linetypes:
            if lt not in doc.linetypes:
                doc.linetypes.new(lt)

    def attach_custom_data(self, entity):
        """Attach custom data to identify entities created by this script."""
        if hasattr(entity, 'set_hyperlink'):
            try:
                entity.set_hyperlink(self.script_identifier)
                log_info(f"Attached custom data to entity: {entity}")
                # Verify the hyperlink was set correctly
                if hasattr(entity, 'get_hyperlink'):
                    set_value = entity.get_hyperlink()
                    log_info(f"Verified hyperlink for {entity}: {set_value}")
                    if set_value != self.script_identifier and set_value != (self.script_identifier, '', ''):
                        log_warning(f"Hyperlink mismatch for {entity}. Expected: {self.script_identifier}, Got: {set_value}")
                else:
                    log_warning(f"Entity {entity} has set_hyperlink but not get_hyperlink method")
            except Exception as e:
                log_error(f"Error setting hyperlink for entity {entity}: {str(e)}")
        else:
            log_warning(f"Unable to attach custom data to entity: {entity}. No 'set_hyperlink' method.")

    def is_created_by_script(self, entity):
        """Check if an entity was created by this script."""
        if hasattr(entity, 'get_hyperlink'):
            try:
                hyperlink = entity.get_hyperlink()
                is_created = hyperlink == self.script_identifier or (
                    isinstance(hyperlink, tuple) and 
                    len(hyperlink) > 0 and 
                    hyperlink[0] == self.script_identifier
                )
                return is_created
            except Exception as e:
                log_error(f"Error getting hyperlink for entity {entity}: {str(e)}")
                return False
        log_warning(f"Unable to check if entity was created by script: {entity}. No 'get_hyperlink' method.")
        return False

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
        self.attach_custom_data(image)

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

        print(f"add_geometries_to_dxf Layer Name: {layer_name}")
        for idx, geometry in enumerate(geometries):
            if isinstance(geometry, LineString):
                self.add_linestring_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, MultiLineString):
                for line in geometry.geoms:
                    self.add_linestring_to_dxf(msp, line, layer_name)
            else:
                self.add_geometry_to_dxf(msp, geometry, layer_name)

            if labels is not None:
                self.add_label_to_dxf(msp, geometry, labels.iloc[idx], layer_name)
            elif self.is_generated_layer(layer_name):
                self.add_label_to_dxf(msp, geometry, layer_name, layer_name)

    def add_polygon_to_dxf(self, msp, geometry, layer_name):
        log_info(f"Adding polygon to layer {layer_name}")
        if isinstance(geometry, Polygon):
            polygons = [geometry]
        elif isinstance(geometry, MultiPolygon):
            polygons = list(geometry.geoms)
        else:
            return

        for polygon in polygons:
            exterior_coords = list(polygon.exterior.coords)
            if len(exterior_coords) > 2:
                polyline = msp.add_lwpolyline(exterior_coords, dxfattribs={
                    'layer': layer_name, 
                    'closed': self.layer_properties[layer_name]['close']
                })
                self.attach_custom_data(polyline)
                log_info(f"Added polygon to layer {layer_name}: {polyline}")

            for interior in polygon.interiors:
                interior_coords = list(interior.coords)
                if len(interior_coords) > 2:
                    polyline = msp.add_lwpolyline(interior_coords, dxfattribs={
                        'layer': layer_name, 
                        'closed': self.layer_properties[layer_name]['close']
                    })
                    self.attach_custom_data(polyline)
                    log_info(f"Added polygon interior to layer {layer_name}: {polyline}")

    def add_linestring_to_dxf(self, msp, linestring, layer_name):
        points = list(linestring.coords)
        log_info(f"Adding linestring to layer {layer_name} with {len(points)} points")
        log_info(f"First point: {points[0][:2] if points else 'No points'}")

        try:
            # Extract only x and y coordinates
            points_2d = [(p[0], p[1]) for p in points]
            
            polyline = msp.add_lwpolyline(
                points=points_2d,
                dxfattribs={
                    'layer': layer_name,
                    'closed': False,
                }
            )
            
            # Set constant width to 0
            polyline.dxf.const_width = 0
            
            self.attach_custom_data(polyline)
            log_info(f"Successfully added polyline to layer {layer_name}")
            log_info(f"Polyline properties: {polyline.dxf.all_existing_dxf_attribs()}")
        except Exception as e:
            log_error(f"Error adding polyline to layer {layer_name}: {str(e)}")
            log_error(f"Points causing error: {points_2d}")

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
        properties = {
            'color': self.get_color_code(layer_info.get('color', 'White')),
            'textColor': self.get_color_code(layer_info.get('textColor', layer_info.get('color', 'White'))),
            'linetype': layer_info.get('linetype', 'Continuous'),
            'lineweight': layer_info.get('lineweight', 13),
            'plot': layer_info.get('plot', True),
            'locked': layer_info.get('locked', False),
            'frozen': layer_info.get('frozen', False),
            'is_on': layer_info.get('is_on', True),
            'vp_freeze': layer_info.get('vp_freeze', False),
            'transparency': layer_info.get('transparency', 0.0),
            'close': layer_info.get('close', True),
            'close_linestring': layer_info.get('close_linestring', False)  # New property
        }
        self.layer_properties[layer_name] = properties
        
        # Only add label layer properties if it's not a WMTS layer
        if not self.is_wmts_layer(layer_info):
            text_layer_name = f"{layer_name} Label"
            text_properties = {
                'color': properties['textColor'],
                'plot': properties['plot'],
                'locked': properties['locked'],
                'frozen': properties['frozen'],
                'is_on': properties['is_on'],
                'vp_freeze': properties['vp_freeze'],
                'close': properties['close']
            }
            self.layer_properties[text_layer_name] = text_properties

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
        log_info(f"Adding text to layer {layer_name}")
        text_layer_name = f"{layer_name} Label"
        text_color = self.layer_properties[layer_name].get('textColor', self.layer_properties[layer_name]['color'])
        text_entity = msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': text_layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1,
            'color': text_color
        })
        self.attach_custom_data(text_entity)
        log_info(f"Added text to layer {layer_name}: {text_entity}")

    def add_geometry_to_dxf(self, msp, geometry, layer_name):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            self.add_polygon_to_dxf(msp, geometry, layer_name)
        elif isinstance(geometry, LineString):
            self.add_linestring_to_dxf(msp, geometry, layer_name)
        elif isinstance(geometry, MultiLineString):
            for line in geometry.geoms:
                self.add_linestring_to_dxf(msp, line, layer_name)
        elif isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                self.add_geometry_to_dxf(msp, geom, layer_name)
        else:
            log_warning(f"Unsupported geometry type for layer {layer_name}: {type(geometry)}")

    def verify_entity_hyperlinks(self, msp, layer_name):
        log_info(f"Verifying hyperlinks for entities in layer {layer_name}")
        for entity in msp.query(f'*[layer=="{layer_name}"]'):
            if hasattr(entity, 'get_hyperlink'):
                hyperlink = entity.get_hyperlink()
            else:
                log_warning(f"Entity {entity} in layer {layer_name} has no 'get_hyperlink' method")

    def check_existing_entities(self, doc):
        log_info("Checking existing entities in the DXF file")
        for entity in doc.modelspace():
            if hasattr(entity, 'get_hyperlink'):
                hyperlink = entity.get_hyperlink()
            else:
                log_info(f"Entity {entity} has no 'get_hyperlink' method")
