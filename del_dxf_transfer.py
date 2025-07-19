import ezdxf
from src.utils import log_info, log_warning, log_error, resolve_path, log_debug
from src.dxf_utils import ensure_layer_exists, remove_entities_by_layer, update_layer_properties, attach_custom_data, sanitize_layer_name, initialize_document, atomic_save_dxf

class DXFTransfer:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.transfers = project_loader.project_settings.get('dxfTransfer', [])
        self.name_to_aci = project_loader.name_to_aci
        log_debug(f"DXFTransfer initialized with {len(self.transfers)} transfers")
        if not self.transfers:
            log_debug("No DXF transfers found in project settings")
        else:
            for transfer in self.transfers:
                log_debug(f"Found transfer config: {transfer}")

    def process_transfers(self, working_doc):
        """Process all DXF transfers defined in configuration"""
        if not self.transfers:
            return

        for transfer in self.transfers:
            try:
                external_dxf = resolve_path(transfer.get('externalDxf'), self.project_loader.folder_prefix)
                direction = transfer.get('direction', '').lower()

                if direction not in ['load', 'save']:
                    log_warning(f"Invalid transfer direction: {direction}")
                    continue

                if direction == 'load':
                    self._process_load(external_dxf, transfer, working_doc)
                else:
                    self._process_save(external_dxf, transfer, working_doc)

            except Exception as e:
                log_error(f"Error processing DXF transfer: {str(e)}")

    def _process_load(self, external_dxf, transfer_config, working_doc):
        """Load entities from external DXF into working document"""
        try:
            external_doc = ezdxf.readfile(external_dxf)
            log_debug(f"Loading from external DXF: {external_dxf}")

            for transfer in transfer_config.get('transfers', []):
                self._transfer_entities(
                    from_doc=external_doc,
                    to_doc=working_doc,
                    from_layer=transfer.get('fromLayer'),
                    to_layer=transfer.get('toLayer'),
                    entity_types=transfer.get('entityTypes'),
                    entity_filter=transfer.get('filter')
                )

        except Exception as e:
            log_error(f"Error loading from {external_dxf}: {str(e)}")

    def _process_save(self, external_dxf, transfer_config, working_doc):
        """Save entities from working document to external DXF"""
        try:
            # Try to open existing file first
            try:
                external_doc = ezdxf.readfile(external_dxf)
                log_debug(f"Opened existing external DXF: {external_dxf}")
            except:
                # If file doesn't exist, try to use template
                template_dxf = self.project_loader.project_settings.get('templateDxfFilename')
                if template_dxf:
                    template_path = resolve_path(template_dxf, self.project_loader.folder_prefix)
                    try:
                        external_doc = ezdxf.readfile(template_path)
                        log_debug(f"Created new external DXF from template: {template_path}")
                    except Exception as e:
                        log_warning(f"Failed to load template DXF {template_path}: {str(e)}")
                        external_doc = ezdxf.new()
                        log_debug("Created new empty DXF file")
                else:
                    external_doc = ezdxf.new()
                    log_debug("Created new empty DXF file")

            # Initialize the document with standard styles
            initialize_document(external_doc)

            for transfer in transfer_config.get('transfers', []):
                from_layer = transfer.get('fromLayer')
                to_layer = transfer.get('toLayer')

                # Sanitize layer names
                from_layer = sanitize_layer_name(from_layer)
                to_layer = sanitize_layer_name(to_layer) if to_layer else from_layer

                # First remove existing entities from target layer
                if to_layer == 'same' or to_layer is None:
                    target_layer_name = from_layer
                else:
                    target_layer_name = to_layer

                if from_layer != '*':  # Only remove if not copying all layers
                    log_debug(f"Removing existing entities from layer: {target_layer_name}")
                    remove_entities_by_layer(external_doc.modelspace(), target_layer_name, 'DXFEXPORTER')

                # Then transfer new entities
                self._transfer_entities(
                    from_doc=working_doc,
                    to_doc=external_doc,
                    from_layer=from_layer,
                    to_layer=to_layer,
                    entity_types=transfer.get('entityTypes'),
                    entity_filter=transfer.get('filter')
                )

            # Use atomic save for safety
            if atomic_save_dxf(external_doc, external_dxf, create_backup=True):
                log_info(f"Successfully saved to external DXF: {external_dxf}")
            else:
                raise RuntimeError(f"Failed to save external DXF: {external_dxf}")

        except Exception as e:
            log_error(f"Error saving to {external_dxf}: {str(e)}")

    def _transfer_entities(self, from_doc, to_doc, from_layer, to_layer=None, entity_types=None, entity_filter=None):
        """Transfer entities between documents (modelspace only)"""
        # Initialize counters
        entity_counts = {}

        if from_layer == '*':
            layers = from_doc.layers
        else:
            layers = [from_doc.layers.get(from_layer)]

        # If to_layer is None or not specified, use the same layer name(s)
        to_layer = to_layer or 'same'

        for layer in layers:
            source_layer_name = layer.dxf.name
            target_layer_name = source_layer_name if to_layer == 'same' else to_layer

            # Skip if source layer doesn't exist
            if not layer:
                log_warning(f"Source layer not found: {source_layer_name}")
                continue

            # Get entities from source layer (modelspace only)
            entities = from_doc.modelspace().query(f'*[layer=="{source_layer_name}"]')

            # Debug: Log what we found
            log_debug(f"Found {len(entities)} entities on layer '{source_layer_name}'")
            entity_types_found = set(e.dxftype() for e in entities)
            log_debug(f"Entity types found on layer: {entity_types_found}")

            # Apply entity type filter if specified
            if entity_types:
                log_debug(f"Filtering for entity types: {entity_types}")
                entities = [e for e in entities if e.dxftype() in entity_types]
                log_debug(f"After filtering: {len(entities)} entities")

            # Apply custom filter if specified
            if entity_filter:
                entities = self._apply_filter(entities, entity_filter)

            # Copy entities to target document's modelspace
            msp = to_doc.modelspace()
            for entity in entities:
                try:
                    dxftype = entity.dxftype()
                    log_debug(f"Processing entity of type: {dxftype}")

                    # Create a clean copy of attributes without handle
                    dxfattribs = {k: v for k, v in entity.dxfattribs().items() if k != 'handle'}
                    dxfattribs['layer'] = target_layer_name

                    # Create new entity based on type
                    new_entity = None

                    if dxftype == 'LINE':
                        new_entity = msp.add_line(
                            start=entity.dxf.start,
                            end=entity.dxf.end,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'POINT':
                        new_entity = msp.add_point(
                            location=entity.dxf.location,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'HATCH':
                        # Get the boundary paths
                        paths = []
                        for path in entity.paths:
                            if path.path_type_flags & 2:  # Polyline path
                                points = [(vertex[0], vertex[1]) for vertex in path.vertices]
                                paths.append(points)
                            else:  # Edge path
                                edges = []
                                for edge in path.edges:
                                    if edge.EDGE_TYPE == "LineEdge":
                                        edges.extend([edge.start, edge.end])
                                if edges:
                                    paths.append(edges)

                        # Create new hatch
                        new_entity = msp.add_hatch(
                            color=entity.dxf.color,
                            dxfattribs={
                                **dxfattribs,
                                'pattern_name': entity.dxf.pattern_name,
                                'solid_fill': entity.dxf.solid_fill,
                                'pattern_scale': entity.dxf.pattern_scale,
                                'pattern_angle': entity.dxf.pattern_angle,
                            }
                        )

                        # Add the boundary paths
                        for path in paths:
                            try:
                                new_entity.paths.add_polyline_path(
                                    path,
                                    is_closed=True,
                                    flags=1
                                )
                            except Exception as e:
                                log_warning(f"Failed to add hatch boundary path: {str(e)}")

                    elif dxftype == 'CIRCLE':
                        new_entity = msp.add_circle(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'ARC':
                        new_entity = msp.add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=entity.dxf.start_angle,
                            end_angle=entity.dxf.end_angle,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'LWPOLYLINE':
                        new_entity = msp.add_lwpolyline(
                            points=entity.get_points(),
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'TEXT':
                        new_entity = msp.add_text(
                            text=entity.dxf.text,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'MTEXT':
                        new_entity = msp.add_mtext(
                            text=entity.text,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'INSERT':
                        new_entity = msp.add_blockref(
                            name=entity.dxf.name,
                            insert=entity.dxf.insert,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'DIMENSION':
                        # Handle different dimension types
                        dimtype = entity.dimtype
                        if dimtype == 0:  # Linear dimension
                            new_entity = msp.add_linear_dim(
                                base=entity.dxf.defpoint,  # Dimension line location
                                p1=entity.dxf.defpoint2,   # First extension line
                                p2=entity.dxf.defpoint3,   # Second extension line
                                dxfattribs=dxfattribs
                            )
                        elif dimtype == 1:  # Aligned dimension
                            new_entity = msp.add_aligned_dim(
                                p1=entity.dxf.defpoint2,   # First extension line
                                p2=entity.dxf.defpoint3,   # Second extension line
                                distance=entity.dxf.defpoint[1],  # Distance from the dimension line to p1/p2
                                dxfattribs=dxfattribs
                            )
                        elif dimtype == 2:  # Angular dimension
                            new_entity = msp.add_angular_dim(
                                center=entity.dxf.defpoint,
                                p1=entity.dxf.defpoint2,
                                p2=entity.dxf.defpoint3,
                                distance=entity.dxf.defpoint[1],  # Distance from dimension line to center
                                dxfattribs=dxfattribs
                            )
                        elif dimtype == 3:  # Diameter dimension
                            new_entity = msp.add_diameter_dim(
                                center=entity.dxf.defpoint,
                                radius=entity.measurement,
                                angle=0,
                                dxfattribs=dxfattribs
                            )
                        elif dimtype == 4:  # Radius dimension
                            new_entity = msp.add_radius_dim(
                                center=entity.dxf.defpoint,
                                radius=entity.measurement,
                                angle=0,
                                dxfattribs=dxfattribs
                            )
                        else:
                            log_warning(f"Unsupported dimension type: {dimtype}")
                            continue
                    else:
                        log_warning(f"Unsupported entity type for copy: {dxftype}")
                        continue

                    # Important: Attach custom data to mark as created by our script
                    if new_entity:
                        attach_custom_data(new_entity, 'DXFEXPORTER')
                        entity_counts[dxftype] = entity_counts.get(dxftype, 0) + 1

                except Exception as e:
                    log_warning(f"Failed to copy entity of type {dxftype}: {str(e)}")
                    # Decrement counter if entity failed to copy
                    entity_counts[dxftype] = entity_counts.get(dxftype, 1) - 1

        # Log final counts
        log_info("=== Entity Transfer Summary ===")
        if not entity_counts:
            log_info("No entities were transferred")
        else:
            for entity_type, count in entity_counts.items():
                log_info(f"Transferred {count} {entity_type} entities")
        log_info("===========================")

        return entity_counts  # Return counts for potential further use

    def _apply_filter(self, entities, filter_config):
        """Apply filter configuration to entities"""
        filtered = entities

        if 'created_by_script' in filter_config:
            created_by_script = filter_config['created_by_script']
            filtered = [e for e in filtered if hasattr(e, 'has_xdata') and
                       bool(e.get_xdata('DXFEXPORTER')) == created_by_script]

        # Add more filter conditions here as needed

        return filtered
