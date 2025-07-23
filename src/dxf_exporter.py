import random
import shutil
import traceback
import ezdxf
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point
from src.utils import ensure_path_exists, log_info, log_warning, log_error, resolve_path, log_debug, profile_operation, log_performance, log_memory_usage
import geopandas as gpd
import os
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN
from ezdxf import pattern
from ezdxf import const

from PIL import Image
from src.legend_creator import LegendCreator
from src.dxf_utils import (remove_entities_by_layer, update_layer_properties, attach_custom_data, is_created_by_script,
                         set_drawing_properties, verify_dxf_settings, update_layer_geometry,
                         get_style, apply_style_to_entity, create_hatch, SCRIPT_IDENTIFIER, initialize_document,
                         sanitize_layer_name, add_mtext, atomic_save_dxf, remove_entities_by_layer_optimized,
                         ensure_layer_exists, XDATA_APP_ID)
from src.path_array import create_path_array
from src.style_manager import StyleManager
from src.viewport_manager import ViewportManager
from src.block_insert_manager import BlockInsertManager
from src.text_insert_manager import TextInsertManager
from src.reduced_dxf_creator import ReducedDXFCreator
from src.dxf_processor import DXFProcessor

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
        self.dxf_processor = project_loader.dxf_processor
        log_debug(f"DXFExporter initialized with script identifier: {self.script_identifier}")
        self.setup_layers()
        self.viewport_manager = ViewportManager(
            self.project_settings,
            self.script_identifier,
            self.name_to_aci,
            self.style_manager,
            self.project_loader  # Pass project_loader for YAML write-back
        )
        self.loaded_styles = set()
        self.block_insert_manager = BlockInsertManager(
            project_loader,
            self.all_layers,
            self.script_identifier
        )
        self.text_insert_manager = TextInsertManager(
            self.project_settings,
            self.script_identifier,
            self.style_manager,
            self.name_to_aci,
            self.project_loader  # Pass project_loader for YAML write-back
        )
        self.reduced_dxf_creator = ReducedDXFCreator(self)

    def setup_layers(self):
        # Initialize default properties for ALL layers first
        self.initialize_layer_properties()

        # Setup geom layers
        for layer in self.project_settings['geomLayers']:
            self._setup_single_layer(layer)

            # Also setup properties for any layers created through operations
            if 'operations' in layer:
                result_layer_name = layer['name']
                if result_layer_name not in self.layer_properties:
                    # Initialize with default properties if not already set
                    self.add_layer_properties(result_layer_name, {
                        'color': "White",  # Default color
                        'locked': False,
                        'close': True
                    })

        # Setup WMTS/WMS layers
        for layer in self.project_settings.get('wmtsLayers', []):
            self._setup_single_layer(layer)
        for layer in self.project_settings.get('wmsLayers', []):
            self._setup_single_layer(layer)

    def _setup_single_layer(self, layer):
        layer_name = layer['name']

        # Ensure layer has properties, even if just defaults
        if layer_name not in self.layer_properties:
            default_properties = {
                'layer': {
                    'color': 'White',
                    'linetype': 'CONTINUOUS',
                    'lineweight': 0.13,
                    'plot': True,
                    'locked': False,
                    'frozen': False,
                    'is_on': True
                },
                'entity': {
                    'close': False
                }
            }
            self.layer_properties[layer_name] = default_properties
            self.colors[layer_name] = default_properties['layer']['color']

        # Process layer style if it exists
        if 'style' in layer:
            layer_style = self.style_manager.process_layer_style(layer_name, layer)
            self.add_layer_properties(layer_name, layer, layer_style)

    def export_to_dxf(self, skip_dxf_processor=False):
        """Main export method."""
        with profile_operation("Complete DXF Export"):
            try:
                log_debug("Starting DXF export...")
                log_memory_usage("Export Start")

                # Load DXF once
                with profile_operation("Load/Create DXF Document"):
                    doc = self._load_or_create_dxf(skip_dxf_processor=True)  # Load without processing

                # First, process DXF operations (if any)
                if not skip_dxf_processor and self.project_loader.dxf_processor:
                    with profile_operation("DXF Operations Processing"):
                        log_info("Processing DXF operations first...")
                        self.project_loader.dxf_processor.process_all(doc)
                        log_info("DXF operations completed")

                # Then proceed with geometry layers and other processing
                with profile_operation("Document Initialization"):
                    self.layer_processor.set_dxf_document(doc)
                    self.loaded_styles = initialize_document(doc)
                    msp = doc.modelspace()
                    self.register_app_id(doc)

                # Process all content
                with profile_operation("Layer Processing"):
                    self.process_layers(doc, msp)

                log_memory_usage("After Layer Processing")

                with profile_operation("Path Arrays Creation"):
                    self.create_path_arrays(msp)

                with profile_operation("Block Insert Processing"):
                    self.block_insert_manager.process_block_inserts(msp)

                with profile_operation("Text Insert Processing"):
                    self.process_text_inserts(msp)

                # Create legend
                with profile_operation("Legend Creation"):
                    legend_creator = LegendCreator(doc, msp, self.project_loader, self.loaded_styles)
                    legend_creator.create_legend()

                # Create and configure viewports after ALL content exists
                with profile_operation("Viewport Creation"):
                    self.viewport_manager.sync_viewports(doc, msp)

                log_memory_usage("Before File Save")

                # Save once at the end
                with profile_operation("File Save and Cleanup"):
                    self._cleanup_and_save(doc, msp)

                # After successful export, create reduced version if configured
                with profile_operation("Reduced DXF Creation"):
                    self.reduced_dxf_creator.create_reduced_dxf()

                log_memory_usage("Export Complete")

            except Exception as e:
                log_error(f"Error during DXF export: {str(e)}")
                raise

    def _prepare_dxf_document(self, skip_dxf_processor=False):
        # Backup is now handled by atomic_save_dxf() during the save operation
        doc = self._load_or_create_dxf(skip_dxf_processor)
        return doc

    def _load_or_create_dxf(self, skip_dxf_processor=False):
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
        template_filename = self.project_settings.get('templateDxfFilename')

        # Load or create the DXF document
        doc = None
        if os.path.exists(self.dxf_filename):
            doc = ezdxf.readfile(self.dxf_filename)
            log_debug(f"Loaded existing DXF file: {self.dxf_filename}")

            # Run DXF processor on existing document only if not skipped
            if not skip_dxf_processor and self.project_loader.dxf_processor:
                log_info("DXF processor found, running operations on existing document")
                self.project_loader.dxf_processor.process_all(doc)

            self.load_existing_layers(doc)
            self.check_existing_entities(doc)
            set_drawing_properties(doc)
        elif template_filename:
            # Use template if available
            full_template_path = resolve_path(template_filename, self.project_loader.folder_prefix)
            if os.path.exists(full_template_path):
                doc = ezdxf.readfile(full_template_path)
                log_debug(f"Created new DXF file from template: {full_template_path}")
                set_drawing_properties(doc)
            else:
                log_warning(f"Template file not found at: {full_template_path}")
                doc = ezdxf.new(dxfversion=dxf_version)
                log_debug(f"Created new DXF file with version: {dxf_version}")
                set_drawing_properties(doc)
        else:
            doc = ezdxf.new(dxfversion=dxf_version)
            log_debug(f"Created new DXF file with version: {dxf_version}")
            set_drawing_properties(doc)

        # Run DXF processor on new document only if not skipped
        if doc and not os.path.exists(self.dxf_filename) and not skip_dxf_processor and self.project_loader.dxf_processor:
            log_debug("Running DXF processor on new document")
            self.project_loader.dxf_processor.process_all(doc)

        return doc

    def load_existing_layers(self, doc):
        log_debug("Loading existing layers from DXF file")
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
            log_debug(f"Loaded existing layer: {layer_name}")

    def _cleanup_and_save(self, doc, msp):
        if not ensure_path_exists(self.dxf_filename):
            log_warning(f"Directory for DXF file {self.dxf_filename} does not exist. Cannot save file.")
            return

        with profile_operation("Entity Cleanup"):
            processed_layers = (
                [layer['name'] for layer in self.project_settings['geomLayers']] +
                [layer['name'] for layer in self.project_settings.get('wmtsLayers', [])] +
                [layer['name'] for layer in self.project_settings.get('wmsLayers', [])]
            )
            layers_to_clean = [layer for layer in processed_layers if layer not in self.all_layers]
            log_performance(f"Cleaning {len(layers_to_clean)} layers")
            remove_entities_by_layer_optimized(msp, layers_to_clean, self.script_identifier)

        # Use atomic save for safety - writes to temp file first, then moves atomically
        with profile_operation("Atomic DXF Save"):
            save_success = atomic_save_dxf(doc, self.dxf_filename, create_backup=True)

        if save_success:
            log_info(f"DXF file safely saved: {self.dxf_filename}")
            with profile_operation("DXF Settings Verification"):
                verify_dxf_settings(self.dxf_filename)
        else:
            log_error(f"Failed to save DXF file: {self.dxf_filename}")
            raise RuntimeError(f"DXF save operation failed for {self.dxf_filename}")

    def process_layers(self, doc, msp):
        # First, process all normal geometry layers
        geom_layers = self.project_settings.get('geomLayers', [])
        for layer_info in geom_layers:
            layer_name = layer_info['name']
            if layer_name in self.all_layers:
                self._process_regular_layer(doc, msp, layer_name, layer_info)

                # Process hatches after the regular geometry
                if 'applyHatch' in layer_info:
                    self._process_hatch(doc, msp, layer_name, layer_info)

        # Then process any label layers created by simpleLabel operations
        for layer_info in geom_layers:
            layer_name = layer_info['name']
            label_layer_name = f"{layer_name}_labels"

            if label_layer_name in self.all_layers:
                # Create a new layer info object for the label layer
                label_layer_info = layer_info.copy()

                # Use the style from the simpleLabel operation if available
                if 'operations' in layer_info:
                    for op in layer_info['operations']:
                        if op.get('type') == 'simpleLabel' and 'style' in op:
                            label_layer_info['style'] = op['style']

                # Set updateDxf to True for the label layer
                label_layer_info['updateDxf'] = True

                # Process the label layer
                log_debug(f"Processing label layer: {label_layer_name}")
                self._process_label_layer(doc, msp, label_layer_name, label_layer_info)

        # Then process WMTS/WMS layers
        wmts_layers = self.project_settings.get('wmtsLayers', [])
        wms_layers = self.project_settings.get('wmsLayers', [])

        for layer_info in wmts_layers + wms_layers:
            layer_name = layer_info['name']
            if layer_name in self.all_layers:
                self._process_wmts_layer(doc, msp, layer_name, layer_info)

    def process_single_layer(self, doc, msp, layer_name, layer_info):
        log_debug(f"Processing layer: {layer_name}")

        # Check updateDxf flag early
        update_flag = layer_info.get('updateDxf', False)
        if not update_flag:
            log_debug(f"Skipping layer creation and update for {layer_name} as 'updateDxf' flag is not set")
            return

        # Process layer style
        layer_properties = self.style_manager.process_layer_style(layer_name, layer_info)

        # Create and process layer only if updateDxf is True
        if layer_name not in doc.layers:
            new_layer = doc.layers.new(name=layer_name)
            log_debug(f"Created new layer: {layer_name}")
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
        log_debug(f"Processing WMTS layer: {layer_name}")

        # Check updateDxf flag early and skip all processing if false
        update_flag = layer_info.get('updateDxf', False)
        if not update_flag:
            log_debug(f"Skipping layer creation and update for {layer_name} - updateDxf is False")
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
            log_debug(f"Skipping layer creation and update for {layer_name} as 'updateDxf' flag is not set")
            return

        with profile_operation("Layer Creation", layer_name):
            self._ensure_layer_exists(doc, layer_name, layer_info)

        if layer_name in self.all_layers:
            with profile_operation("Geometry Addition", layer_name):
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
        update_flag = layer_config.get('updateDxf', False)

        if not update_flag:
            log_debug(f"Skipping geometry update for layer {layer_name} as 'updateDxf' flag is not set")
            return

        def update_function():
            with profile_operation("Layer Style Processing", layer_name):
                layer = msp.doc.layers.get(layer_name)
                if layer:
                    # Get properties from StyleManager - either from config or defaults
                    style_properties = {}
                    if layer_config.get('style'):
                        # If a style is specified in config, use it
                        style_properties = self.style_manager.process_layer_style(layer_name, layer_config)
                    else:
                        # If no style specified, use StyleManager defaults
                        style_properties = self.style_manager.default_layer_settings.copy()

                    # Update the layer with properties from StyleManager
                    update_layer_properties(layer, style_properties, self.name_to_aci)

            # Remove and update geometry
            with profile_operation("Remove Existing Entities", layer_name):
                log_debug(f"Removing existing geometry from layer {layer_name}")
                remove_entities_by_layer_optimized(msp, layer_name, self.script_identifier)

            # Add new geometry
            with profile_operation("Add New Geometries", layer_name):
                log_debug(f"Adding new geometry to layer {layer_name}")
                if isinstance(geo_data, list) and all(isinstance(item, tuple) for item in geo_data):
                    self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
                else:
                    self.add_geometries_to_dxf(msp, geo_data, layer_name)

        with profile_operation("Update Layer Geometry Wrapper", layer_name):
            update_layer_geometry(msp, layer_name, self.script_identifier, update_function)

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        log_debug(f"Creating new layer: {layer_name}")
        sanitized_layer_name = sanitize_layer_name(layer_name)
        properties = self.layer_properties[layer_name]

        # Update this line to only pass required arguments
        ensure_layer_exists(doc, sanitized_layer_name)

        # Apply properties after layer creation
        if properties:
            layer = doc.layers.get(sanitized_layer_name)
            update_layer_properties(layer, properties, self.name_to_aci)

        log_debug(f"Created new layer: {sanitized_layer_name}")
        log_debug(f"Layer properties: {properties}")

        if add_geometry and layer_name in self.all_layers:
            self.update_layer_geometry(msp, sanitized_layer_name, self.all_layers[layer_name], layer_info)

        return doc.layers.get(sanitized_layer_name)

    def apply_layer_properties(self, layer, layer_properties):
        update_layer_properties(layer, layer_properties, self.name_to_aci)
        log_debug(f"Updated layer properties: {layer_properties}")

    def attach_custom_data(self, entity, entity_name=None):
        attach_custom_data(entity, self.script_identifier, entity_name)

    def is_created_by_script(self, entity):
        return is_created_by_script(entity, self.script_identifier)

    def add_wmts_xrefs_to_dxf(self, msp, tile_data, layer_name):
        log_debug(f"Adding WMTS xrefs to DXF for layer: {layer_name}")

        for image_path, world_file_path in tile_data:
            self.add_image_with_worldfile(msp, image_path, world_file_path, layer_name)

        log_debug(f"Added {len(tile_data)} WMTS xrefs to layer: {layer_name}")

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
        log_debug(f"Adding image with worldfile for layer: {layer_name}")
        log_info(f"Adding image with worldfile for layer: {layer_name}")
        log_debug(f"Image path: {image_path}")
        log_debug(f"World file path: {world_file_path}")

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
        log_debug(f"Relative image path: {relative_image_path}")

        # Read the world file to get the transformation parameters
        with open(world_file_path, 'r') as wf:
            a = float(wf.readline().strip())
            d = float(wf.readline().strip())
            b = float(wf.readline().strip())
            e = float(wf.readline().strip())
            c = float(wf.readline().strip())
            f = float(wf.readline().strip())
        log_debug(f"World file parameters: a={a}, d={d}, b={b}, e={e}, c={c}, f={f}")

        # Get image dimensions
        with Image.open(image_path) as img:
            img_width, img_height = img.size

        # Calculate the insertion point (bottom-left corner)
        insert_point = (c, f - abs(e) * img_height)
        size_in_units = (abs(a) * img_width, abs(e) * img_height)
        log_debug(f"Insertion point: {insert_point}")
        log_debug(f"Size in units: {size_in_units}")

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
            log_debug(f"Added image with transparency enabled: {image}")
            log_info(f"Added image with transparency enabled: {image}")
        else:
            # Image.SHOW_IMAGE (1) | Image.SHOW_WHEN_NOT_ALIGNED (2)
            image.dxf.flags = 1 | 2
            log_debug(f"Added image without transparency: {image}")

        # Set the $PROJECTNAME header variable to an empty string
        msp.doc.header['$PROJECTNAME'] = ''

    def add_geometries_to_dxf(self, msp, geo_data, layer_name):
        with profile_operation("Add Geometries to DXF", layer_name):
            log_debug(f"Adding geometries to DXF for layer: {layer_name}")

            layer_info = next((l for l in self.project_settings['geomLayers'] if l['name'] == layer_name), {})

            if self.is_wmts_or_wms_layer(layer_name):
                self.add_wmts_xrefs_to_dxf(msp, geo_data, layer_name)
                return

            if geo_data is None:
                log_debug(f"No geometry data available for layer: {layer_name}")
                return

            if isinstance(geo_data, gpd.GeoDataFrame):
                # Check if this is a label layer from labelAssociation operation
                if 'label' in geo_data.columns and 'rotation' in geo_data.columns:
                    self.add_label_points_to_dxf(msp, geo_data, layer_name, layer_info)
                    return

                geometries = geo_data.geometry
            elif isinstance(geo_data, gpd.GeoSeries):
                geometries = geo_data
            else:
                log_warning(f"Unexpected data type for layer {layer_name}: {type(geo_data)}")
                return

            log_debug(f"add_geometries_to_dxf Layer Name: {layer_name}")
            log_performance(f"Adding {len(geometries)} geometries to layer {layer_name}")

            for geometry in geometries:
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

    def add_polygon_to_dxf(self, msp, geometry, layer_name, entity_name=None):
        layer_properties = self.layer_properties.get(layer_name, {})
        entity_properties = layer_properties.get('entity', {})

        dxfattribs = {
            'layer': layer_name,
            'closed': entity_properties.get('close', True),  # Default to True for polygons
        }

        # Add any other entity-level properties
        if 'linetypeScale' in entity_properties:
            dxfattribs['ltscale'] = entity_properties['linetypeScale']
        # Note: linetypeGeneration is handled after polyline creation via bitwise flag operations

        exterior_coords = list(geometry.exterior.coords)
        if len(exterior_coords) > 2:
            polyline = msp.add_lwpolyline(exterior_coords, dxfattribs=dxfattribs)
            self.attach_custom_data(polyline, entity_name)
            # Apply linetype generation setting
            if entity_properties.get('linetypeGeneration'):
                polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
            else:
                polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

        for interior in geometry.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) > 2:
                polyline = msp.add_lwpolyline(interior_coords, dxfattribs=dxfattribs)
                self.attach_custom_data(polyline, entity_name)
                # Apply linetype generation setting
                if entity_properties.get('linetypeGeneration'):
                    polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                else:
                    polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

    def add_linestring_to_dxf(self, msp, geometry, layer_name):
        """Add a LineString geometry to the DXF modelspace."""
        coords = list(geometry.coords)
        if not coords:
            return

        layer_properties = self.layer_properties.get(layer_name, {})
        entity_properties = layer_properties.get('entity', {})

        # Default to False for LineStrings if 'close' is not specified
        should_close = entity_properties.get('close', False)

        # Prepare DXF attributes
        dxfattribs = {'layer': layer_name}
        if 'linetypeScale' in entity_properties:
            dxfattribs['ltscale'] = entity_properties['linetypeScale']

        # Create polyline
        polyline = msp.add_lwpolyline(coords, dxfattribs=dxfattribs)

        if should_close:
            polyline.close(True)

        # Apply linetype generation setting
        if entity_properties.get('linetypeGeneration'):
            polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
        else:
            polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

        # Apply style if available
        if layer_properties:
            style = get_style(layer_properties, self.project_loader)
            if style:
                apply_style_to_entity(polyline, style, self.project_loader, self.loaded_styles)

        self.attach_custom_data(polyline)

    def initialize_layer_properties(self):
        # Process all geom layers, not just those with style configurations
        for layer in self.project_settings['geomLayers']:
            layer_name = layer['name']

            # If the layer already has properties defined, skip it
            if layer_name in self.layer_properties:
                continue

            # Let StyleManager handle ALL defaults - remove hardcoded values
            if (layer.get('style') or
                any(key in layer for key in [
                    'color', 'linetype', 'lineweight', 'plot', 'locked',
                    'frozen', 'is_on', 'transparency', 'close', 'linetypeScale',
                    'linetypeGeneration'
                ])):
                self.add_layer_properties(layer_name, layer)

    def add_layer_properties(self, layer_name, layer, processed_style=None):
        # Always get properties from StyleManager
        properties = processed_style or self.style_manager.process_layer_style(layer_name, layer)
        entity_properties = self.style_manager.process_entity_style(layer_name, layer)

        # Store the properties
        self.layer_properties[layer_name] = {
            'layer': properties,
            'entity': entity_properties
        }

        # Store color for quick access
        if 'color' in properties:
            self.colors[layer_name] = properties['color']

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

    def add_geometry_to_dxf(self, msp, geometry, layer_name, entity_name=None):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            self.add_polygon_to_dxf(msp, geometry, layer_name, entity_name)
        elif isinstance(geometry, LineString):
            self.add_linestring_to_dxf(msp, geometry, layer_name)
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

            log_debug(f"Added point at ({x}, {y}) to layer {layer_name}")

        except Exception as e:
            log_error(f"Error adding point to layer {layer_name}: {str(e)}")

    def verify_entity_hyperlinks(self, msp, layer_name):
        log_debug(f"Verifying hyperlinks for entities in layer {layer_name}")
        for entity in msp.query(f'*[layer=="{layer_name}"]'):
            if hasattr(entity, 'get_hyperlink'):
                pass
            else:
                log_warning(f"Entity {entity.dxftype()} in layer {layer_name} has no 'get_hyperlink' method")

    def check_existing_entities(self, doc):
        log_debug("Checking existing entities in the DXF file")
        for entity in doc.modelspace():
            if hasattr(entity, 'get_hyperlink'):
                hyperlink = entity.get_hyperlink()
            else:
                log_debug(f"Entity {entity} has no 'get_hyperlink' method")

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

                    log_debug(f"Set viewport-specific properties for {vp_style['name']} on layer {layer_name}")
                else:
                    log_warning(f"Viewport {vp_style['name']} not found")
            except Exception as e:
                log_error(f"Error processing viewport style for {vp_style['name']}: {str(e)}")
                log_error(f"Traceback:\n{traceback.format_exc()}")

        # Commit the changes to the layer overrides
        layer_overrides.commit()

    def register_app_id(self, doc):
        if XDATA_APP_ID not in doc.appids:
            doc.appids.new(XDATA_APP_ID)

    def _process_hatch(self, doc, msp, layer_name, layer_info):
        with profile_operation("Hatch Processing", layer_name):
            log_debug(f"Processing hatch for layer: {layer_name}")

            hatch_config = self.style_manager.get_hatch_config(layer_info)

            log_debug(f"Hatch config: {hatch_config}")

            apply_hatch = layer_info.get('applyHatch', False)
            if not apply_hatch:
                log_debug(f"Hatch processing skipped for layer: {layer_name}")
                return

            with profile_operation("Boundary Geometry Collection", layer_name):
                boundary_layers = hatch_config.get('layers', [layer_name])
                boundary_geometry = self._get_boundary_geometry(boundary_layers)

            if boundary_geometry is None or boundary_geometry.is_empty:
                log_warning(f"No valid boundary geometry found for hatch in layer: {layer_name}")
                return

            individual_hatches = hatch_config.get('individual_hatches', True)
            log_performance(f"Hatching {layer_name}: individual_hatches={individual_hatches}")

            if individual_hatches:
                geometries = [boundary_geometry] if isinstance(boundary_geometry, (Polygon, LineString)) else list(boundary_geometry.geoms)
            else:
                geometries = [boundary_geometry]

            log_performance(f"Hatching {layer_name}: Processing {len(geometries)} geometries")

            with profile_operation("Hatch Entity Creation", f"{layer_name} ({len(geometries)} hatches)"):
                for i, geometry in enumerate(geometries):
                    hatch_paths = self._get_hatch_paths(geometry)
                    if hatch_paths:
                        hatch = create_hatch(msp, hatch_paths, hatch_config, self.project_loader)
                        hatch.dxf.layer = layer_name
                        self.attach_custom_data(hatch)

            log_debug(f"Added hatch{'es' if individual_hatches else ''} to layer: {layer_name}")

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
        log_debug(f"Processing {len(path_arrays)} path array configurations")

        for config in path_arrays:
            name = config.get('name')
            source_layer_name = config.get('sourceLayer')
            updateDxf = config.get('updateDxf', False)  # Default is False

            if not name or not source_layer_name:
                log_warning(f"Invalid path array configuration: {config}")
                continue

            if not updateDxf:
                log_debug(f"Skipping path array '{name}' as updateDxf flag is not set")
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
            all_edges = config.get('all_edges', False)

            log_debug(f"Creating path array: {name}")
            log_debug(f"Source layer: {source_layer_name}")
            log_debug(f"Block: {block_name}, Spacing: {spacing}, Scale: {scale}")
            log_debug(f"Path offset: {path_offset}")
            log_debug(f"All edges: {all_edges}")

            create_path_array(msp, source_layer_name, name, block_name,
                             spacing, buffer_distance, scale, rotation,
                             show_debug_visual, self.all_layers,
                             adjust_for_vertices, path_offset, all_edges)

        log_debug("Finished processing all path array configurations")

    def process_text_inserts(self, msp):
        """Process text inserts using the sync-based TextInsertManager."""
        text_configs = self.project_settings.get('textInserts', [])
        if not text_configs:
            log_debug("No text inserts found in project settings")
            return

        # Clean target layers before processing
        configs_to_process = [c for c in text_configs if self.text_insert_manager._get_sync_direction(c) == 'push']
        self.text_insert_manager.clean_target_layers(msp.doc, configs_to_process)

        # Process using sync manager
        processed_texts = self.text_insert_manager.process_entities(msp.doc, msp)
        log_debug(f"Processed {len(processed_texts)} text inserts using sync system")

    def get_viewport_by_name(self, doc, name):
        """Retrieve a viewport by its name using xdata."""
        for layout in doc.layouts:
            for entity in layout:
                if entity.dxftype() == 'VIEWPORT':
                    try:
                        xdata = entity.get_xdata(XDATA_APP_ID)
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

    def export_geometry_to_dxf(self, geometry, layer_info, doc):
        layer_name = layer_info['name']

        # First check if we have any layer properties stored
        layer_properties = self.layer_properties.get(layer_name, {})

        # Only create layer if it doesn't exist, without modifying properties
        ensure_layer_exists(doc, layer_name)

        # Only apply properties if they were explicitly set (not empty dicts)
        if layer_properties.get('layer') or layer_properties.get('entity'):
            layer = doc.layers[layer_name]
            if layer_properties.get('layer'):
                update_layer_properties(layer, layer_properties['layer'])

        # Process the geometry...

    def add_label_points_to_dxf(self, msp, geo_data, layer_name, layer_info):
        """Add label points with rotation to DXF."""
        log_debug(f"Adding label points to DXF for layer: {layer_name}")

        # Get style information
        style_name = layer_info.get('style')
        log_debug(f"Style name from layer_info: {style_name}")  # Should show 'baumLabel'

        if style_name:
            # Get the full style from the style manager
            style, warning = self.style_manager.get_style(style_name)  # Unpack the tuple
            log_debug(f"Full style loaded from style manager: {style}")
            if warning:
                log_warning(f"Warning when loading style '{style_name}'")
        else:
            style = {}

        # Process each label point
        for idx, row in geo_data.iterrows():
            if not isinstance(row.geometry, Point):
                continue

            # Check if required columns exist
            if 'label' not in row.index:
                log_warning(f"Missing 'label' column in row {idx} for layer {layer_name}")
                continue
            if 'rotation' not in row.index:
                log_warning(f"Missing 'rotation' column in row {idx} for layer {layer_name}")
                continue

            point = row.geometry
            label_text = str(row['label'])
            rotation = float(row['rotation'])

            # Create a deep copy of the text style and add rotation
            text_style = style.get('text', {}).copy()
            log_debug(f"Text style before adding rotation: {text_style}")
            text_style['rotation'] = rotation
            log_debug(f"Text style after adding rotation: {text_style}")

            mtext, _ = add_mtext(
                msp,
                label_text,
                point.x,
                point.y,
                layer_name,
                text_style.get('font', 'Standard'),
                text_style=text_style,
                name_to_aci=self.name_to_aci
            )

            if mtext:
                self.attach_custom_data(mtext)
                log_debug(f"Added label '{label_text}' at ({point.x}, {point.y}) with rotation {rotation}")

    def has_labels(self, layer_info):
        """Check if a layer has associated labels."""
        # Check if there are any labelAssociation or simpleLabel operations
        if 'operations' in layer_info:
            for operation in layer_info['operations']:
                if operation.get('type') in ['labelAssociation', 'simpleLabel']:
                    return True

        # Check if there's a label column specified
        if 'label' in layer_info:
            return True

        return False

    def _process_label_layer(self, doc, msp, label_layer_name, layer_info):
        """Process a label layer created by the simpleLabel operation."""
        if label_layer_name not in self.all_layers:
            return

        # Ensure the label layer exists in the DXF document
        if label_layer_name not in doc.layers:
            new_layer = doc.layers.new(name=label_layer_name)
            log_debug(f"Created new label layer: {label_layer_name}")

            # Apply style properties to the layer
            style_name = layer_info.get('style')
            if style_name:
                style_data, _ = self.style_manager.get_style(style_name)
                if style_data:
                    update_layer_properties(new_layer, style_data, self.name_to_aci)

        # Add the label points to the DXF
        label_gdf = self.all_layers[label_layer_name]
        self.add_label_points_to_dxf(msp, label_gdf, label_layer_name, layer_info)
