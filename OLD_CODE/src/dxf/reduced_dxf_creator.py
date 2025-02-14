"""Module for creating reduced DXF files."""

import ezdxf
from pathlib import Path
from src.core.utils import resolve_path, log_info, log_warning, log_error, log_debug
from src.dxf.legend_creator import LegendCreator
from src.dxf_exporter.utils import add_mtext, attach_custom_data
from src.dxf.path_array import create_path_array
import traceback

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
                # Create a new entity based on type
                dxftype = entity.dxftype()
                
                # Get basic properties that all entities have
                common_attribs = {
                    'layer': layer_name,
                    'color': entity.dxf.color if hasattr(entity.dxf, 'color') else None,
                    'linetype': entity.dxf.linetype if hasattr(entity.dxf, 'linetype') else 'CONTINUOUS',
                    'lineweight': entity.dxf.lineweight if hasattr(entity.dxf, 'lineweight') else -1,
                }
                
                if dxftype == 'LWPOLYLINE':
                    # For polylines, create completely new entity with points
                    points = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in entity.get_points()]
                    new_entity = reduced_msp.add_lwpolyline(
                        points,
                        dxfattribs=common_attribs
                    )
                    # Copy closed status
                    if hasattr(entity.dxf, 'closed'):
                        new_entity.dxf.closed = entity.dxf.closed
                    
                elif dxftype == 'LINE':
                    # For lines, create new with start and end points
                    new_entity = reduced_msp.add_line(
                        start=entity.dxf.start,
                        end=entity.dxf.end,
                        dxfattribs=common_attribs
                    )
                    
                elif dxftype == 'CIRCLE':
                    # For circles, create new with center and radius
                    new_entity = reduced_msp.add_circle(
                        center=entity.dxf.center,
                        radius=entity.dxf.radius,
                        dxfattribs=common_attribs
                    )
                    
                elif dxftype == 'ARC':
                    # For arcs, create new with all arc properties
                    new_entity = reduced_msp.add_arc(
                        center=entity.dxf.center,
                        radius=entity.dxf.radius,
                        start_angle=entity.dxf.start_angle,
                        end_angle=entity.dxf.end_angle,
                        dxfattribs=common_attribs
                    )
                    
                elif dxftype == 'HATCH':
                    # Create new hatch
                    new_entity = reduced_msp.add_hatch(
                        color=entity.dxf.color,
                        dxfattribs=common_attribs
                    )
                    # Copy pattern data
                    if hasattr(entity, 'pattern'):
                        new_entity.set_pattern_fill(
                            entity.pattern.name,
                            scale=entity.pattern.scale
                        )
                    # Copy boundary paths
                    for path in entity.paths:
                        new_entity.paths.add_path(path.copy())
                    
                elif dxftype == 'INSERT':
                    # Handle block references
                    block_name = entity.dxf.name
                    if block_name not in reduced_msp.doc.blocks:
                        self._copy_block_definition(entity.doc, reduced_msp.doc, block_name)
                    
                    # Create new block reference with all properties
                    insert_attribs = common_attribs.copy()
                    insert_attribs.update({
                        'name': block_name,
                        'insert': entity.dxf.insert,
                        'xscale': entity.dxf.xscale,
                        'yscale': entity.dxf.yscale,
                        'rotation': entity.dxf.rotation
                    })
                    new_entity = reduced_msp.add_blockref(
                        block_name,
                        insert_attribs['insert'],
                        dxfattribs=insert_attribs
                    )
                
                else:
                    # For unsupported types, try basic copy but with new attributes
                    new_entity = reduced_msp.add_entity(entity.dxftype())
                    for key, value in common_attribs.items():
                        if hasattr(new_entity.dxf, key):
                            setattr(new_entity.dxf, key, value)
                
                # Attach custom data with minimal information
                new_entity.set_xdata(
                    'DXFEXPORTER',
                    [(1000, self.script_identifier)]
                )
                
                entity_count += 1
                
            except Exception as e:
                log_warning(f"Failed to copy entity in layer {layer_name}: {str(e)}")
        
        return entity_count

    def _copy_block_definition(self, source_doc, target_doc, block_name):
        """Copy a block definition from source document to target document."""
        try:
            source_block = source_doc.blocks[block_name]
            new_block = target_doc.blocks.new(name=block_name)
            
            for entity in source_block:
                try:
                    self._clean_entity_for_copy(entity)
                    new_entity = entity.copy()
                    new_block.add_entity(new_entity)
                except Exception as e:
                    log_warning(f"Failed to copy entity in block {block_name}: {str(e)}")
                
        except Exception as e:
            log_warning(f"Failed to copy block definition {block_name}: {str(e)}")

    def _save_reduced_dxf(self, reduced_doc):
        original_path = Path(self.dxf_filename)
        reduced_path = original_path.parent / f"{original_path.stem}_reduced{original_path.suffix}"
        
        try:
            self._audit_and_save(reduced_doc, reduced_path)
        except Exception as e:
            log_error(f"Error saving reduced DXF: {str(e)}")
            raise

    def _audit_and_save(self, reduced_doc, reduced_path):
        """Perform a thorough audit and fix issues before saving."""
        try:
            # First run validation which includes audit and fixes
            log_info("Running DXF validation...")
            is_valid = reduced_doc.validate(print_report=True)
            if is_valid:
                log_info("✓ Document passed initial validation")
            else:
                log_warning("Document validation found unfixable errors")
            
            # Run a thorough audit
            log_info("Running detailed audit...")
            auditor = reduced_doc.audit()
            
            # Fix any issues found
            if len(auditor.errors) == 0:
                log_info("✓ No issues found during audit")
            else:
                log_warning(f"Found {len(auditor.errors)} issues during audit")
                for error in auditor.errors:
                    log_warning(f"Audit error: {error}")
                    
                # Let the auditor fix the issues it can
                if auditor.has_fixes:
                    log_info("Applying fixes...")
                    auditor.apply_fixes()
                    log_info("✓ Fixes applied successfully")
            
            # Clean up the document
            self._cleanup_document(reduced_doc)
            
            # Run a final validation to verify everything is okay
            log_info("Running final validation...")
            final_valid = reduced_doc.validate(print_report=True)
            if final_valid:
                log_info("✓ Document passed final validation")
            else:
                log_warning("Document still contains unfixable errors after cleanup")
            
            # Save the document
            reduced_doc.saveas(str(reduced_path))
            log_info(f"✓ Created reduced DXF file: {reduced_path}")
            
        except Exception as e:
            log_error(f"Error during audit and save: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")
            raise

    def _cleanup_document(self, doc):
        """Clean up the document by removing unused resources."""
        try:
            modelspace = doc.modelspace()
            paperspace = doc.paperspace()
            
            # Audit groups first
            log_debug("Auditing groups...")
            if hasattr(doc, 'groups'):
                # Remove empty groups and invalid handles from all groups
                doc.groups.audit(doc.audit())
                
                # Audit each group individually
                for group in doc.groups.groups():
                    group.audit(doc.audit())
                    if len(group) == 0:
                        try:
                            doc.groups.delete(group)
                            log_debug(f"Removed empty group")
                        except Exception as e:
                            log_warning(f"Could not remove empty group: {str(e)}")
            
            # Purge unused blocks
            for block in list(doc.blocks):
                try:
                    if not block.is_alive:
                        doc.blocks.remove(block.name)
                        log_debug(f"Removed unused block: {block.name}")
                except Exception as e:
                    if "still in use" not in str(e):
                        log_warning(f"Could not remove block {block.name}: {str(e)}")
            
            # Purge unused layers
            for layer in list(doc.layers):
                layer_name = layer.dxf.name
                
                # Skip system layers
                if layer_name in ['0', 'Defpoints']:
                    continue
                
                # Check if layer has any entities
                has_entities = False
                for entity in modelspace:
                    if entity.dxf.layer == layer_name:
                        has_entities = True
                        break
                if not has_entities:
                    for entity in paperspace:
                        if entity.dxf.layer == layer_name:
                            has_entities = True
                            break
                
                # Remove empty layer
                if not has_entities:
                    try:
                        doc.layers.remove(layer_name)
                        log_debug(f"Removed empty layer: {layer_name}")
                    except Exception as e:
                        log_warning(f"Could not remove layer {layer_name}: {str(e)}")
            
            # Force database update
            doc.entitydb.purge()
            
            log_debug("Document cleanup completed successfully")
            
        except Exception as e:
            log_error(f"Error during document cleanup: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")

    def _clean_entity_for_copy(self, entity):
        """Prepare an entity for copying by cleaning up any problematic attributes."""
        try:
            # Only try to remove XDATA if the entity has appdata
            if hasattr(entity, 'appdata') and entity.appdata:
                for appid in list(entity.appdata.keys()):  # Create a list to avoid modification during iteration
                    try:
                        entity.discard_xdata(appid)
                    except:
                        pass
            
            # Clear any reactors
            if hasattr(entity.dxf, 'reactors'):
                entity.dxf.reactors = []
            
            # Clear any handles
            if hasattr(entity.dxf, 'handle'):
                entity.dxf.handle = None
            
            # Clear owner
            if hasattr(entity.dxf, 'owner'):
                entity.dxf.owner = None

            # Clear any hyperlinks
            if hasattr(entity, 'get_hyperlink') and entity.get_hyperlink():
                try:
                    entity.remove_hyperlink()
                except:
                    pass

        except Exception as e:
            log_warning(f"Error cleaning entity for copy: {str(e)}")