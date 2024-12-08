import ezdxf
from pathlib import Path
from src.utils import resolve_path, log_info, log_warning, log_error, log_debug
from src.legend_creator import LegendCreator
from src.dxf_utils import add_text_insert, add_mtext
from src.path_array import create_path_array

class ReducedDXFCreator:
    def __init__(self, dxf_exporter):
        self.dxf_exporter = dxf_exporter
        self.project_settings = dxf_exporter.project_settings
        self.project_loader = dxf_exporter.project_loader
        self.all_layers = dxf_exporter.all_layers
        self.script_identifier = dxf_exporter.script_identifier
        self.loaded_styles = dxf_exporter.loaded_styles
        self.dxf_filename = dxf_exporter.dxf_filename

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
            log_debug("No reducedDxf.layers specified in project settings, skipping reduced DXF creation")
            return

        reduced_layers = reduced_settings['layers']
        process_from_scratch = reduced_settings.get('processFromScratch', False)
        process_types = reduced_settings.get('processTypes', [])

        template_filename = self.project_settings.get('templateDxfFilename')
        if not template_filename:
            log_warning("No templateDxfFilename specified in project settings, required for reduced DXF creation")
            return
        
        reduced_doc, reduced_msp = self._create_reduced_doc(template_filename)
        if not reduced_doc:
            return

        if process_from_scratch:
            self._process_from_scratch(reduced_doc, reduced_msp, reduced_layers, process_types)
        else:
            self._copy_from_main_dxf(reduced_doc, reduced_msp, reduced_layers)

        self._save_reduced_dxf(reduced_doc)

    def _create_reduced_doc(self, template_filename):
        template_path = resolve_path(template_filename, self.project_loader.folder_prefix)
        if not Path(template_path).exists():
            log_warning(f"Template file not found at: {template_path}")
            return None, None
        
        reduced_doc = ezdxf.readfile(template_path)
        log_debug(f"Created reduced DXF from template: {template_path}")
        return reduced_doc, reduced_doc.modelspace()

    def _process_from_scratch(self, reduced_doc, reduced_msp, reduced_layers, process_types):
        log_debug(f"Processing reduced DXF from scratch with types: {process_types}")
        entity_counts = self._initialize_entity_counts()
        
        self._process_geom_layers(reduced_doc, reduced_msp, reduced_layers, process_types, entity_counts)
        self._process_wmts_wms_layers(reduced_doc, reduced_msp, reduced_layers, process_types, entity_counts)
        self._process_text_inserts(reduced_msp, reduced_layers, process_types, entity_counts)
        self._process_block_inserts(reduced_msp, reduced_layers, process_types, entity_counts)
        self._process_path_arrays(reduced_msp, reduced_layers, process_types, entity_counts)
        self._process_legends_and_viewports(reduced_doc, reduced_msp, process_types)
        
        self._log_empty_types(process_types, entity_counts)

    def _initialize_entity_counts(self):
        return {
            'geomLayers': 0,
            'wmtsLayers': 0,
            'wmsLayers': 0,
            'textInserts': 0,
            'blockInserts': 0,
            'pathArrays': 0
        }

    def _process_geom_layers(self, reduced_doc, reduced_msp, reduced_layers, process_types, entity_counts):
        if 'geomLayers' not in process_types:
            return
            
        for layer_info in self.project_settings.get('geomLayers', []):
            layer_name = layer_info['name']
            if layer_name not in reduced_layers:
                continue
            
            log_debug(f"Processing reduced geom layer: {layer_name}")
            modified_layer_info = layer_info.copy()
            modified_layer_info['updateDxf'] = True
            
            self.dxf_exporter._ensure_layer_exists(reduced_doc, layer_name, modified_layer_info)
            if layer_name in self.all_layers:
                self.dxf_exporter.update_layer_geometry(reduced_msp, layer_name, self.all_layers[layer_name], modified_layer_info)
                if self.dxf_exporter.has_labels(modified_layer_info):
                    self.dxf_exporter._ensure_label_layer_exists(reduced_doc, layer_name, modified_layer_info)
                entity_counts['geomLayers'] += 1

    def _process_wmts_wms_layers(self, reduced_doc, reduced_msp, reduced_layers, process_types, entity_counts):
        for layer_type in ['wmtsLayers', 'wmsLayers']:
            if layer_type not in process_types:
                continue
                
            for layer_info in self.project_settings.get(layer_type, []):
                layer_name = layer_info['name']
                if layer_name not in reduced_layers:
                    continue
                self.dxf_exporter._process_wmts_layer(reduced_doc, reduced_msp, layer_name, layer_info)
                entity_counts[layer_type] += 1

    def _process_text_inserts(self, reduced_msp, reduced_layers, process_types, entity_counts):
        if 'textInserts' not in process_types:
            return
            
        for config in self.project_settings.get('textInserts', []):
            layer_name = config.get('targetLayer')
            if not layer_name or layer_name not in reduced_layers:
                continue
            
            log_debug(f"Processing reduced text insert for layer: {layer_name}")
            
            # Skip if not marked for update
            if not config.get('updateDxf', False):
                log_debug(f"Skipping text insert for layer '{layer_name}' as updateDxf flag is not set")
                continue

            # Get position
            position = config.get('position', {'x': 0, 'y': 0})
            x = position.get('x', 0)
            y = position.get('y', 0)
            
            # Get style information
            style_name = config.get('style')
            if style_name:
                style, warning = self.project_loader.style_manager.get_style(style_name)
                if warning:
                    log_warning(f"Warning when loading style '{style_name}'")
                    style = {}
            else:
                style = {}
            
            text_style = style.get('text', {})
            
            # Create MTEXT
            mtext, _ = add_mtext(
                reduced_msp,
                config.get('text', ''),
                x,
                y,
                layer_name,
                text_style.get('font', 'Standard'),
                text_style=text_style,
                name_to_aci=self.project_loader.name_to_aci
            )
            
            if mtext:
                # Attach custom data
                mtext.set_xdata(self.script_identifier, [('TEXT_INSERT', None)])
                entity_counts['textInserts'] += 1
                log_debug(f"Added text insert to layer: {layer_name}")

    def _process_block_inserts(self, reduced_msp, reduced_layers, process_types, entity_counts):
        if 'blockInserts' in process_types:
            self.dxf_exporter.block_insert_manager.process_block_inserts(
                reduced_msp,
                filter_layers=reduced_layers
            )
            entity_counts['blockInserts'] += 1

    def _process_path_arrays(self, reduced_msp, reduced_layers, process_types, entity_counts):
        if 'pathArrays' not in process_types:
            return
            
        for array in self.project_settings.get('pathArrays', []):
            if array.get('targetLayer') in reduced_layers:
                create_path_array(reduced_msp, array, self.project_loader)
                entity_counts['pathArrays'] += 1

    def _process_legends_and_viewports(self, reduced_doc, reduced_msp, process_types):
        if 'legends' in process_types:
            legend_creator = LegendCreator(reduced_doc, reduced_msp, self.project_loader, self.loaded_styles)
            legend_creator.create_legend()

        if 'viewports' in process_types:
            self.dxf_exporter.viewport_manager.create_viewports(reduced_doc, reduced_msp)

    def _log_empty_types(self, process_types, entity_counts):
        for process_type, count in entity_counts.items():
            if process_type in process_types and count == 0:
                log_warning(f"No {process_type} were copied to the reduced DXF")

    def _copy_from_main_dxf(self, reduced_doc, reduced_msp, reduced_layers):
        log_debug("Copying reduced DXF layers from main DXF")
        try:
            original_doc = ezdxf.readfile(self.dxf_filename)
            original_msp = original_doc.modelspace()
            empty_layers = []
            
            # Create a set of all layers to copy, including label layers
            layers_to_copy = set(reduced_layers)
            for layer_name in reduced_layers:
                label_layer = f"{layer_name} Label"
                # Check if the label layer exists in the original document
                if label_layer in original_doc.layers:
                    layers_to_copy.add(label_layer)
                    log_debug(f"Adding associated label layer: {label_layer}")
            
            for layer_name in layers_to_copy:
                self._copy_layer(reduced_doc, reduced_msp, original_doc, original_msp, layer_name, empty_layers)
            
            if empty_layers:
                log_warning(f"The following layers have no entities: {', '.join(empty_layers)}")

        except Exception as e:
            log_error(f"Error during layer copying: {str(e)}")
            raise

    def _copy_layer(self, reduced_doc, reduced_msp, original_doc, original_msp, layer_name, empty_layers):
        if layer_name not in original_doc.layers:
            empty_layers.append(layer_name)
            log_warning(f"Layer {layer_name} not found in original DXF")
            return

        log_debug(f"Processing layer: {layer_name}")
        
        # Create the layer in reduced doc if it doesn't exist
        if layer_name not in reduced_doc.layers:
            layer_properties = original_doc.layers.get(layer_name).dxf.all_existing_dxf_attribs()
            reduced_doc.layers.new(name=layer_name, dxfattribs=layer_properties)
        
        # Copy entities
        entity_count = self._copy_layer_entities(reduced_msp, original_msp, layer_name)
        
        if entity_count == 0:
            empty_layers.append(layer_name)
            log_warning(f"No entities were copied for layer: {layer_name}")
        else:
            log_debug(f"Copied {entity_count} entities for layer: {layer_name}")

    def _copy_layer_entities(self, reduced_msp, original_msp, layer_name):
        entity_count = 0
        
        # Query for all entities including block references (INSERT entities)
        query = f'*[layer=="{layer_name}"]'
        
        for entity in original_msp.query(query):
            try:
                # If this is a block reference, ensure the block definition exists in reduced doc
                if entity.dxftype() == 'INSERT':
                    block_name = entity.dxf.name
                    if block_name not in reduced_msp.doc.blocks:
                        # Get the block definition from original doc
                        original_block = original_msp.doc.blocks[block_name]
                        # Create new block in reduced doc
                        new_block = reduced_msp.doc.blocks.new(name=block_name)
                        # Copy all entities from original block to new block
                        for block_entity in original_block:
                            new_block.add_entity(block_entity.copy())
                        log_debug(f"Copied block definition: {block_name}")
                
                # Copy the entity (works for both regular entities and block references)
                new_entity = entity.copy()
                reduced_msp.add_entity(new_entity)
                entity_count += 1
                
            except Exception as e:
                log_warning(f"Failed to copy entity in layer {layer_name}: {str(e)}")
        
        return entity_count

    def _save_reduced_dxf(self, reduced_doc):
        original_path = Path(self.dxf_filename)
        reduced_path = original_path.parent / f"{original_path.stem}_reduced{original_path.suffix}"
        
        try:
            self._audit_and_save(reduced_doc, reduced_path)
        except Exception as e:
            log_error(f"Error saving reduced DXF: {str(e)}")
            raise

    def _audit_and_save(self, reduced_doc, reduced_path):
        auditor = reduced_doc.audit()
        if len(auditor.errors) > 0:
            log_warning(f"Found {len(auditor.errors)} issues during audit")
            for error in auditor.errors:
                log_warning(f"Audit error: {error}")
        
        reduced_doc.saveas(str(reduced_path))
        log_debug(f"Created reduced DXF file: {reduced_path}")