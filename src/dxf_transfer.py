import ezdxf
from src.utils import log_info, log_warning, log_error, resolve_path
from src.dxf_utils import ensure_layer_exists, remove_entities_by_layer, update_layer_properties, attach_custom_data

class DXFTransfer:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.transfers = project_loader.project_settings.get('dxfTransfer', [])
        
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
            log_info(f"Loading from external DXF: {external_dxf}")
            
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
            # Create new or open existing external DXF
            try:
                external_doc = ezdxf.readfile(external_dxf)
                log_info(f"Opened existing external DXF: {external_dxf}")
            except:
                external_doc = ezdxf.new()
                log_info(f"Created new external DXF: {external_dxf}")
            
            for transfer in transfer_config.get('transfers', []):
                from_layer = transfer.get('fromLayer')
                to_layer = transfer.get('toLayer')
                
                # First remove existing entities from target layer
                if to_layer == 'same' or to_layer is None:
                    target_layer_name = from_layer
                else:
                    target_layer_name = to_layer
                    
                if from_layer != '*':  # Only remove if not copying all layers
                    log_info(f"Removing existing entities from layer: {target_layer_name}")
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
                
            external_doc.saveas(external_dxf)
            log_info(f"Saved to external DXF: {external_dxf}")
            
        except Exception as e:
            log_error(f"Error saving to {external_dxf}: {str(e)}")

    def _transfer_entities(self, from_doc, to_doc, from_layer, to_layer=None, entity_types=None, entity_filter=None):
        """Transfer entities between documents"""
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
            
            # Ensure target layer exists with same properties
            ensure_layer_exists(to_doc, target_layer_name)
            update_layer_properties(to_doc.layers.get(target_layer_name), layer)
            
            # Get entities from source layer
            entities = from_doc.modelspace().query(f'*[layer=="{source_layer_name}"]')
            
            # Apply entity type filter if specified
            if entity_types:
                entities = [e for e in entities if e.dxftype() in entity_types]
                
            # Apply custom filter if specified
            if entity_filter:
                entities = self._apply_filter(entities, entity_filter)
            
            # Copy entities to target document
            for entity in entities:
                try:
                    new_entity = to_doc.modelspace().add_entity_in_layout(
                        entity.dxftype(),
                        dxfattribs=entity.dxfattribs()
                    )
                    new_entity.dxf.layer = target_layer_name
                    attach_custom_data(new_entity, entity)
                except Exception as e:
                    log_warning(f"Failed to copy entity: {str(e)}")

    def _apply_filter(self, entities, filter_config):
        """Apply filter configuration to entities"""
        filtered = entities
        
        if 'created_by_script' in filter_config:
            created_by_script = filter_config['created_by_script']
            filtered = [e for e in filtered if hasattr(e, 'has_xdata') and 
                       bool(e.get_xdata('DXFEXPORTER')) == created_by_script]
            
        # Add more filter conditions here as needed
        
        return filtered