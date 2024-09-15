import random
import shutil
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
        for layer in self.project_settings['dxfLayers']:
            self._setup_single_layer(layer)

    def _setup_single_layer(self, layer):
        layer_name = layer['name']
        self.add_layer_properties(layer_name, layer)
        
        if not self.is_wmts_layer(layer) and not layer_name.endswith(' Label'):
            self._setup_label_layer(layer_name, layer)

    def _setup_label_layer(self, base_layer_name, base_layer):
        label_layer_name = f"{base_layer_name} Label"
        label_properties = self.layer_properties[base_layer_name].copy()
        
        style = base_layer.get('style', {})
        if 'labelColor' in style:
            label_properties['color'] = self.get_color_code(style['labelColor'])
        
        self.layer_properties[label_layer_name] = label_properties
        self.colors[label_layer_name] = label_properties['color']

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        doc = self._prepare_dxf_document()
        msp = doc.modelspace()

        self.process_layers(doc, msp)
        self._cleanup_and_save(doc, msp)

    def _prepare_dxf_document(self):
        self._backup_existing_file()
        doc = self._load_or_create_dxf()
        return doc

    def _backup_existing_file(self):
        if os.path.exists(self.dxf_filename):
            backup_filename = f"{self.dxf_filename}.ezdxf_bak"
            shutil.copy2(self.dxf_filename, backup_filename)
            log_info(f"Created backup of existing DXF file: {backup_filename}")

    def _load_or_create_dxf(self):
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
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
        return doc

    def load_existing_layers(self, doc):
        log_info("Loading existing layers from DXF file")
        for layer in doc.layers:
            layer_name = layer.dxf.name
            if layer_name not in self.layer_properties:
                self.layer_properties[layer_name] = {
                    'color': layer.color,
                    'linetype': layer.dxf.linetype,
                    'lineweight': layer.dxf.lineweight,
                    'plot': layer.dxf.plot,
                    'locked': layer.is_locked,
                    'frozen': layer.is_frozen,
                    'is_on': layer.is_on,
                    'transparency': layer.transparency
                }
                self.colors[layer_name] = layer.color
            log_info(f"Loaded existing layer: {layer_name}")

    def set_drawing_properties(self, doc):
        # Set drawing properties based on project settings
        # You may need to adjust this method based on your specific requirements
        doc.header['$INSUNITS'] = 6  # Assuming meters, adjust if needed
        doc.header['$LUNITS'] = 2  # Assuming decimal units
        doc.header['$LUPREC'] = 4  # Precision for linear units
        doc.header['$AUPREC'] = 4  # Precision for angular units
        log_info("Drawing properties set")

    def _cleanup_and_save(self, doc, msp):
        processed_layers = [layer['name'] for layer in self.project_settings['dxfLayers']]
        self.remove_unused_entities(msp, processed_layers)
        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")
        self.verify_dxf_settings()

    def process_layers(self, doc, msp):
        for layer_info in self.project_settings['dxfLayers']:
            if layer_info.get('update', False):
                self.process_single_layer(doc, msp, layer_info['name'], layer_info)

    def process_single_layer(self, doc, msp, layer_name, layer_info):
        log_info(f"Processing layer: {layer_name}")
        
        if self.is_wmts_layer(layer_info):
            self._process_wmts_layer(doc, msp, layer_name, layer_info)
        else:
            self._process_regular_layer(doc, msp, layer_name, layer_info)

    def _process_wmts_layer(self, doc, msp, layer_name, layer_info):
        log_info(f"Processing WMTS layer: {layer_name}")
        self.create_new_layer(doc, msp, layer_name, layer_info)

    def _process_regular_layer(self, doc, msp, layer_name, layer_info):
        self._ensure_layer_exists(doc, layer_name, layer_info)
        self._ensure_label_layer_exists(doc, layer_name, layer_info)
        
        if layer_name in self.all_layers:
            self.update_layer_geometry(msp, layer_name, self.all_layers[layer_name], layer_info)

    def _ensure_layer_exists(self, doc, layer_name, layer_info):
        if layer_name not in doc.layers:
            self.create_new_layer(doc, None, layer_name, layer_info, add_geometry=False)
        else:
            self.update_layer_properties(doc.layers.get(layer_name), layer_info)

    def _ensure_label_layer_exists(self, doc, base_layer_name, layer_info):
        label_layer_name = f"{base_layer_name} Label"
        if label_layer_name not in doc.layers:
            self.create_new_layer(doc, None, label_layer_name, layer_info, add_geometry=False)
        else:
            self.update_layer_properties(doc.layers.get(label_layer_name), layer_info)

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

        # Remove existing entities for both the main layer and its label layer
        layers_to_clear = [layer_name]
        if not layer_name.endswith(' Label'):
            layers_to_clear.append(f"{layer_name} Label")

        for layer in layers_to_clear:
            log_info(f"Removing existing entities for layer {layer}")
            entities_to_delete = [entity for entity in msp.query(f'*[layer=="{layer}"]') if self.is_created_by_script(entity)]
            
            delete_count = 0
            for entity in entities_to_delete:
                try:
                    msp.delete_entity(entity)
                    delete_count += 1
                except Exception as e:
                    log_error(f"Error deleting entity: {e}")
            
            log_info(f"Removed {delete_count} entities from layer {layer}")

        # Add new geometry and labels
        log_info(f"Adding new geometry to layer {layer_name}")
        if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
            self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
        else:
            self.add_geometries_to_dxf(msp, geo_data, layer_name)

        # Verify hyperlinks after adding new entities
        self.verify_entity_hyperlinks(msp, layer_name)
        if not layer_name.endswith(' Label'):
            self.verify_entity_hyperlinks(msp, f"{layer_name} Label")

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        log_info(f"Creating new layer: {layer_name}")
        properties = self.layer_properties[layer_name]
        
        new_layer = doc.layers.new(layer_name)
        new_layer.color = properties['color']
        new_layer.linetype = properties['linetype']
        new_layer.lineweight = properties['lineweight']
        new_layer.plot = properties['plot']
        new_layer.locked = properties['locked']
        new_layer.frozen = properties['frozen']
        new_layer.on = properties['is_on']
        
        if 'transparency' in properties:
            new_layer.transparency = int(properties['transparency'] * 100)
        
        log_info(f"Created new layer: {layer_name}")
        log_info(f"Layer properties: {properties}")
        
        if add_geometry and layer_name in self.all_layers:
            self.update_layer_geometry(msp, layer_name, self.all_layers[layer_name], layer_info)
        
        return new_layer

    def update_layer_properties(self, layer, layer_info):
        log_info(f"Updating properties for layer: {layer.dxf.name}")
        layer_name = layer.dxf.name
        properties = self.layer_properties[layer_name]
        
        layer.color = properties['color']
        layer.dxf.linetype = properties['linetype']
        layer.dxf.lineweight = properties['lineweight']
        layer.dxf.plot = properties['plot']
        layer.locked = properties['locked']
        layer.frozen = properties['frozen']
        layer.on = properties['is_on']
        
        if 'transparency' in properties:
            layer.transparency = int(properties['transparency'] * 100)
        
        log_info(f"Updated layer properties: {properties}")

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
                # Verify the hyperlink was set correctly
                if hasattr(entity, 'get_hyperlink'):
                    set_value = entity.get_hyperlink()
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
        close_linestring = self.layer_properties[layer_name].get('close_linestring', False)
        
        if close_linestring and points[0] != points[-1]:
            points.append(points[0])  # Close the linestring by adding the first point at the end
        
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

        text_layer_name = f"{layer_name} Label" if not layer_name.endswith(' Label') else layer_name
        self.add_text(msp, str(label), centroid.x, centroid.y, text_layer_name, 'Standard')

    def initialize_layer_properties(self):
        for layer in self.project_settings['dxfLayers']:
            self.add_layer_properties(layer['name'], layer)

    def add_layer_properties(self, layer_name, layer_info):
        style = layer_info.get('style', {})
        properties = {
            'color': self.get_color_code(style.get('color', 'White')),
            'linetype': style.get('linetype', 'Continuous'),
            'lineweight': style.get('lineweight', 13),
            'plot': style.get('plot', True),
            'locked': style.get('locked', False),
            'frozen': style.get('frozen', False),
            'is_on': style.get('is_on', True),
            'transparency': style.get('transparency', 0.0),
            'close': style.get('close', True),
            'close_linestring': style.get('close_linestring', False)
        }
        self.layer_properties[layer_name] = properties
        self.colors[layer_name] = properties['color']
        
        log_info(f"Added layer properties for {layer_name}: {properties}")

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
    
    def add_text(self, msp, text, x, y, layer_name, style_name):
        text_layer_name = f"{layer_name} Label" if not layer_name.endswith(' Label') else layer_name
        
        text_entity = msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': text_layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1
        })
        self.attach_custom_data(text_entity)

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
