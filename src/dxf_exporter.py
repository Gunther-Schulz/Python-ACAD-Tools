import random
import shutil
import traceback
import ezdxf
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
from src.utils import ensure_path_exists, log_info, log_warning, log_error, resolve_path
import geopandas as gpd
import os
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN
from ezdxf import pattern
from ezdxf import const



from PIL import Image
from src.legend_creator import LegendCreator
from src.dxf_utils import (get_color_code,attach_custom_data, 
                           is_created_by_script, add_text, remove_entities_by_layer, 
                           ensure_layer_exists, update_layer_properties, 
                           set_drawing_properties, verify_dxf_settings, update_layer_geometry,
                           get_style, apply_style_to_entity, create_hatch, SCRIPT_IDENTIFIER, initialize_document, sanitize_layer_name, add_text_insert)
from src.path_array import create_path_array
from src.style_manager import StyleManager
from src.viewport_manager import ViewportManager
from src.block_insert_manager import BlockInsertManager

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
        self.block_insert_manager = BlockInsertManager(
            project_loader,
            self.all_layers,
            self.script_identifier
        )

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
        """Main export method."""
        try:
            log_info("Starting DXF export...")
            doc = self._prepare_dxf_document()
            
            # Share the document with LayerProcessor
            self.layer_processor.set_dxf_document(doc)
            
            self.loaded_styles = initialize_document(doc)
            msp = doc.modelspace()
            self.register_app_id(doc)
            
            # First ensure all layers exist
            # self._ensure_all_layers_exist(doc)
            
            # Then process all content
            self.process_layers(doc, msp)
            self.create_path_arrays(msp)
            self.block_insert_manager.process_block_inserts(msp)
            self.process_text_inserts(msp)
            
            # Create legend
            legend_creator = LegendCreator(doc, msp, self.project_loader, self.loaded_styles)
            legend_creator.create_legend()
            
            # Create and configure viewports after ALL content exists
            self.viewport_manager.create_viewports(doc, msp)
            
            self._cleanup_and_save(doc, msp)
            
            # After successful export, create reduced version if configured
            self.create_reduced_dxf()
            
        except Exception as e:
            log_error(f"Error during DXF export: {str(e)}")
            raise

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
        template_filename = self.project_settings.get('templateDxfFilename')
        
        if os.path.exists(self.dxf_filename):
            doc = ezdxf.readfile(self.dxf_filename)
            log_info(f"Loaded existing DXF file: {self.dxf_filename}")
            self.load_existing_layers(doc)
            self.check_existing_entities(doc)
            set_drawing_properties(doc)
        elif template_filename:
            # Use resolve_path with folder prefix
            full_template_path = resolve_path(template_filename, self.project_loader.folder_prefix)
            if os.path.exists(full_template_path):
                doc = ezdxf.readfile(full_template_path)
                log_info(f"Created new DXF file from template: {full_template_path}")
                set_drawing_properties(doc)
            else:
                log_warning(f"Template file not found at: {full_template_path}")
                doc = ezdxf.new(dxfversion=dxf_version)
                log_info(f"Created new DXF file with version: {dxf_version}")
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
            # First update the layer style
            layer = msp.doc.layers.get(layer_name)
            if layer:
                # Process and apply the layer style
                layer_properties = self.style_manager.process_layer_style(layer_name, layer_config)
                update_layer_properties(layer, layer_properties, self.name_to_aci)
                log_info(f"Updated style for layer {layer_name}")
            
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

        # For linestrings, we should not close them unless explicitly requested
        # and the first and last points are already the same
        should_close = (layer_properties['close'] and 
                       points[0] == points[-1])

        log_info(f"Adding linestring to layer {layer_name} with {len(points)} points")
        log_info(f"First point: {points[0][:2] if points else 'No points'}")

        try:
            # Extract only x and y coordinates
            points_2d = [(p[0], p[1]) for p in points]
            
            polyline = msp.add_lwpolyline(
                points=points_2d,
                dxfattribs={
                    'layer': layer_name,
                    'closed': should_close,
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
        elif isinstance(geometry, Point):
            self.add_point_to_dxf(msp, geometry, layer_name, entity_name)
        elif isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                self.add_geometry_to_dxf(msp, geom, layer_name, entity_name)
        else:
            log_warning(f"Unsupported geometry type for layer {layer_name}: {type(geometry)}")

    def add_point_to_dxf(self, msp, point, layer_name, entity_name=None):
        """Add a point geometry to the DXF file."""
        try:
            # Get point coordinates
            x, y = point.x, point.y
            
            # Create a POINT entity
            point_entity = msp.add_point(
                (x, y),
                dxfattribs={
                    'layer': layer_name,
                }
            )
            
            # Attach custom data
            self.attach_custom_data(point_entity, entity_name)
            
            log_info(f"Added point at ({x}, {y}) to layer {layer_name}")
            
        except Exception as e:
            log_error(f"Error adding point to layer {layer_name}: {str(e)}")

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
            path_offset = config.get('pathOffset', 0.0)
            show_debug_visual = config.get('showDebugVisual', False)
            adjust_for_vertices = config.get('adjustForVertices', False)
            
            log_info(f"Creating path array: {name}")
            log_info(f"Source layer: {source_layer_name}")
            log_info(f"Block: {block_name}, Spacing: {spacing}, Scale: {scale}")
            log_info(f"Path offset: {path_offset}")
            
            create_path_array(msp, source_layer_name, name, block_name, 
                             spacing, buffer_distance, scale, rotation, 
                             show_debug_visual, self.all_layers, 
                             adjust_for_vertices, path_offset)
        
        log_info("Finished processing all path array configurations")

    def process_text_inserts(self, msp):
        """Process text inserts for both model and paper space."""
        text_inserts = self.project_settings.get('textInserts', [])
        if not text_inserts:
            log_info("No text inserts found in project settings")
            return

        # First, identify all layers that will get new text
        target_layers = {
            config['targetLayer'] 
            for config in text_inserts 
            if config.get('updateDxf', False) and 'targetLayer' in config
        }
        
        log_info(f"Processing text inserts for layers: {', '.join(target_layers)}")
        
        # Clear each target layer (remove_entities_by_layer handles both spaces)
        for layer_name in target_layers:
            remove_entities_by_layer(msp, layer_name, self.script_identifier)
        
        # Add all new text inserts
        for config in text_inserts:
            try:
                if not config.get('updateDxf', False):
                    continue
                    
                layer_name = config.get('targetLayer')
                if not layer_name:
                    log_warning(f"No target layer specified for text insert '{config.get('name')}'")
                    continue

                text_entity = add_text_insert(
                    msp,
                    config,
                    layer_name,
                    self.project_loader,
                    self.script_identifier
                )
                
                if text_entity:
                    space_type = "paperspace" if config.get('paperspace', False) else "modelspace"
                    log_info(f"Added text insert '{config.get('name')}' to {space_type}")
                else:
                    log_warning(f"Failed to add text insert '{config.get('name')}'")
                    
            except Exception as e:
                log_error(f"Error processing text insert '{config.get('name')}': {str(e)}")
                log_error(f"Traceback:\n{traceback.format_exc()}")

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

    # def get_insertion_points(self, position_config):
    #     """Common method to get insertion points for both blocks and text."""
    #     points = []
    #     position_type = position_config.get('type', 'polygon')
    #     offset_x = position_config.get('offset', {}).get('x', 0)
    #     offset_y = position_config.get('offset', {}).get('y', 0)
    #     source_layer = position_config.get('sourceLayer')

    #     # Handle absolute positioning
    #     if position_type == 'absolute':
    #         x = position_config.get('x', 0)
    #         y = position_config.get('y', 0)
    #         points.append((x + offset_x, y + offset_y))
    #         return points

    #     # For non-absolute positioning, we need a source layer
    #     if not source_layer:
    #         log_warning("Source layer required for non-absolute positioning")
    #         return points

    #     # Handle geometry-based positioning
    #     if source_layer not in self.all_layers:
    #         log_warning(f"Source layer '{source_layer}' not found in all_layers")
    #         return points

    #     layer_data = self.all_layers[source_layer]
    #     if not hasattr(layer_data, 'geometry'):
    #         log_warning(f"Layer {source_layer} has no geometry attribute")
    #         return points

    #     # Process each geometry based on type and method
    #     for geometry in layer_data.geometry:
    #         insert_point = self.get_insert_point(geometry, position_config)
    #         points.append((insert_point[0] + offset_x, insert_point[1] + offset_y))

    #     return points

    # def get_insert_point(self, geometry, position_config):
    #     position_type = position_config.get('type', 'polygon')
    #     position_method = position_config.get('method', 'centroid')

    #     if position_type == 'absolute':
    #         log_warning("Absolute positioning doesn't use geometry-based insert points")
    #         return (0, 0)
        
    #     elif position_type == 'polygon':
    #         if position_method == 'centroid':
    #             return geometry.centroid.coords[0]
    #         elif position_method == 'center':
    #             return geometry.envelope.centroid.coords[0]
    #         elif position_method == 'random':
    #             minx, miny, maxx, maxy = geometry.bounds
    #             while True:
    #                 point = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
    #                 if geometry.contains(point):
    #                     return point.coords[0]
                    
    #     elif position_type == 'line':
    #         if position_method == 'start':
    #             return geometry.coords[0]
    #         elif position_method == 'end':
    #             return geometry.coords[-1]
    #         elif position_method == 'middle':
    #             return geometry.interpolate(0.5, normalized=True).coords[0]
    #         elif position_method == 'random':
    #             distance = random.random()
    #             return geometry.interpolate(distance, normalized=True).coords[0]
        
    #     elif position_type == 'points':
    #         if hasattr(geometry, 'coords'):
    #             return geometry.coords[0]
        
    #     # Default fallback
    #     log_warning(f"Invalid position type '{position_type}' or method '{position_method}'. Using polygon centroid.")
    #     return geometry.centroid.coords[0]

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

    def create_reduced_dxf(self):
        """
        Create a reduced version of the DXF file. Can either:
        1. Process layers from scratch (if processFromScratch=True in settings)
           - Processes only the types specified in processTypes
        2. Copy layers from the main DXF (if processFromScratch=False or not specified)
           - Simply copies the specified layers from the main DXF
        """
        reduced_settings = self.project_settings.get('reducedDxf', {})
        if not reduced_settings or 'layers' not in reduced_settings:
            log_info("No reducedDxf.layers specified in project settings, skipping reduced DXF creation")
            return

        reduced_layers = reduced_settings['layers']
        process_from_scratch = reduced_settings.get('processFromScratch', False)
        process_types = reduced_settings.get('processTypes', [])

        template_filename = self.project_settings.get('templateDxfFilename')
        if not template_filename:
            log_warning("No templateDxfFilename specified in project settings, required for reduced DXF creation")
            return
        
        # Create new DXF document from template
        template_path = resolve_path(template_filename, self.project_loader.folder_prefix)
        if not os.path.exists(template_path):
            log_warning(f"Template file not found at: {template_path}")
            return
        
        # Start with a fresh template
        reduced_doc = ezdxf.readfile(template_path)
        log_info(f"Created reduced DXF from template: {template_path}")
        reduced_msp = reduced_doc.modelspace()
        
        if process_from_scratch:
            log_info(f"Processing reduced DXF from scratch with types: {process_types}")
            entity_counts = {
                'geomLayers': 0,
                'wmtsLayers': 0,
                'wmsLayers': 0,
                'textInserts': 0,
                'blockInserts': 0,
                'pathArrays': 0
            }
            
            # Process geom layers
            if 'geomLayers' in process_types:
                for layer_info in self.project_settings.get('geomLayers', []):
                    layer_name = layer_info['name']
                    if layer_name not in reduced_layers:
                        continue
                    
                    log_info(f"Processing reduced geom layer: {layer_name}")
                    modified_layer_info = layer_info.copy()
                    modified_layer_info['updateDxf'] = True
                    
                    self._ensure_layer_exists(reduced_doc, layer_name, modified_layer_info)
                    if layer_name in self.all_layers:
                        self.update_layer_geometry(reduced_msp, layer_name, self.all_layers[layer_name], modified_layer_info)
                        if self.has_labels(modified_layer_info):
                            self._ensure_label_layer_exists(reduced_doc, layer_name, modified_layer_info)
                        entity_counts['geomLayers'] += 1

            # Process WMTS layers
            if 'wmtsLayers' in process_types:
                for layer_info in self.project_settings.get('wmtsLayers', []):
                    layer_name = layer_info['name']
                    if layer_name not in reduced_layers:
                        continue
                    self._process_wmts_layer(reduced_doc, reduced_msp, layer_name, layer_info)
                    entity_counts['wmtsLayers'] += 1

            # Process WMS layers
            if 'wmsLayers' in process_types:
                for layer_info in self.project_settings.get('wmsLayers', []):
                    layer_name = layer_info['name']
                    if layer_name not in reduced_layers:
                        continue
                    self._process_wmts_layer(reduced_doc, reduced_msp, layer_name, layer_info)
                    entity_counts['wmsLayers'] += 1

            # Process text inserts
            if 'textInserts' in process_types:
                text_inserts = self.project_settings.get('textInserts', [])
                for config in text_inserts:
                    layer_name = config.get('targetLayer')
                    if not layer_name or layer_name not in reduced_layers:
                        continue
                    
                    log_info(f"Processing reduced text insert for layer: {layer_name}")
                    modified_config = config.copy()
                    modified_config['updateDxf'] = True
                    
                    add_text_insert(
                        reduced_msp,
                        modified_config,
                        layer_name,
                        self.project_loader,
                        self.script_identifier
                    )
                    entity_counts['textInserts'] += 1

            # Process block inserts
            if 'blockInserts' in process_types:
                self.block_insert_manager.process_block_inserts(
                    reduced_msp,
                    filter_layers=reduced_layers
                )
                entity_counts['blockInserts'] += 1

            # Process path arrays
            if 'pathArrays' in process_types:
                path_arrays = self.project_settings.get('pathArrays', [])
                for array in path_arrays:
                    if array.get('targetLayer') in reduced_layers:
                        create_path_array(reduced_msp, array, self.project_loader)
                        entity_counts['pathArrays'] += 1

            # Create legend
            if 'legends' in process_types:
                legend_creator = LegendCreator(reduced_doc, reduced_msp, self.project_loader, self.loaded_styles)
                legend_creator.create_legend()

            # Create viewports
            if 'viewports' in process_types:
                self.viewport_manager.create_viewports(reduced_doc, reduced_msp)

            # Log warnings for empty types
            for process_type, count in entity_counts.items():
                if process_type in process_types and count == 0:
                    log_warning(f"No {process_type} were copied to the reduced DXF")

        else:
            log_info("Copying reduced DXF layers from main DXF")
            try:
                # Copy layers from the main DXF file
                original_doc = ezdxf.readfile(self.dxf_filename)
                original_msp = original_doc.modelspace()

                # Track layers with no entities
                empty_layers = []
                
                # Copy layers and their entities
                for layer_name in reduced_layers:
                    if layer_name in original_doc.layers:
                        log_info(f"Processing layer: {layer_name}")
                        
                        # Create the layer in reduced doc
                        if layer_name not in reduced_doc.layers:
                            layer_properties = original_doc.layers.get(layer_name).dxf.all_existing_dxf_attribs()
                            reduced_doc.layers.new(name=layer_name, dxfattribs=layer_properties)
                        
                        # Copy entities for this layer
                        entity_count = 0
                        for entity in original_msp.query(f'*[layer=="{layer_name}"]'):
                            try:
                                new_entity = entity.copy()
                                reduced_msp.add_entity(new_entity)
                                entity_count += 1
                            except Exception as e:
                                log_warning(f"Failed to copy entity in layer {layer_name}: {str(e)}")
                                continue
                        
                        if entity_count == 0:
                            empty_layers.append(layer_name)
                            log_warning(f"No entities were copied for layer: {layer_name}")
                        else:
                            log_info(f"Copied {entity_count} entities for layer: {layer_name}")
                    else:
                        empty_layers.append(layer_name)
                        log_warning(f"Layer {layer_name} not found in original DXF")
                
                # Summary of empty layers
                if empty_layers:
                    log_warning(f"The following layers have no entities: {', '.join(empty_layers)}")

            except Exception as e:
                log_error(f"Error during layer copying: {str(e)}")
                raise

        # Generate reduced DXF filename
        original_path = Path(self.dxf_filename)
        reduced_path = original_path.parent / f"{original_path.stem}_reduced{original_path.suffix}"
        
        try:
            # Audit and clean up the document before saving
            auditor = reduced_doc.audit()
            if len(auditor.errors) > 0:
                log_warning(f"Found {len(auditor.errors)} issues during audit")
                for error in auditor.errors:
                    log_warning(f"Audit error: {error}")
            
            # Save reduced DXF
            reduced_doc.saveas(str(reduced_path))
            log_info(f"Created reduced DXF file: {reduced_path}")
        except Exception as e:
            log_error(f"Error saving reduced DXF: {str(e)}")
            raise

































