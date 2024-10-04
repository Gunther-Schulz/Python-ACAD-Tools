import random
import shutil
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
from src.utils import log_info, log_warning, log_error
import geopandas as gpd
import os
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN



from PIL import Image

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
        self.viewports = {}

    def setup_layers(self):
        for layer in self.project_settings['dxfLayers']:
            self._setup_single_layer(layer)

    def _setup_single_layer(self, layer):
        layer_name = layer['name']
        self.add_layer_properties(layer_name, layer)
        
        if not self.is_wmts_or_wms_layer(layer) and not layer_name.endswith(' Label'):
            if self.has_labels(layer):
                self._setup_label_layer(layer_name, layer)

    def has_labels(self, layer):
        return 'label' in layer or 'labelStyle' in layer

    def _setup_label_layer(self, base_layer_name, base_layer):
        label_layer_name = f"{base_layer_name} Label"
        label_properties = self.layer_properties[base_layer_name].copy()
        
        style = base_layer.get('style', {})
        label_style = base_layer.get('labelStyle', {})
        
        # Apply label style properties, falling back to base style if not specified
        for key, value in label_style.items():
            if key == 'color':
                label_properties['color'] = self.get_color_code(value)
            else:
                label_properties[key] = value
        
        self.layer_properties[label_layer_name] = label_properties
        self.colors[label_layer_name] = label_properties['color']

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        doc = self._prepare_dxf_document()
        msp = doc.modelspace()
        self.register_app_id(doc)
        self.create_viewports(doc, msp)
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
        
        if self.is_wmts_or_wms_layer(layer_info):
            self._process_wmts_layer(doc, msp, layer_name, layer_info)
        else:
            self._process_regular_layer(doc, msp, layer_name, layer_info)
        
        if 'viewports' in layer_info:
            self._process_viewport_styles(doc, layer_name, layer_info['viewports'])

    def _process_wmts_layer(self, doc, msp, layer_name, layer_info):
        log_info(f"Processing WMTS layer: {layer_name}")
        self.create_new_layer(doc, msp, layer_name, layer_info)

    def _process_regular_layer(self, doc, msp, layer_name, layer_info):
        self._ensure_layer_exists(doc, layer_name, layer_info)
        
        if self.has_labels(layer_info):
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
        new_layer.dxf.linetype = properties['linetype']
        new_layer.dxf.lineweight = properties['lineweight']
        new_layer.dxf.plot = properties['plot']
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
            # Ensure transparency is between 0 and 1
            transparency = max(0, min(properties['transparency'], 1))
            layer.transparency = transparency
        
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
        try:
            entity.set_xdata(
                'DXFEXPORTER',
                [
                    (1000, self.script_identifier),
                    (1002, '{'),
                    (1000, 'CREATED_BY'),
                    (1000, 'DXFExporter'),
                    (1002, '}')
                ]
            )
            log_info(f"Attached custom XDATA to entity: {entity}")
        except Exception as e:
            log_error(f"Error setting XDATA for entity {entity}: {str(e)}")

    def is_created_by_script(self, entity):
        """Check if an entity was created by this script."""
        try:
            xdata = entity.get_xdata('DXFEXPORTER')
            if xdata:
                for code, value in xdata:
                    if code == 1000 and value == self.script_identifier:
                        return True
        except ezdxf.lldxf.const.DXFValueError:
            # This exception is raised when the entity has no XDATA for 'DXFEXPORTER'
            # It's not an error, just means the entity wasn't created by this script
            return False
        except Exception as e:
            log_warning(f"Unexpected error checking XDATA for entity {entity}: {str(e)}")
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

        # Read the world file to get the transformation parameters
        with open(world_file_path, 'r') as wf:
            a = float(wf.readline().strip())
            d = float(wf.readline().strip())
            b = float(wf.readline().strip())
            e = float(wf.readline().strip())
            c = float(wf.readline().strip())
            f = float(wf.readline().strip())
        log_info(f"World file parameters: a={a}, d={d}, b={b}, e={e}, c={c}, f={f}")

        # Get image dimensions
        with Image.open(image_path) as img:
            img_width, img_height = img.size

        # Calculate the insertion point (bottom-left corner)
        insert_point = (c, f - abs(e) * img_height)
        size_in_units = (abs(a) * img_width, abs(e) * img_height)
        log_info(f"Insertion point: {insert_point}")
        log_info(f"Size in units: {size_in_units}")

        # Create the image definition with the relative Windows-style path
        image_def = msp.doc.add_image_def(filename=relative_image_path, size_in_pixel=(img_width, img_height))

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

        # Enable background transparency
        log_info(f"Added image with transparency: {image}")

    def add_geometries_to_dxf(self, msp, geo_data, layer_name):
        log_info(f"Adding geometries to DXF for layer: {layer_name}")
        
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), {})
        
        if self.is_wmts_or_wms_layer(layer_name):
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
            elif self.is_generated_layer(layer_name) and self.has_labels(layer_info):
                self.add_label_to_dxf(msp, geometry, layer_name, layer_name)

    def add_polygon_to_dxf(self, msp, geometry, layer_name):
        if isinstance(geometry, Polygon):
            polygons = [geometry]
        elif isinstance(geometry, MultiPolygon):
            polygons = list(geometry.geoms)
        else:
            return

        layer_properties = self.layer_properties[layer_name]
        for polygon in polygons:
            exterior_coords = list(polygon.exterior.coords)
            if len(exterior_coords) > 2:
                polyline = msp.add_lwpolyline(exterior_coords, dxfattribs={
                    'layer': layer_name, 
                    'closed': layer_properties['close'],
                    'ltscale': layer_properties['linetypeScale']
                })
                self.attach_custom_data(polyline)
                # Set linetype generation using flags attribute
                if layer_properties['linetypeGeneration']:
                    polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                else:
                    polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

            for interior in polygon.interiors:
                interior_coords = list(interior.coords)
                if len(interior_coords) > 2:
                    polyline = msp.add_lwpolyline(interior_coords, dxfattribs={
                        'layer': layer_name, 
                        'closed': layer_properties['close'],
                        'ltscale': layer_properties['linetypeScale']
                    })
                    self.attach_custom_data(polyline)
                    # Set linetype generation using flags attribute
                    if layer_properties['linetypeGeneration']:
                        polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                    else:
                        polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
                    log_info(f"Added polygon interior to layer {layer_name}: {polyline}")

    def add_linestring_to_dxf(self, msp, linestring, layer_name):
        points = list(linestring.coords)
        layer_properties = self.layer_properties[layer_name]
        close_linestring = layer_properties.get('close_linestring', False)
        
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
                    'closed': close_linestring,
                    'ltscale': layer_properties['linetypeScale']
                }
            )
            
            # Set constant width to 0
            polyline.dxf.const_width = 0
            
            # Set linetype generation using flags attribute
            if layer_properties['linetypeGeneration']:
                polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
            else:
                polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
            
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
            'linetypeScale': layer_info.get('linetypeScale', 1.0),
            'linetypeGeneration': bool(layer_info.get('linetypeGeneration', False)),
            'plot': style.get('plot', True),
            'locked': style.get('locked', False),
            'frozen': style.get('frozen', False),
            'is_on': style.get('is_on', True),
            'transparency': max(0, min(style.get('transparency', 0.0), 1)),
            'close': style.get('close', True),
            'close_linestring': style.get('close_linestring', False)
        }
        self.layer_properties[layer_name] = properties
        self.colors[layer_name] = properties['color']
        
        # Add label layer properties only if labels are present
        if self.has_labels(layer_info):
            label_layer_name = f"{layer_name} Label"
            label_style = layer_info.get('labelStyle', {})
            label_properties = properties.copy()
            
            for key, value in label_style.items():
                if key == 'color':
                    label_properties['color'] = self.get_color_code(value)
                else:
                    label_properties[key] = value
            
            self.layer_properties[label_layer_name] = label_properties
            self.colors[label_layer_name] = label_properties['color']
            
            log_info(f"Added label layer properties for {label_layer_name}: {label_properties}")
        
        log_info(f"Added layer properties for {layer_name}: {properties}")

    def is_wmts_or_wms_layer(self, layer_name):
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
        if layer_info and 'operations' in layer_info:
            return any(op['type'] in ['wmts', 'wms'] for op in layer_info['operations'])
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

    def create_viewports(self, doc, msp):
        log_info("Creating viewports...")
        paper_space = doc.paperspace()
        for vp_config in self.project_settings.get('viewports', []):
            existing_viewport = self.get_viewport_by_name(doc, vp_config['name'])
            if existing_viewport:
                log_info(f"Viewport {vp_config['name']} already exists. Skipping creation.")
                self.viewports[vp_config['name']] = existing_viewport
            else:
                viewport = paper_space.add_viewport(
                    center=vp_config['center'],
                    size=(vp_config['width'], vp_config['height']),
                    view_center_point=vp_config['target_view']['center'],
                    view_height=vp_config['target_view']['height']
                )
                viewport.dxf.status = 1  # Activate the viewport
                viewport.dxf.layer = 'VIEWPORTS'
                
                # Store the viewport name as XDATA
                viewport.set_xdata(
                    'DXFEXPORTER',
                    [
                        (1000, self.script_identifier),
                        (1002, '{'),
                        (1000, 'VIEWPORT_NAME'),
                        (1000, vp_config['name']),
                        (1002, '}')
                    ]
                )
                
                self.viewports[vp_config['name']] = viewport
                log_info(f"Created viewport: {vp_config['name']}")
        return self.viewports

    def get_viewport_by_name(self, doc, name):
        for layout in doc.layouts:
            for entity in layout:
                if entity.dxftype() == 'VIEWPORT':
                    try:
                        xdata = entity.get_xdata('DXFEXPORTER')
                        if xdata:
                            in_viewport_section = False
                            for code, value in xdata:
                                if code == 1000 and value == 'VIEWPORT_NAME':
                                    in_viewport_section = True
                                elif in_viewport_section and code == 1000 and value == name:
                                    return entity
                    except ezdxf.lldxf.const.DXFValueError:
                        continue
        return None

    def _process_viewport_styles(self, doc, layer_name, viewport_styles):
        layer = doc.layers.get(layer_name)
        if layer is None:
            log_warning(f"Layer {layer_name} not found in the document.")
            return

        layer_overrides = layer.get_vp_overrides()

        for vp_style in viewport_styles:
            try:
                viewport = self.get_viewport_by_name(doc, vp_style['name'])
                if viewport:
                    vp_handle = viewport.dxf.handle
                    
                    # Set color override
                    color = self.get_color_code(vp_style['style'].get('color'))
                    if color is not None:
                        layer_overrides.set_color(vp_handle, color)

                    # Set linetype override
                    linetype = vp_style['style'].get('linetype')
                    if linetype:
                        layer_overrides.set_linetype(vp_handle, linetype)

                    # Set lineweight override
                    lineweight = vp_style['style'].get('lineweight')
                    if lineweight is not None:
                        layer_overrides.set_lineweight(vp_handle, lineweight)

                    # Set transparency override
                    transparency = vp_style['style'].get('transparency')
                    if transparency is not None:
                        # Ensure transparency is between 0 and 1
                        transparency_value = max(0, min(transparency, 1))
                        layer_overrides.set_transparency(vp_handle, transparency_value)

                    log_info(f"Set viewport-specific properties for {vp_style['name']} on layer {layer_name}")
                else:
                    log_warning(f"Viewport {vp_style['name']} not found")
            except Exception as e:
                log_error(f"Error processing viewport style for {vp_style['name']}: {str(e)}")

        # Commit the changes to the layer overrides
        layer_overrides.commit()

    def register_app_id(self, doc):
        if 'DXFEXPORTER' not in doc.appids:
            doc.appids.new('DXFEXPORTER')