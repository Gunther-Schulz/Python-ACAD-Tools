import ezdxf
from pathlib import Path
from src.utils import resolve_path, log_info, log_warning, log_error, log_debug
from src.legend_creator import LegendCreator
from src.dxf_utils import add_mtext, attach_custom_data, initialize_document, set_drawing_properties, atomic_save_dxf, XDATA_APP_ID, SCRIPT_IDENTIFIER, create_simple_xdata
from src.path_array import create_path_array
import traceback
import pkg_resources

# Determine ezdxf version for compatibility fixes
try:
    EZDXF_VERSION = pkg_resources.get_distribution("ezdxf").version
    EZDXF_VERSION_TUPLE = tuple(map(int, EZDXF_VERSION.split('.')))
    log_debug(f"Using ezdxf version: {EZDXF_VERSION}")
except Exception as e:
    # Default to 1.3.1 if we can't determine the version
    EZDXF_VERSION = "1.3.1"
    EZDXF_VERSION_TUPLE = (1, 3, 1)
    log_warning(f"Could not determine ezdxf version, defaulting to {EZDXF_VERSION}: {str(e)}")

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
        Create a simplified version of the DXF file, containing only basic geometry
        from the specified layers, using the template DXF as a basis.
        """
        try:
            reduced_settings = self.project_settings.get('reducedDxf', {})
            if not reduced_settings or 'layers' not in reduced_settings:
                log_debug("No reducedDxf.layers specified in project settings, skipping reduced DXF creation")
                return

            reduced_layers = reduced_settings['layers']
            if not reduced_layers:
                log_debug("Empty reducedDxf.layers list, skipping reduced DXF creation")
                return

            # Get template filename - required
            template_filename = self.project_settings.get('templateDxfFilename')
            if not template_filename:
                log_warning("No templateDxfFilename specified in project settings, required for reduced DXF creation")
                return

            log_info(f"Creating reduced DXF with {len(reduced_layers)} layers from template")

            # Create a new document based on the template
            reduced_doc, reduced_msp = self._create_reduced_doc(template_filename)
            if not reduced_doc:
                log_error("Failed to create reduced DXF document")
                return

            # Copy only the basic geometry from specified layers
            self._copy_from_main_dxf(reduced_doc, reduced_msp, reduced_layers)

            # Clean up and save the document
            self._cleanup_and_save(reduced_doc)

            log_info("Reduced DXF creation completed successfully")
        except Exception as e:
            log_error(f"Error creating reduced DXF: {str(e)}\n{traceback.format_exc()}")
            # Don't re-raise - just log the error and continue

    def _create_reduced_doc(self, template_filename):
        """Create a new DXF document from template."""
        template_path = resolve_path(template_filename, self.project_loader.folder_prefix)
        if not Path(template_path).exists():
            log_warning(f"Template file not found at: {template_path}")
            return None, None

        try:
            # Read the original file to get its version and basic settings
            original_doc = ezdxf.readfile(self.dxf_filename)
            dxf_version = original_doc.dxfversion

            # Always use the template as a basis (no fallback logic)
            log_debug(f"Creating reduced DXF from template: {template_path}")
            reduced_doc = ezdxf.readfile(template_path)

            # Set the correct DXF version
            if hasattr(reduced_doc, 'dxfversion'):
                reduced_doc.dxfversion = dxf_version

            # CRITICAL: Initialize the document structure
            self.loaded_styles = initialize_document(reduced_doc)
            set_drawing_properties(reduced_doc)

            # Register app ID
            if XDATA_APP_ID not in reduced_doc.appids:
                reduced_doc.appids.new(XDATA_APP_ID)

            # Copy essential header variables from original document
            header_vars = [
                '$MEASUREMENT', '$INSUNITS', '$LUNITS',
                '$ACADVER', '$DWGCODEPAGE', '$LTSCALE',
                '$DIMSCALE', '$LIMMIN', '$LIMMAX',
                '$EXTMIN', '$EXTMAX'
            ]

            for var in header_vars:
                if var in original_doc.header and var in reduced_doc.header:
                    try:
                        reduced_doc.header[var] = original_doc.header[var]
                    except Exception as e:
                        log_warning(f"Could not copy header variable {var}: {str(e)}")

            # Create a minimal set of layers based on the specified layers
            for layer_name in self.project_settings.get('reducedDxf', {}).get('layers', []):
                if layer_name not in reduced_doc.layers and layer_name in original_doc.layers:
                    # Get original layer properties
                    try:
                        original_layer = original_doc.layers.get(layer_name)
                        layer_attribs = {}

                        # Copy basic layer properties
                        for attr in ['color', 'linetype', 'lineweight', 'plot', 'description']:
                            if hasattr(original_layer.dxf, attr):
                                layer_attribs[attr] = getattr(original_layer.dxf, attr)

                        # Create the layer
                        reduced_doc.layers.new(name=layer_name, dxfattribs=layer_attribs)
                        log_debug(f"Created layer: {layer_name}")
                    except Exception as e:
                        # Create with defaults if copying properties fails
                        try:
                            reduced_doc.layers.new(name=layer_name)
                            log_warning(f"Created layer {layer_name} with default properties: {str(e)}")
                        except:
                            log_warning(f"Could not create layer {layer_name}")

            # Add standard linetypes if missing
            std_linetypes = ['CONTINUOUS', 'DASHED', 'DOTTED', 'DASHDOT']
            for lt_name in std_linetypes:
                if lt_name not in reduced_doc.linetypes:
                    try:
                        if lt_name == 'CONTINUOUS':
                            reduced_doc.linetypes.add(lt_name, pattern=[])
                        elif lt_name == 'DASHED':
                            reduced_doc.linetypes.add(lt_name, pattern=[0.5, -0.25])
                        elif lt_name == 'DOTTED':
                            reduced_doc.linetypes.add(lt_name, pattern=[0.0, -0.25])
                        elif lt_name == 'DASHDOT':
                            reduced_doc.linetypes.add(lt_name, pattern=[0.5, -0.25, 0.0, -0.25])
                    except Exception as e:
                        log_warning(f"Could not add linetype {lt_name}: {str(e)}")

            log_debug(f"Created reduced DXF document with {len(reduced_doc.layers)} layers")
            return reduced_doc, reduced_doc.modelspace()
        except Exception as e:
            log_error(f"Error creating reduced DXF: {str(e)}")
            return None, None

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
                # Attach custom data using centralized function
                mtext.set_xdata(XDATA_APP_ID, create_simple_xdata(SCRIPT_IDENTIFIER))
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
            self.dxf_exporter.viewport_manager.sync_viewports(reduced_doc, reduced_msp)

    def _log_empty_types(self, process_types, entity_counts):
        for process_type, count in entity_counts.items():
            if process_type in process_types and count == 0:
                log_warning(f"No {process_type} were copied to the reduced DXF")

    def _copy_from_main_dxf(self, reduced_doc, reduced_msp, reduced_layers):
        """Copy basic geometry from main DXF to reduced DXF."""
        log_debug("Copying reduced DXF layers from main DXF")
        try:
            original_doc = ezdxf.readfile(self.dxf_filename)
            original_msp = original_doc.modelspace()
            empty_layers = []

            # Process each layer
            for layer_name in reduced_layers:
                log_debug(f"Processing layer: {layer_name}")

                # Ensure the layer exists in both documents
                if layer_name not in original_doc.layers:
                    log_warning(f"Layer {layer_name} not found in source DXF")
                    continue

                if layer_name not in reduced_doc.layers:
                    try:
                        # Create layer with default properties if it doesn't exist
                        reduced_doc.layers.new(name=layer_name)
                        log_debug(f"Created layer: {layer_name}")
                    except Exception as e:
                        log_warning(f"Could not create layer {layer_name}: {str(e)}")
                        continue

                # Copy entities from this layer
                entity_count = self._copy_layer_entities(reduced_msp, original_msp, layer_name)

                # Report results
                if entity_count == 0:
                    empty_layers.append(layer_name)
                    log_warning(f"No entities were copied for layer: {layer_name}")
                else:
                    log_debug(f"Copied {entity_count} entities for layer: {layer_name}")

            # Report empty layers
            if empty_layers:
                log_warning(f"The following layers had no entities: {', '.join(empty_layers)}")

        except Exception as e:
            log_error(f"Error copying from main DXF: {str(e)}")
            raise

    def _copy_layer_entities(self, reduced_msp, original_msp, layer_name):
        """
        Copy only basic geometry entities from a layer, avoiding blocks and complex structures.
        Only copies: LWPOLYLINE, LINE, CIRCLE, ARC, POINT, TEXT, MTEXT
        """
        entity_count = 0
        # Query for all entities in the layer
        query = f'*[layer=="{layer_name}"]'

        for entity in original_msp.query(query):
            try:
                # Get entity type
                dxftype = entity.dxftype()

                # Skip any block references or complex entities
                if dxftype == 'INSERT':
                    continue

                # Get basic DXF attributes but exclude problematic ones
                dxf_attribs = {}
                if hasattr(entity, 'dxf'):
                    # Copy only essential attributes
                    for attr_name in ['color', 'layer', 'linetype', 'lineweight']:
                        if hasattr(entity.dxf, attr_name):
                            dxf_attribs[attr_name] = getattr(entity.dxf, attr_name)

                # Ensure layer is set correctly
                dxf_attribs['layer'] = layer_name

                new_entity = None
                # Handle each basic entity type
                if dxftype == 'LWPOLYLINE':
                    # Extract points
                    try:
                        points = list(entity.get_points())
                        # Create new polyline with just the basic geometry
                        new_entity = reduced_msp.add_lwpolyline(
                            points,
                            dxfattribs=dxf_attribs
                        )
                        # Copy closed status
                        if hasattr(entity.dxf, 'closed'):
                            new_entity.dxf.closed = entity.dxf.closed
                    except Exception as e:
                        log_warning(f"Failed to copy LWPOLYLINE: {str(e)}")

                elif dxftype == 'LINE':
                    try:
                        # Create simple line
                        new_entity = reduced_msp.add_line(
                            start=entity.dxf.start,
                            end=entity.dxf.end,
                            dxfattribs=dxf_attribs
                        )
                    except Exception as e:
                        log_warning(f"Failed to copy LINE: {str(e)}")

                elif dxftype == 'CIRCLE':
                    try:
                        # Create simple circle
                        new_entity = reduced_msp.add_circle(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            dxfattribs=dxf_attribs
                        )
                    except Exception as e:
                        log_warning(f"Failed to copy CIRCLE: {str(e)}")

                elif dxftype == 'ARC':
                    try:
                        # Create simple arc
                        new_entity = reduced_msp.add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=entity.dxf.start_angle,
                            end_angle=entity.dxf.end_angle,
                            dxfattribs=dxf_attribs
                        )
                    except Exception as e:
                        log_warning(f"Failed to copy ARC: {str(e)}")

                elif dxftype == 'POINT':
                    try:
                        # Create simple point
                        new_entity = reduced_msp.add_point(
                            location=entity.dxf.location,
                            dxfattribs=dxf_attribs
                        )
                    except Exception as e:
                        log_warning(f"Failed to copy POINT: {str(e)}")

                elif dxftype == 'TEXT':
                    try:
                        # Create simple text
                        new_entity = reduced_msp.add_text(
                            text=entity.dxf.text,
                            dxfattribs=dxf_attribs
                        )
                        # Copy position
                        if hasattr(entity.dxf, 'insert'):
                            new_entity.dxf.insert = entity.dxf.insert
                        # Copy height
                        if hasattr(entity.dxf, 'height'):
                            new_entity.dxf.height = entity.dxf.height
                        # Copy rotation
                        if hasattr(entity.dxf, 'rotation'):
                            new_entity.dxf.rotation = entity.dxf.rotation
                    except Exception as e:
                        log_warning(f"Failed to copy TEXT: {str(e)}")

                elif dxftype == 'MTEXT':
                    try:
                        # Extract plain text content safely
                        text_content = ""
                        if hasattr(entity, 'text'):
                            if callable(entity.text):
                                text_content = entity.text()
                            else:
                                text_content = entity.text

                        # Create simple mtext
                        new_entity = reduced_msp.add_mtext(
                            text=text_content,
                            dxfattribs=dxf_attribs
                        )
                        # Copy position
                        if hasattr(entity.dxf, 'insert'):
                            new_entity.dxf.insert = entity.dxf.insert
                        # Copy height
                        if hasattr(entity.dxf, 'char_height'):
                            new_entity.dxf.char_height = entity.dxf.char_height
                        # Copy width
                        if hasattr(entity.dxf, 'width'):
                            new_entity.dxf.width = entity.dxf.width
                        # Copy rotation
                        if hasattr(entity.dxf, 'rotation'):
                            new_entity.dxf.rotation = entity.dxf.rotation
                    except Exception as e:
                        log_warning(f"Failed to copy MTEXT: {str(e)}")

                # Skip all other entity types

                # Add standard DXFEXPORTER appID to track entities using centralized function
                try:
                    new_entity.set_xdata(XDATA_APP_ID, create_simple_xdata(SCRIPT_IDENTIFIER))
                    entity_count += 1
                except Exception as e:
                    log_warning(f"Failed to add XDATA to entity: {str(e)}")

            except Exception as e:
                log_warning(f"Failed to copy entity in layer {layer_name}: {str(e)}")

        return entity_count

    def _copy_block_definition(self, source_doc, target_doc, block_name):
        """Copy a block definition from source document to target document."""
        try:
            # Guard against non-string block names
            if not isinstance(block_name, str):
                log_warning(f"Invalid block name type: {type(block_name)}")
                return

            # Guard against None values in block reference
            if block_name.startswith('*'):
                try:
                    # Special block names starting with * might be anonymous blocks
                    # Check if the block name points to an actual block
                    if block_name not in source_doc.blocks:
                        log_warning(f"Anonymous/special block {block_name} not found in source document")
                        return
                except Exception as e:
                    log_warning(f"Error checking block {block_name}: {str(e)}")
                    return

            if block_name not in source_doc.blocks:
                log_warning(f"Block {block_name} not found in source document")
                return

            source_block = source_doc.blocks[block_name]

            # If block already exists in target, skip it
            if block_name in target_doc.blocks:
                log_debug(f"Block {block_name} already exists in target document")
                return

            # Create new block with all attributes from source
            block_attribs = {}
            try:
                if hasattr(source_block, 'block') and hasattr(source_block.block, 'dxf'):
                    block_attribs = source_block.block.dxf.all_existing_dxf_attribs()
            except Exception as e:
                log_warning(f"Error getting block attributes for {block_name}: {str(e)}")

            # Ensure required attributes are set
            if 'name' not in block_attribs:
                block_attribs['name'] = block_name

            # Create a new block safely
            try:
                # Create the block with non-string safety
                new_block = target_doc.blocks.new(name=block_name, dxfattribs=block_attribs)
            except Exception as e:
                log_warning(f"Error creating block {block_name}: {str(e)}")
                return

            # Copy all entities from source block
            for entity in source_block:
                try:
                    # Guard against string objects incorrectly passed as entities
                    if isinstance(entity, str):
                        log_warning(f"String passed as entity in block {block_name}: {entity}")
                        continue

                    if not hasattr(entity, 'dxf'):
                        log_debug(f"Skipping entity without dxf attribute in block {block_name}")
                        continue

                    # Create a new entity of the same type
                    dxftype = entity.dxftype()
                    dxfattribs = entity.dxf.all_existing_dxf_attribs()

                    # Remove problematic attributes that should be regenerated
                    for attr in ['handle', 'owner', 'reactors']:
                        if attr in dxfattribs:
                            del dxfattribs[attr]

                    # Create the new entity based on type
                    if dxftype == 'INSERT':
                        # Handle nested blocks recursively
                        try:
                            # Guard against None or non-string names
                            if not hasattr(entity.dxf, 'name'):
                                log_warning(f"INSERT entity without name attribute in block {block_name}")
                                continue

                            nested_block_name = entity.dxf.name

                            if nested_block_name is None:
                                log_warning(f"INSERT with None block name in {block_name}")
                                continue

                            if not isinstance(nested_block_name, str):
                                log_warning(f"Invalid nested block name type in {block_name}: {type(nested_block_name)}")
                                continue

                            if nested_block_name not in target_doc.blocks:
                                # Skip circular references
                                if nested_block_name != block_name:
                                    self._copy_block_definition(source_doc, target_doc, nested_block_name)
                                else:
                                    log_warning(f"Circular block reference detected: {block_name}")
                                    continue

                            new_entity = new_block.add_blockref(
                                nested_block_name,
                                insert=entity.dxf.insert,
                                dxfattribs=dxfattribs
                            )

                            # Copy attributes if any
                            if hasattr(entity, 'attribs') and entity.attribs:
                                for attrib in entity.attribs:
                                    try:
                                        if hasattr(attrib, 'dxf'):
                                            attrib_dxf = attrib.dxf.all_existing_dxf_attribs()
                                            new_entity.add_attrib(
                                                tag=attrib.dxf.tag,
                                                text=attrib.dxf.text,
                                                insert=attrib.dxf.insert,
                                                dxfattribs=attrib_dxf
                                            )
                                    except Exception as attrib_e:
                                        log_warning(f"Error copying block attribute: {str(attrib_e)}")
                        except Exception as inner_e:
                            log_warning(f"Error handling INSERT in block {block_name}: {str(inner_e)}")
                            continue
                    else:
                        # For all other entity types, try simple copy
                        try:
                            # For all other entity types
                            new_entity = new_block.add_entity(dxftype)
                            for key, value in dxfattribs.items():
                                if hasattr(new_entity.dxf, key):
                                    setattr(new_entity.dxf, key, value)
                        except Exception as inner_e:
                            log_warning(f"Error copying entity of type {dxftype} in block {block_name}: {str(inner_e)}")
                            continue

                    # Skip XData copy - it's causing most of the errors
                except Exception as e:
                    log_warning(f"Failed to copy entity in block {block_name}: {str(e)}")

        except Exception as e:
            log_warning(f"Failed to copy block definition {block_name}: {str(e)}")
            # Don't raise here, just log the error and continue

    def _cleanup_and_save(self, reduced_doc):
        """Clean up and save the reduced DXF file."""
        original_path = Path(self.dxf_filename)
        reduced_path = original_path.parent / f"{original_path.stem}_reduced{original_path.suffix}"

        try:
            # Ensure path exists
            reduced_path.parent.mkdir(parents=True, exist_ok=True)

            # Set essential DXF header variables (similar to the normal export)
            if '$ACADVER' not in reduced_doc.header:
                reduced_doc.header['$ACADVER'] = 'AC1027'  # AutoCAD 2013
            if '$DWGCODEPAGE' not in reduced_doc.header:
                reduced_doc.header['$DWGCODEPAGE'] = 'ANSI_1252'
            if '$MEASUREMENT' not in reduced_doc.header:
                reduced_doc.header['$MEASUREMENT'] = 1  # Metric
            if '$INSUNITS' not in reduced_doc.header:
                reduced_doc.header['$INSUNITS'] = 6  # Meters

            # Use atomic save for safety and reliability
            if atomic_save_dxf(reduced_doc, reduced_path, create_backup=True):
                log_info(f"Successfully created reduced DXF file: {reduced_path}")
            else:
                raise RuntimeError(f"Failed to save reduced DXF file: {reduced_path}")

        except Exception as e:
            log_error(f"Error creating reduced DXF: {str(e)}\n{traceback.format_exc()}")
            raise e



    def _clean_dictionaries(self, doc):
        """Clean up dictionaries that might cause copy issues"""
        try:
            # Method 1: Try to clean visual style references in the root dictionary
            if hasattr(doc, 'rootdict'):
                root_dict = doc.rootdict
                for key in list(root_dict.keys()):
                    if key.upper() in ['ACAD_VISUALSTYLE', 'VISUALSTYLE', 'ACAD_VISUALSTYLES']:
                        try:
                            del root_dict[key]
                            log_debug(f"Removed {key} from root dictionary")
                        except Exception as e:
                            log_warning(f"Could not remove {key} from root dictionary: {str(e)}")

            # Method 2: Remove visual style dictionaries from objects section if found
            # This uses safe iteration that works with both ezdxf 1.3.x and newer versions
            if hasattr(doc, 'objects'):
                try:
                    # Safe way to iterate through dictionaries
                    dictionaries = []
                    try:
                        # For newer ezdxf versions
                        dictionaries = list(doc.objects.query('DICTIONARY'))
                    except:
                        # Fallback for older versions
                        try:
                            for obj in doc.objects:
                                if hasattr(obj, 'dxftype') and callable(obj.dxftype) and obj.dxftype() == 'DICTIONARY':
                                    dictionaries.append(obj)
                        except:
                            pass

                    # Process all found dictionaries
                    for obj in dictionaries:
                        vs_dict = False
                        # Check if this might be a visual style dictionary
                        if hasattr(obj, 'keys'):
                            for key in list(obj.keys()):
                                if 'VISUALSTYLE' in key.upper() or 'VS' in key.upper() or 'ACAD' in key.upper():
                                    vs_dict = True
                                    try:
                                        del obj[key]
                                    except:
                                        pass

                            if vs_dict:
                                log_debug("Cleaned visual style dictionary entries")
                except Exception as e:
                    log_warning(f"Error cleaning dictionaries from objects: {str(e)}")
        except Exception as e:
            log_warning(f"Error during dictionary cleanup: {str(e)}")

    def _fix_header_issues(self, doc):
        """Fix any header issues that affect copying"""
        try:
            # Remove problematic header variables
            problematic_headers = [
                '$VSACUISTATE', '$VSMOVIETYPE', '$VSOBJECTDSP',
                '$VSLIGHTINGDSP', '$SHADOWPLANELOCATION',
                '$CMATERIAL', '$INTERFEREOBJVS', '$INTERFEREVPVS'
            ]

            for var in problematic_headers:
                if var in doc.header:
                    try:
                        del doc.header[var]
                    except:
                        pass
        except Exception as e:
            log_warning(f"Error fixing header issues: {str(e)}")

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
