import random
import shutil
import traceback
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
from src.utils import ensure_path_exists, log_info, log_warning, log_error, resolve_path
import geopandas as gpd
import os
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN
from ezdxf import pattern
from ezdxf import const



from PIL import Image
from src.legend_creator import LegendCreator
from src.dxf_utils import (add_block_reference, get_color_code, convert_transparency, attach_custom_data, 
                           is_created_by_script, add_text, remove_entities_by_layer, 
                           ensure_layer_exists, update_layer_properties, 
                           set_drawing_properties, verify_dxf_settings, update_layer_geometry,
                           get_style, apply_style_to_entity, create_hatch, SCRIPT_IDENTIFIER, initialize_document, sanitize_layer_name, add_text_insert)
from src.path_array import create_path_array
from src.style_manager import StyleManager
from src.viewport_manager import ViewportManager

class DXFExporter:
    def __init__(self, project_loader, layer_processor):
        self.project_loader = project_loader
        self.layer_processor = layer_processor
        self.project_settings = project_loader.project_settings
        self.dxf_filename = project_loader.dxf_filename
        self.script_identifier = SCRIPT_IDENTIFIER
        self.all_layers = layer_processor.all_layers
        self.layer_properties = {}
        self.colors = {}
        self.name_to_aci = project_loader.name_to_aci
        self.block_inserts = self.project_settings.get('blockInserts', [])
        self.style_manager = StyleManager(project_loader)
        log_info(f"DXFExporter initialized with script identifier: {self.script_identifier}")
        self.setup_layers()
        self.viewport_manager = ViewportManager(
            self.project_settings, 
            self.script_identifier,
            self.name_to_aci,
            self.style_manager
        )
        self.loaded_styles = set()

    def setup_layers(self):
        # Setup geom layers
        for layer in self.project_settings['geomLayers']:
            self._setup_single_layer(layer)
        
        # Setup WMTS/WMS layers
        for layer in self.project_settings.get('wmtsLayers', []):
            self._setup_single_layer(layer)
        for layer in self.project_settings.get('wmsLayers', []):
            self._setup_single_layer(layer)

    def _setup_single_layer(self, layer):
        layer_name = layer['name']
        
        # Process layer style
        if 'style' in layer:
            layer_style = self.style_manager.process_layer_style(layer_name, layer)
            self.add_layer_properties(layer_name, layer, layer_style)
        else:
            self.add_layer_properties(layer_name, layer)
        
        if not self.is_wmts_or_wms_layer(layer) and not layer_name.endswith(' Label'):
            if self.has_labels(layer):
                self._setup_label_layer(layer_name, layer)

    def has_labels(self, layer):
        return 'label' in layer or 'labelStyle' in layer

    def _setup_label_layer(self, base_layer_name, base_layer):
        label_layer_name = f"{base_layer_name} Label"
        label_properties = self.layer_properties[base_layer_name].copy()
        
        layerStyle = base_layer.get('layerStyle', {})
        label_style = base_layer.get('labelStyle', {})
        
        # Apply label style properties, falling back to base style if not specified
        for key, value in label_style.items():
            if key == 'color':
                label_properties['color'] = get_color_code(value, self.name_to_aci)
            else:
                label_properties[key] = value
        
        # If no color is specified in label_style, use the base layer color or default to white
        if 'color' not in label_style:
            label_properties['color'] = get_color_code(layerStyle.get('color'), self.name_to_aci)
        
        self.layer_properties[label_layer_name] = label_properties
        self.colors[label_layer_name] = label_properties['color']

    def export_to_dxf(self):
        log_info("Starting DXF export...")
        doc = self._prepare_dxf_document()
        self.loaded_styles = initialize_document(doc)
        msp = doc.modelspace()
        self.register_app_id(doc)
        
        # First ensure all layers exist
        # self._ensure_all_layers_exist(doc)
        
        # Then process all content
        self.process_layers(doc, msp)
        self.create_path_arrays(msp)
        self.process_block_inserts(msp)
        self.process_text_inserts(msp)
        
        # Create legend
        legend_creator = LegendCreator(doc, msp, self.project_loader, self.loaded_styles)
        legend_creator.create_legend()
        
        # Create and configure viewports after ALL content exists
        self.viewport_manager.create_viewports(doc, msp)
        
        self._cleanup_and_save(doc, msp)

    def _prepare_dxf_document(self):
        self._backup_existing_file()
        doc = self._load_or_create_dxf()
        return doc

    def _backup_existing_file(self):
        if os.path.exists(self.dxf_filename):
            backup_filename = resolve_path(f"{self.dxf_filename}.ezdxf_bak")
            shutil.copy2(self.dxf_filename, backup_filename)
            log_info(f"Created backup of existing DXF file: {backup_filename}")

    def _load_or_create_dxf(self):
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
        if os.path.exists(self.dxf_filename):
            doc = ezdxf.readfile(self.dxf_filename)
            log_info(f"Loaded existing DXF file: {self.dxf_filename}")
            self.load_existing_layers(doc)
            self.check_existing_entities(doc)
            # Print settings for existing file
            set_drawing_properties(doc)
        else:
            doc = ezdxf.new(dxfversion=dxf_version)
            log_info(f"Created new DXF file with version: {dxf_version}")
            set_drawing_properties(doc)
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
                    'lock': layer.is_locked,
                    'frozen': layer.is_frozen,
                    'is_on': layer.is_on,
                    'transparency': layer.transparency
                }
                self.colors[layer_name] = layer.color
            log_info(f"Loaded existing layer: {layer_name}")

    def _cleanup_and_save(self, doc, msp):
        if not ensure_path_exists(self.dxf_filename):
            log_warning(f"Directory for DXF file {self.dxf_filename} does not exist. Cannot save file.")
            return
        
        processed_layers = (
            [layer['name'] for layer in self.project_settings['geomLayers']] +
            [layer['name'] for layer in self.project_settings.get('wmtsLayers', [])] +
            [layer['name'] for layer in self.project_settings.get('wmsLayers', [])]
        )
        layers_to_clean = [layer for layer in processed_layers if layer not in self.all_layers]
        remove_entities_by_layer(msp, layers_to_clean, self.script_identifier)
        doc.saveas(self.dxf_filename)
        log_info(f"DXF file saved: {self.dxf_filename}")
        verify_dxf_settings(self.dxf_filename)

    def process_layers(self, doc, msp):
        # First process geometric layers (including hatches)
        geom_layers = self.project_settings.get('geomLayers', [])
        for layer_info in geom_layers:
            layer_name = layer_info['name']
            if layer_name in self.all_layers:
                self._process_regular_layer(doc, msp, layer_name, layer_info)
                
                # Process hatches after the regular geometry
                if 'applyHatch' in layer_info:
                    self._process_hatch(doc, msp, layer_name, layer_info)

        # Then process WMTS/WMS layers
        wmts_layers = self.project_settings.get('wmtsLayers', [])
        wms_layers = self.project_settings.get('wmsLayers', [])
        
        for layer_info in wmts_layers + wms_layers:
            layer_name = layer_info['name']
            if layer_name in self.all_layers:
                self._process_wmts_layer(doc, msp, layer_name, layer_info)

    def process_single_layer(self, doc, msp, layer_name, layer_info):
        log_info(f"Processing layer: {layer_name}")
        
        # Check updateDxf flag early
        update_flag = layer_info.get('updateDxf', False)
        if not update_flag:
            log_info(f"Skipping layer creation and update for {layer_name} as 'updateDxf' flag is not set")
            return
        
        # Process layer style
        layer_properties = self.style_manager.process_layer_style(layer_name, layer_info)
        
        # Create and process layer only if updateDxf is True
        if layer_name not in doc.layers:
            new_layer = doc.layers.new(name=layer_name)
            log_info(f"Created new layer: {layer_name}")
        else:
            new_layer = doc.layers.get(layer_name)
        
        # Apply layer properties
        update_layer_properties(new_layer, layer_properties, self.name_to_aci)
        
        if self.is_wmts_or_wms_layer(layer_info):
            self._process_wmts_layer(doc, msp, layer_name, layer_info)
        else:
            self._process_regular_layer(doc, msp, layer_name, layer_info)
        
        if 'viewports' in layer_info:
            self._process_viewport_styles(doc, layer_name, layer_info['viewports'])
        
        self._process_hatch(doc, msp, layer_name, layer_info)

    def _process_wmts_layer(self, doc, msp, layer_name, layer_info):
        log_info(f"Processing WMTS layer: {layer_name}")
        
        # Check updateDxf flag early and skip all processing if false
        update_flag = layer_info.get('updateDxf', False)
        if not update_flag:
            log_info(f"Skipping layer creation and update for {layer_name} - updateDxf is False")
            return
        
        # Only create and update if updateDxf is True
        self._ensure_layer_exists(doc, layer_name, layer_info)
        
        # Get the tile data from all_layers
        if layer_name in self.all_layers:
            geo_data = self.all_layers[layer_name]
            if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
                # Remove existing entities from the layer
                remove_entities_by_layer(msp, layer_name, self.script_identifier)
                # Add new xrefs
                self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)

    def _process_regular_layer(self, doc, msp, layer_name, layer_info):
        # Check updateDxf flag early
        update_flag = layer_info.get('updateDxf', False)
        if not update_flag:
            log_info(f"Skipping layer creation and update for {layer_name} as 'updateDxf' flag is not set")
            return
        
        self._ensure_layer_exists(doc, layer_name, layer_info)
        
        if self.has_labels(layer_info):
            self._ensure_label_layer_exists(doc, layer_name, layer_info)
        
        if layer_name in self.all_layers:
            self.update_layer_geometry(msp, layer_name, self.all_layers[layer_name], layer_info)

    def _ensure_layer_exists(self, doc, layer_name, layer_info):
        if layer_name not in doc.layers:
            self.create_new_layer(doc, None, layer_name, layer_info, add_geometry=False)
        else:
            self.apply_layer_properties(doc.layers.get(layer_name), layer_info)

    def _ensure_label_layer_exists(self, doc, base_layer_name, layer_info):
        label_layer_name = f"{base_layer_name} Label"
        if label_layer_name not in doc.layers:
            self.create_new_layer(doc, None, label_layer_name, layer_info, add_geometry=False)
        else:
            self.apply_layer_properties(doc.layers.get(label_layer_name), layer_info)

    def update_layer_geometry(self, msp, layer_name, geo_data, layer_config):
        update_flag = layer_config.get('updateDxf', False)  # Default to False
        
        log_info(f"Updating layer geometry for {layer_name}. Update flag: {update_flag}")
        
        if not update_flag:
            log_info(f"Skipping geometry update for layer {layer_name} as 'updateDxf' flag is not set")
            return
        
        def update_function():
            # Remove existing geometry and labels
            log_info(f"Removing existing geometry from layer {layer_name}")
            remove_entities_by_layer(msp, layer_name, self.script_identifier)
            
            # Remove existing labels
            label_layer_name = f"{layer_name} Label"
            log_info(f"Removing existing labels from layer {label_layer_name}")
            remove_entities_by_layer(msp, label_layer_name, self.script_identifier)

            # Add new geometry and labels
            log_info(f"Adding new geometry to layer {layer_name}")
            if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
                self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
            else:
                self.add_geometries_to_dxf(msp, geo_data, layer_name)

            # Verify hyperlinks after adding new entities
            self.verify_entity_hyperlinks(msp, layer_name)
            self.verify_entity_hyperlinks(msp, label_layer_name)

        update_layer_geometry(msp, layer_name, self.script_identifier, update_function)

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        log_info(f"Creating new layer: {layer_name}")
        sanitized_layer_name = sanitize_layer_name(layer_name)  # Add this line
        properties = self.layer_properties[layer_name]
        
        ensure_layer_exists(doc, sanitized_layer_name, properties, self.name_to_aci)  # Update this line
        
        log_info(f"Created new layer: {sanitized_layer_name}")  # Update this line
        log_info(f"Layer properties: {properties}")
        
        if add_geometry and layer_name in self.all_layers:
            self.update_layer_geometry(msp, sanitized_layer_name, self.all_layers[layer_name], layer_info)  # Update this line
        
        return doc.layers.get(sanitized_layer_name)  # Update this line

    def apply_layer_properties(self, layer, layer_properties):
        update_layer_properties(layer, layer_properties, self.name_to_aci)
        log_info(f"Updated layer properties: {layer_properties}")

    def attach_custom_data(self, entity, entity_name=None):
        attach_custom_data(entity, self.script_identifier, entity_name)

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, self.script_identifier)

    def add_wmts_xrefs_to_dxf(self, msp, tile_data, layer_name):
        log_info(f"Adding WMTS xrefs to DXF for layer: {layer_name}")
        
        for image_path, world_file_path in tile_data:
            self.add_image_with_worldfile(msp, image_path, world_file_path, layer_name)

        log_info(f"Added {len(tile_data)} WMTS xrefs to layer: {layer_name}")

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
        log_info(f"Adding image with worldfile for layer: {layer_name}")
        print(f"Adding image with worldfile for layer: {layer_name}")
        log_info(f"Image path: {image_path}")
        log_info(f"World file path: {world_file_path}")

        # Get layer configuration from both WMTS and WMS layers
        layer_info = (
            next((l for l in self.project_settings.get('wmtsLayers', []) if l['name'] == layer_name), None) or
            next((l for l in self.project_settings.get('wmsLayers', []) if l['name'] == layer_name), None)
        )
        
        use_transparency = False
        if layer_info and 'operations' in layer_info:
            for op in layer_info['operations']:
                if op['type'] in ['wms', 'wmts']:
                    use_transparency = op.get('imageTransparency', False)
                    break

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
            dxfattribs={
                'layer': layer_name,
            }
        )
        self.attach_custom_data(image)

        # Set the image path as a relative path
        image.dxf.image_def_handle = image_def.dxf.handle
        
        # Set flags based on transparency setting
        if use_transparency:
            # Image.SHOW_IMAGE (1) | Image.SHOW_WHEN_NOT_ALIGNED (2) | Image.USE_TRANSPARENCY (8)
            image.dxf.flags = 1 | 2 | 8
            log_info(f"Added image with transparency enabled: {image}")
            print(f"Added image with transparency enabled: {image}")
        else:
            # Image.SHOW_IMAGE (1) | Image.SHOW_WHEN_NOT_ALIGNED (2)
            image.dxf.flags = 1 | 2
            log_info(f"Added image without transparency: {image}")

        # Set the $PROJECTNAME header variable to an empty string
        msp.doc.header['$PROJECTNAME'] = ''

    def add_geometries_to_dxf(self, msp, geo_data, layer_name):
        log_info(f"Adding geometries to DXF for layer: {layer_name}")
        
        layer_info = next((l for l in self.project_settings['geomLayers'] if l['name'] == layer_name), {})
        
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
            if isinstance(geometry, Polygon):
                self.add_polygon_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, MultiPolygon):
                for polygon in geometry.geoms:
                    self.add_polygon_to_dxf(msp, polygon, layer_name)
            elif isinstance(geometry, LineString):
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

    def add_polygon_to_dxf(self, msp, geometry, layer_name, entity_name=None):
        layer_properties = self.layer_properties[layer_name]
        exterior_coords = list(geometry.exterior.coords)
        if len(exterior_coords) > 2:
            polyline = msp.add_lwpolyline(exterior_coords, dxfattribs={
                'layer': layer_name, 
                'closed': layer_properties['close'],
                'ltscale': layer_properties.get('linetypeScale', 1.0)
            })
            self.attach_custom_data(polyline, entity_name)
            # Apply linetype generation setting
            if layer_properties['linetypeGeneration']:
                polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
            else:
                polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

        for interior in geometry.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) > 2:
                polyline = msp.add_lwpolyline(interior_coords, dxfattribs={
                    'layer': layer_name, 
                    'closed': layer_properties['close'],
                    'ltscale': layer_properties.get('linetypeScale', 1.0)
                })
                self.attach_custom_data(polyline, entity_name)
                # Apply linetype generation setting
                if layer_properties['linetypeGeneration']:
                    polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                else:
                    polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

    def add_linestring_to_dxf(self, msp, linestring, layer_name, entity_name=None):
        points = list(linestring.coords)
        layer_properties = self.layer_properties[layer_name]

        if layer_properties['close'] and points[0] != points[-1]:
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
                    'closed': layer_properties['close'],
                    'ltscale': layer_properties['linetypeScale']
                }
            )
            
            # Set constant width to 0
            polyline.dxf.const_width = 0
            
            # Apply linetype generation setting
            if layer_properties['linetypeGeneration']:
                polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
            else:
                polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
            
            self.attach_custom_data(polyline, entity_name)
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
        text_entity = self.add_text(msp, str(label), centroid.x, centroid.y, text_layer_name, 'Standard')
        self.attach_custom_data(text_entity)  # Attach custom data to label entities

    def initialize_layer_properties(self):
        for layer in self.project_settings['geomLayers']:
            self.add_layer_properties(layer['name'], layer)

    def add_layer_properties(self, layer_name, layer, processed_style=None):
        properties = {}
        
        # Get the style configuration
        if processed_style:
            # Use the processed style from StyleManager
            properties.update(processed_style)
        else:
            # Get the style from layer configuration
            style_config = layer.get('style')
            if style_config:
                properties.update(self.style_manager.process_layer_style(layer_name, layer))
        
        # Always apply these properties, whether from style or direct layer config
        properties['color'] = properties.get('color') or get_color_code(layer.get('color'), self.name_to_aci)
        properties['linetype'] = properties.get('linetype', layer.get('linetype', 'CONTINUOUS'))
        properties['plot'] = properties.get('plot', layer.get('plot', True))
        properties['locked'] = properties.get('locked', layer.get('locked', False))
        properties['frozen'] = properties.get('frozen', layer.get('frozen', False))
        properties['is_on'] = properties.get('is_on', layer.get('is_on', True))
        properties['transparency'] = properties.get('transparency', layer.get('transparency', 0))
        properties['close'] = layer.get('close', True)
        properties['linetypeScale'] = layer.get('linetypeScale', 1.0)
        properties['linetypeGeneration'] = layer.get('linetypeGeneration', True)
        
        self.layer_properties[layer_name] = properties
        self.colors[layer_name] = properties.get('color')

    def is_wmts_or_wms_layer(self, layer_name):
        layer_info = next((l for l in self.project_settings['geomLayers'] if l['name'] == layer_name), None)
        if layer_info and 'operations' in layer_info:
            return any(op['type'] in ['wmts', 'wms'] for op in layer_info['operations'])
        return False
    
    def is_generated_layer(self, layer_name):
        # Check if the layer is generated (has an operation) and not loaded from a shapefile
        for layer in self.project_settings['geomLayers']:
            if layer['name'] == layer_name:
                return 'operation' in layer and 'shapeFile' not in layer
        return False
        
    def get_label_column(self, layer_name):
        for layer in self.project_settings['geomLayers']:
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
        self.attach_custom_data(text_entity)  # Attach custom data to text entities
        return text_entity

    def add_geometry_to_dxf(self, msp, geometry, layer_name, entity_name=None):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            self.add_polygon_to_dxf(msp, geometry, layer_name, entity_name)
        elif isinstance(geometry, LineString):
            self.add_linestring_to_dxf(msp, geometry, layer_name, entity_name)
        elif isinstance(geometry, MultiLineString):
            for line in geometry.geoms:
                self.add_linestring_to_dxf(msp, line, layer_name, entity_name)
        elif isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                self.add_geometry_to_dxf(msp, geom, layer_name, entity_name)
        else:
            log_warning(f"Unsupported geometry type for layer {layer_name}: {type(geometry)}")

    def verify_entity_hyperlinks(self, msp, layer_name):
        log_info(f"Verifying hyperlinks for entities in layer {layer_name}")
        for entity in msp.query(f'*[layer=="{layer_name}"]'):
            if hasattr(entity, 'get_hyperlink'):
                pass
            else:
                log_warning(f"Entity {entity.dxftype()} in layer {layer_name} has no 'get_hyperlink' method")

    def check_existing_entities(self, doc):
        log_info("Checking existing entities in the DXF file")
        for entity in doc.modelspace():
            if hasattr(entity, 'get_hyperlink'):
                hyperlink = entity.get_hyperlink()
            else:
                log_info(f"Entity {entity} has no 'get_hyperlink' method")

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
                    
                    # Validate and get the style
                    style_config = vp_style.get('style', {})
                    self.style_manager.validate_style(layer_name, style_config)
                    style, warning_generated = self.style_manager.get_style(style_config)
                    
                    if warning_generated:
                        log_warning(f"Style not found for viewport {vp_style['name']} on layer {layer_name}")
                        continue

                    if style and 'layer' in style:
                        layer_style = style['layer']
                        
                        # Set color override
                        color = get_color_code(layer_style.get('color'), self.project_loader.name_to_aci)
                        layer_overrides.set_color(vp_handle, color)

                        # Set linetype override
                        linetype = layer_style.get('linetype')
                        if linetype:
                            layer_overrides.set_linetype(vp_handle, linetype)

                        # Set lineweight override
                        lineweight = layer_style.get('lineweight')
                        if lineweight is not None:
                            layer_overrides.set_lineweight(vp_handle, lineweight)

                        # Set transparency override
                        transparency = layer_style.get('transparency')
                        if transparency is not None:
                            # Ensure transparency is between 0 and 1
                            transparency_value = max(0, min(transparency, 1))
                            layer_overrides.set_transparency(vp_handle, transparency_value)

                    log_info(f"Set viewport-specific properties for {vp_style['name']} on layer {layer_name}")
                else:
                    log_warning(f"Viewport {vp_style['name']} not found")
            except Exception as e:
                log_error(f"Error processing viewport style for {vp_style['name']}: {str(e)}")
                log_error(f"Traceback:\n{traceback.format_exc()}")

        # Commit the changes to the layer overrides
        layer_overrides.commit()

    def register_app_id(self, doc):
        if 'DXFEXPORTER' not in doc.appids:
            doc.appids.new('DXFEXPORTER')

    def _process_hatch(self, doc, msp, layer_name, layer_info):
        log_info(f"Processing hatch for layer: {layer_name}")
        
        hatch_config = self.style_manager.get_hatch_config(layer_info)
        
        log_info(f"Hatch config: {hatch_config}")

        apply_hatch = layer_info.get('applyHatch', False)
        if not apply_hatch:
            log_info(f"Hatch processing skipped for layer: {layer_name}")
            return

        boundary_layers = hatch_config.get('layers', [layer_name])
        boundary_geometry = self._get_boundary_geometry(boundary_layers)
        
        if boundary_geometry is None or boundary_geometry.is_empty:
            log_warning(f"No valid boundary geometry found for hatch in layer: {layer_name}")
            return
        
        individual_hatches = hatch_config.get('individual_hatches', True)

        if individual_hatches:
            geometries = [boundary_geometry] if isinstance(boundary_geometry, (Polygon, LineString)) else list(boundary_geometry.geoms)
        else:
            geometries = [boundary_geometry]
        
        for geometry in geometries:
            hatch_paths = self._get_hatch_paths(geometry)
            if hatch_paths:
                hatch = create_hatch(msp, hatch_paths, hatch_config, self.project_loader)
                hatch.dxf.layer = layer_name
                self.attach_custom_data(hatch)

        log_info(f"Added hatch{'es' if individual_hatches else ''} to layer: {layer_name}")

    def _get_boundary_geometry(self, boundary_layers):
        combined_geometry = None
        for layer_name in boundary_layers:
            if layer_name in self.all_layers:
                layer_geometry = self.all_layers[layer_name]
                if isinstance(layer_geometry, gpd.GeoDataFrame):
                    layer_geometry = layer_geometry.geometry.unary_union
                if combined_geometry is None:
                    combined_geometry = layer_geometry
                else:
                    combined_geometry = combined_geometry.union(layer_geometry)
        return combined_geometry

    def _get_hatch_paths(self, geometry):
        # This method should return a list of paths for the hatch
        # The implementation depends on your specific geometry types
        # Here's a simple example for polygons:
        if isinstance(geometry, Polygon):
            paths = [list(geometry.exterior.coords)]
            for interior in geometry.interiors:
                paths.append(list(interior.coords))
            return paths
        elif isinstance(geometry, MultiPolygon):
            paths = []
            for polygon in geometry.geoms:
                paths.extend(self._get_hatch_paths(polygon))
            return paths
        # Add more geometry types as needed
        return []

    def deep_merge(self, dict1, dict2):
        result = dict1.copy()
        for key, value in dict2.items():
            if isinstance(value, dict):
                result[key] = self.deep_merge(result.get(key, {}), value)
            else:
                result[key] = value
        return result

    def apply_style(self, entity, style):
        apply_style_to_entity(entity, style, self.project_loader, self.loaded_styles)

    def create_path_arrays(self, msp):
        path_arrays = self.project_settings.get('pathArrays', [])
        log_info(f"Processing {len(path_arrays)} path array configurations")
        
        for config in path_arrays:
            name = config.get('name')
            source_layer_name = config.get('sourceLayer')
            updateDxf = config.get('updateDxf', False)  # Default is False
            
            if not name or not source_layer_name:
                log_warning(f"Invalid path array configuration: {config}")
                continue
            
            if not updateDxf:
                log_info(f"Skipping path array '{name}' as updateDxf flag is not set")
                continue
            
            if source_layer_name not in self.all_layers:
                log_warning(f"Source layer '{source_layer_name}' does not exist in all_layers. Skipping path array creation for this configuration.")
                continue
            
            remove_entities_by_layer(msp, name, self.script_identifier)
            
            block_name = config['block']
            spacing = config['spacing']
            scale = config.get('scale', 1.0)
            rotation = config.get('rotation', 0.0)
            buffer_distance = config.get('bufferDistance', 0.0)
            show_debug_visual = config.get('showDebugVisual', False)
            adjust_for_vertices = config.get('adjustForVertices', False)
            
            log_info(f"Creating path array: {name}")
            log_info(f"Source layer: {source_layer_name}")
            log_info(f"Block: {block_name}, Spacing: {spacing}, Scale: {scale}")
            
            create_path_array(msp, source_layer_name, name, block_name, 
                              spacing, buffer_distance, scale, rotation, 
                              show_debug_visual, self.all_layers, adjust_for_vertices)
        
        log_info("Finished processing all path array configurations")

    def process_block_inserts(self, msp):
        self.process_inserts(msp, 'block')

    def process_text_inserts(self, msp):
        self.process_inserts(msp, 'text')

    def process_inserts(self, msp, insert_type='block'):
        configs = self.project_settings.get(f'{insert_type}Inserts', [])
        log_info(f"Processing {len(configs)} {insert_type} insert configurations")
        
        doc = msp.doc
        
        if insert_type == 'block':
            # First pass: collect all names that need cleaning for blocks
            layers_to_clean = set()
            for config in configs:
                if config.get('updateDxf', False):
                    name = config.get('name')
                    if name:
                        layers_to_clean.add(name)
            
            # Clean all block layers at once
            for layer_name in layers_to_clean:
                space = doc.paperspace() if any(c.get('paperspace', False) for c in configs) else doc.modelspace()
                remove_entities_by_layer(space, layer_name, self.script_identifier)
                log_info(f"Cleaned existing entities from layer: {layer_name}")
        else:
            # For text inserts, clean by target layer or name
            layers_to_clean = set()
            for config in configs:
                if config.get('updateDxf', False):
                    # Use targetLayer if specified, otherwise use name
                    layer_name = config.get('targetLayer', config.get('name'))
                    if layer_name:
                        layers_to_clean.add(layer_name)
            
            # Clean all text layers at once
            for layer_name in layers_to_clean:
                space = doc.paperspace() if any(c.get('paperspace', False) for c in configs) else doc.modelspace()
                remove_entities_by_layer(space, layer_name, self.script_identifier)
                log_info(f"Cleaned existing entities from layer: {layer_name}")
        
        # Second pass: process inserts
        for config in configs:
            try:
                name = config.get('name')
                update_dxf = config.get('updateDxf', False)
                
                if not update_dxf:
                    log_info(f"Skipping {insert_type} insert '{name}' as updateDxf flag is not set")
                    continue

                if not name:
                    log_warning(f"Missing name for {insert_type} insert: {config}")
                    continue

                # Get the correct space for insertion
                space = doc.paperspace() if config.get('paperspace', False) else doc.modelspace()

                # Insert entities using common insertion method with correct space
                if insert_type == 'block':
                    self.insert_blocks(space, config)
                else:  # text
                    self.insert_text(space, config)

            except Exception as e:
                log_error(f"Error processing {insert_type} insert: {str(e)}")
                continue

        log_info(f"Finished processing all {insert_type} insert configurations")

    def insert_blocks(self, space, config):
        points = self.get_insertion_points(config.get('position', {}))
        name = config.get('name')  # Use name as the layer
        
        for point in points:
            block_ref = add_block_reference(
                space,
                config['blockName'],
                point,
                name,  # Use name as the layer
                scale=config.get('scale', 1.0),
                rotation=config.get('rotation', 0)
            )
            if block_ref:
                self.attach_custom_data(block_ref)

    def insert_text(self, space, config):
        points = self.get_insertion_points(config.get('position', {}))
        # Use targetLayer if specified, otherwise use name as the layer
        layer_name = config.get('targetLayer', config.get('name'))
        
        for point in points:
            text_entity = add_text_insert(
                space,
                {**config, 'position': {'x': point[0], 'y': point[1]}},
                layer_name,  # Use the determined layer name
                self.project_loader,
                self.script_identifier
            )

    def get_viewport_by_name(self, doc, name):
        """Retrieve a viewport by its name using xdata."""
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
                    except:
                        continue
        return None

    def get_insertion_points(self, position_config):
        """Common method to get insertion points for both blocks and text."""
        points = []
        position_type = position_config.get('type', 'polygon')
        offset_x = position_config.get('offset', {}).get('x', 0)
        offset_y = position_config.get('offset', {}).get('y', 0)
        source_layer = position_config.get('sourceLayer')

        # Handle absolute positioning
        if position_type == 'absolute':
            x = position_config.get('x', 0)
            y = position_config.get('y', 0)
            points.append((x + offset_x, y + offset_y))
            return points

        # For non-absolute positioning, we need a source layer
        if not source_layer:
            log_warning("Source layer required for non-absolute positioning")
            return points

        # Handle geometry-based positioning
        if source_layer not in self.all_layers:
            log_warning(f"Source layer '{source_layer}' not found in all_layers")
            return points

        layer_data = self.all_layers[source_layer]
        if not hasattr(layer_data, 'geometry'):
            log_warning(f"Layer {source_layer} has no geometry attribute")
            return points

        # Process each geometry based on type and method
        for geometry in layer_data.geometry:
            insert_point = self.get_insert_point(geometry, position_config)
            points.append((insert_point[0] + offset_x, insert_point[1] + offset_y))

        return points

    def get_insert_point(self, geometry, position_config):
        position_type = position_config.get('type', 'polygon')
        position_method = position_config.get('method', 'centroid')

        if position_type == 'absolute':
            log_warning("Absolute positioning doesn't use geometry-based insert points")
            return (0, 0)
        
        elif position_type == 'polygon':
            if position_method == 'centroid':
                return geometry.centroid.coords[0]
            elif position_method == 'center':
                return geometry.envelope.centroid.coords[0]
            elif position_method == 'random':
                minx, miny, maxx, maxy = geometry.bounds
                while True:
                    point = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
                    if geometry.contains(point):
                        return point.coords[0]
                    
        elif position_type == 'line':
            if position_method == 'start':
                return geometry.coords[0]
            elif position_method == 'end':
                return geometry.coords[-1]
            elif position_method == 'middle':
                return geometry.interpolate(0.5, normalized=True).coords[0]
            elif position_method == 'random':
                distance = random.random()
                return geometry.interpolate(distance, normalized=True).coords[0]
        
        elif position_type == 'points':
            if hasattr(geometry, 'coords'):
                return geometry.coords[0]
        
        # Default fallback
        log_warning(f"Invalid position type '{position_type}' or method '{position_method}'. Using polygon centroid.")
        return geometry.centroid.coords[0]

    # def _ensure_all_layers_exist(self, doc):
    #     """Ensures all layers exist in the document before viewport creation."""
    #     # Create layers for path arrays
    #     path_arrays = self.project_settings.get('pathArrays', [])
    #     for array in path_arrays:
    #         if 'name' in array:
    #             layer_name = array['name']
    #             if layer_name not in doc.layers:
    #                 doc.layers.new(layer_name)
    #                 log_info(f"Created layer for path array: {layer_name}")
        
    #     # Create layers for block inserts
    #     block_inserts = self.project_settings.get('blockInserts', [])
    #     for insert in block_inserts:
    #         if 'targetLayer' in insert:
    #             layer_name = insert['targetLayer']
    #             if layer_name not in doc.layers:
    #                 doc.layers.new(layer_name)
    #                 log_info(f"Created layer for block insert: {layer_name}")
        
    #     # Create layers for text inserts
    #     text_inserts = self.project_settings.get('textInserts', [])
    #     for insert in text_inserts:
    #         if 'targetLayer' in insert:
    #             layer_name = insert['targetLayer']
    #             if layer_name not in doc.layers:
    #                 doc.layers.new(layer_name)
    #                 log_info(f"Created layer for text insert: {layer_name}")


































