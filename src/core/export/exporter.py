"""Main DXF exporter module."""

import ezdxf
import os
import shutil
import geopandas as gpd
from pathlib import Path
from src.utils import ensure_path_exists, log_info, log_warning, log_error, resolve_path, log_debug
from .utils import (
    SCRIPT_IDENTIFIER,
    initialize_document,
    cleanup_document,
    set_drawing_properties,
    verify_dxf_settings,
    remove_entities_by_layer
)
from .layer_manager import LayerManager
from .geometry_processor import GeometryProcessor
from .text_processor import TextProcessor
from .hatch_processor import HatchProcessor
# from .path_array_processor import PathArrayProcessor
from .style_manager import StyleManager
# from src.dxf.viewport_manager import ViewportManager
# from src.dxf.block_insert_manager import BlockInsertManager
# from src.dxf.reduced_dxf_creator import ReducedDXFCreator
# from src.dxf.legend_creator import LegendCreator

class DXFExporter:
    def __init__(self, project_loader, layer_processor):
        self.project_loader = project_loader
        self.layer_processor = layer_processor
        self.project_settings = project_loader.project_settings
        self.dxf_filename = project_loader.dxf_filename
        self.script_identifier = SCRIPT_IDENTIFIER
        self.all_layers = layer_processor.all_layers
        self.loaded_styles = set()  # Initialize as empty set
        
        # Initialize managers and processors
        self.style_manager = StyleManager(project_loader)
        self.layer_manager = LayerManager(project_loader, self.style_manager)
        self.geometry_processor = GeometryProcessor(self.script_identifier, project_loader, self.style_manager, self.layer_manager)
        self.text_processor = TextProcessor(self.script_identifier, project_loader, self.style_manager, self.layer_manager)
        self.hatch_processor = HatchProcessor(self.script_identifier, project_loader, self.style_manager, self.layer_manager)
        # self.path_array_processor = PathArrayProcessor(project_loader, self.style_manager)
        
        # # Set up additional managers
        # self.viewport_manager = ViewportManager(
        #     self.project_settings,
        #     self.script_identifier,
        #     project_loader.name_to_aci,
        #     self.style_manager
        # )
        # self.block_insert_manager = BlockInsertManager(
        #     project_loader,
        #     self.all_layers,
        #     self.script_identifier
        # )
        # self.reduced_dxf_creator = ReducedDXFCreator(self)
        
        # Share all_layers with processors that need it
        self.hatch_processor.set_all_layers(self.all_layers)
        # self.path_array_processor.set_all_layers(self.all_layers)

    def export_to_dxf(self, skip_dxf_processor=False):
        """Main export method."""
        try:
            log_debug("Starting DXF export...")
            
            # Load DXF once
            doc = self._load_or_create_dxf(skip_dxf_processor=True)  # Load without processing
            
            # First, process DXF operations (if any)
            if not skip_dxf_processor and self.project_loader.dxf_processor:
                log_info("Processing DXF operations first...")
                self.project_loader.dxf_processor.process_all(doc)
                log_info("DXF operations completed")
            
            # Then proceed with geometry layers and other processing
            self.layer_processor.set_dxf_document(doc)
            self.loaded_styles = initialize_document(doc)
            msp = doc.modelspace()
            self.register_app_id(doc)
            
            # Process all content
            self.process_layers(doc, msp)
            # self.path_array_processor.create_path_arrays(msp)
            # self.block_insert_manager.process_block_inserts(msp)
            self.text_processor.process_text_inserts(msp)
            
            # # Create legend
            # legend_creator = LegendCreator(doc, msp, self.project_loader, self.loaded_styles)
            # legend_creator.create_legend()
            
            # Create and configure viewports after ALL content exists
            # self.viewport_manager.create_viewports(doc, msp)
            
            # Save once at the end
            self._cleanup_and_save(doc, msp)
            
            # After successful export, create reduced version if configured
            # self.reduced_dxf_creator.create_reduced_dxf()
            
        except Exception as e:
            log_error(f"Error during DXF export: {str(e)}")
            raise

    def _load_or_create_dxf(self, skip_dxf_processor=False):
        """Load existing DXF or create new one"""
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')
        template_filename = self.project_settings.get('templateDxfFilename')
        
        # Backup existing file if it exists
        if os.path.exists(self.dxf_filename):
            backup_filename = resolve_path(f"{self.dxf_filename}.ezdxf_bak")
            shutil.copy2(self.dxf_filename, backup_filename)
            log_debug(f"Created backup of existing DXF file: {backup_filename}")
            
            doc = ezdxf.readfile(self.dxf_filename)
            log_debug(f"Loaded existing DXF file: {self.dxf_filename}")
            
        elif template_filename:
            # Use template if available
            full_template_path = resolve_path(template_filename, self.project_loader.folder_prefix)
            if os.path.exists(full_template_path):
                doc = ezdxf.readfile(full_template_path)
                log_debug(f"Created new DXF file from template: {full_template_path}")
            else:
                log_warning(f"Template file not found at: {full_template_path}")
                doc = ezdxf.new(dxfversion=dxf_version)
                log_debug(f"Created new DXF file with version: {dxf_version}")
        else:
            doc = ezdxf.new(dxfversion=dxf_version)
            log_debug(f"Created new DXF file with version: {dxf_version}")

        return doc

    def process_layers(self, doc, msp):
        """Process all layers in the document"""
        geom_layers = self.project_settings.get('geomLayers', [])
        
        # First, clean up all layers that will be updated
        for layer_info in geom_layers:
            layer_name = layer_info['name']
            if layer_info.get('updateDxf', False):  # Only clean layers that are marked for update
                log_debug(f"Cleaning existing entities from layer: {layer_name}")
                remove_entities_by_layer(msp, layer_name, self.script_identifier)
        
        # Then process each layer
        for layer_info in geom_layers:
            layer_name = layer_info['name']
            if layer_name in self.all_layers:
                self._process_layer(doc, msp, layer_name, layer_info)

    def _process_layer(self, doc, msp, layer_name, layer_info):
        """Process a single layer"""
        # Check updateDxf flag early
        update_flag = layer_info.get('updateDxf', False)
        if not update_flag:
            log_debug(f"Skipping layer creation and update for {layer_name} as 'updateDxf' flag is not set")
            return
        
        # Ensure layer exists and has correct properties
        self.layer_manager.ensure_layer_exists(doc, layer_name, layer_info)
        
        # Process geometry
        if layer_name in self.all_layers:
            geo_data = self.all_layers[layer_name]
            
            # First process the geometry
            if isinstance(geo_data, gpd.GeoDataFrame):
                self.geometry_processor.add_geometries_to_dxf(msp, geo_data, layer_name)
            
            # Then add labels if configured
            if isinstance(geo_data, gpd.GeoDataFrame):
                simple_label_field = layer_info.get('simpleLabel')
                if 'label' in geo_data.columns and 'rotation' in geo_data.columns:
                    # Label points with rotation from label association
                    self.text_processor.add_label_points_to_dxf(msp, geo_data, layer_name, layer_info)
                elif simple_label_field and simple_label_field in geo_data.columns:
                    # Simple labels from YAML simpleLabel key
                    geo_data['label'] = geo_data[simple_label_field]
                    self.text_processor.add_label_points_to_dxf(msp, geo_data, layer_name, layer_info)
            
            # Process hatch if configured
            if layer_info.get('applyHatch'):
                self.hatch_processor.process_hatch(doc, msp, layer_name, layer_info)

    def _cleanup_and_save(self, doc, msp):
        """Clean up and save the document"""
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
        log_debug(f"DXF file saved: {self.dxf_filename}")
        verify_dxf_settings(self.dxf_filename)

    def register_app_id(self, doc):
        """Register the application ID in the document"""
        if 'DXFEXPORTER' not in doc.appids:
            doc.appids.new('DXFEXPORTER')
