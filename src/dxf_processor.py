import ezdxf
import geopandas as gpd
from pathlib import Path
import traceback
import math
import numpy as np

from shapely import MultiPolygon
from shapely.geometry import LineString, Point, Polygon
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists, log_debug
from src.dxf_utils import ensure_layer_exists, remove_entities_by_layer, attach_custom_data, sanitize_layer_name, initialize_document
from src.shapefile_utils import write_shapefile
from src.preprocessors.block_exploder import explode_blocks
from src.preprocessors.circle_extractor import extract_circle_centers

class DXFProcessor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.crs = project_loader.crs
        
        # Configure operations from project settings
        self.transfers = project_loader.project_settings.get('dxfTransfer', [])
        self.extracts = project_loader.project_settings.get('updateFromSource', [])
        
        # Register preprocessors
        self.preprocessors = {
            'block_exploder': explode_blocks,
            'circle_extractor': extract_circle_centers
        }
        
        log_debug(f"DXFProcessor initialized with {len(self.transfers)} transfers and {len(self.extracts)} extracts")

    def process_all(self, working_doc):
        """Process all DXF operations (transfers and extracts)"""
        if self.transfers:
            self.process_transfers(working_doc)
            
        if self.extracts:
            self.process_extracts(working_doc)

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

    def process_extracts(self, default_doc):
        """Process all DXF extracts defined in updateFromSource configuration"""
        if not self.extracts:
            log_debug("No DXF extracts configured")
            return
        
        for extract in self.extracts:
            source_layer = extract.get('sourceLayer')
            output_file = extract.get('outputShapeFile')
            source_dxf = extract.get('sourceDxf')
            preprocessors = extract.get('preprocessors', [])
            
            if not source_layer or not output_file:
                log_warning(f"Skipping invalid DXF extract configuration: {extract}")
                continue
            
            # Load alternative DXF if specified
            doc = default_doc
            if source_dxf:
                try:
                    full_source_path = resolve_path(source_dxf, self.project_loader.folder_prefix)
                    doc = ezdxf.readfile(full_source_path)
                except Exception as e:
                    log_error(f"Failed to load alternative DXF {source_dxf}: {str(e)}")
                    continue
            
            if source_layer not in doc.layers:
                log_warning(f"Source layer '{source_layer}' not found in DXF document")
                continue
                
            self._process_single_extract(doc, source_layer, output_file, preprocessors)

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
            # Try to open existing file or create new one
            try:
                external_doc = ezdxf.readfile(external_dxf)
                log_debug(f"Opened existing external DXF: {external_dxf}")
            except:
                template_dxf = self.project_loader.project_settings.get('templateDxfFilename')
                if template_dxf:
                    template_path = resolve_path(template_dxf, self.project_loader.folder_prefix)
                    try:
                        external_doc = ezdxf.readfile(template_path)
                        log_debug(f"Created new external DXF from template: {template_path}")
                    except:
                        external_doc = ezdxf.new()
                        log_debug("Created new empty DXF file (template failed)")
                else:
                    external_doc = ezdxf.new()
                    log_debug("Created new empty DXF file")
            
            initialize_document(external_doc)
            
            for transfer in transfer_config.get('transfers', []):
                from_layer = transfer.get('fromLayer')
                to_layer = transfer.get('toLayer')
                
                from_layer = sanitize_layer_name(from_layer)
                to_layer = sanitize_layer_name(to_layer) if to_layer else from_layer
                
                target_layer_name = to_layer if to_layer != 'same' else from_layer
                
                if from_layer != '*':
                    remove_entities_by_layer(external_doc.modelspace(), target_layer_name, 'DXFEXPORTER')
                
                self._transfer_entities(
                    from_doc=working_doc,
                    to_doc=external_doc,
                    from_layer=from_layer,
                    to_layer=to_layer,
                    entity_types=transfer.get('entityTypes'),
                    entity_filter=transfer.get('filter')
                )
                
            external_doc.saveas(external_dxf)
            log_debug(f"Saved to external DXF: {external_dxf}")
            
        except Exception as e:
            log_error(f"Error saving to {external_dxf}: {str(e)}")

    def _process_single_extract(self, doc, source_layer, output_file, preprocessors=None):
        """Extract geometries from a single DXF layer and save to shapefile"""
        try:
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)
            output_dir = str(Path(full_output_path).parent)
            
            if not ensure_path_exists(output_dir):
                log_error(f"Could not create output directory: {output_dir}")
                return

            msp = doc.modelspace()
            entities = msp.query(f'*[layer=="{source_layer}"]')
            log_debug(f"Found {len(entities)} entities in layer {source_layer}")

            if preprocessors:
                processed_data = self._apply_preprocessors(entities, preprocessors, source_layer)
                if processed_data:
                    self._save_preprocessed_data(processed_data, full_output_path)
            else:
                self._extract_and_save_geometries(entities, source_layer, full_output_path)

        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")

    def _apply_preprocessors(self, entities, preprocessors, source_layer):
        """Apply preprocessors to entities"""
        processed_data = entities
        for preprocessor in preprocessors:
            if preprocessor not in self.preprocessors:
                log_warning(f"Preprocessor '{preprocessor}' not found, skipping")
                continue
            
            log_debug(f"Applying preprocessor: {preprocessor}")
            processed_data = self.preprocessors[preprocessor](processed_data, source_layer)
            log_debug(f"Preprocessor {preprocessor} produced {len(processed_data)} features")
        
        return processed_data

    def _save_preprocessed_data(self, processed_data, output_path):
        """Save preprocessed data to shapefile"""
        if isinstance(processed_data[0], dict):
            points_df = gpd.GeoDataFrame(
                geometry=[gpd.points_from_xy([p['coords'][0]], [p['coords'][1]])[0] for p in processed_data],
                data=[p['attributes'] for p in processed_data],
                crs=self.crs
            )
        else:
            points_df = gpd.GeoDataFrame(
                geometry=[gpd.points_from_xy([p[0]], [p[1]])[0] for p in processed_data],
                crs=self.crs
            )
        
        if write_shapefile(points_df, output_path):
            log_debug(f"Successfully saved {len(processed_data)} processed features")
        else:
            log_error(f"Failed to write {len(processed_data)} processed features")

    def _extract_and_save_geometries(self, entities, source_layer, output_path):
        """Extract geometries from entities and save to shapefile"""
        geometries = []
        attributes = []
        unsupported_types = set()
        entity_counts = {}

        for entity in entities:
            dxftype = entity.dxftype()
            entity_counts[dxftype] = entity_counts.get(dxftype, 0) + 1
            
            try:
                geom, attrs = self._convert_entity_to_geometry(entity)
                if geom:
                    geometries.append(geom)
                    attributes.append(attrs)
                else:
                    unsupported_types.add(dxftype)
            except Exception as e:
                log_warning(f"Error processing {dxftype}: {str(e)}")
                continue

        if geometries:
            gdf = gpd.GeoDataFrame(geometry=geometries, data=attributes, crs=self.crs)
            if write_shapefile(gdf, output_path):
                log_debug(f"Successfully saved {len(geometries)} features")
            else:
                log_error(f"Failed to write {len(geometries)} features")
        else:
            if unsupported_types:
                log_warning(f"No supported geometries found. Unsupported types: {', '.join(sorted(unsupported_types))}")
            else:
                log_warning(f"No geometries found. Entity counts: {entity_counts}")

    def _convert_entity_to_geometry(self, entity):
        """Convert a DXF entity to a Shapely geometry"""
        dxftype = entity.dxftype()
        attrs = {}

        if dxftype == 'LINE':
            return LineString([(entity.dxf.start[0], entity.dxf.start[1]), 
                             (entity.dxf.end[0], entity.dxf.end[1])]), attrs
        
        elif dxftype == 'CIRCLE':
            return Point(entity.dxf.center[0], entity.dxf.center[1]), {'radius': entity.dxf.radius}
        
        elif dxftype == 'POINT':
            return Point(entity.dxf.location[0], entity.dxf.location[1]), attrs
        
        elif dxftype == 'LWPOLYLINE':
            points = [(vertex[0], vertex[1]) for vertex in entity.get_points()]
            if len(points) > 1:
                if entity.closed:
                    points.append(points[0])
                    return Polygon(points), attrs
                return LineString(points), attrs
        
        elif dxftype == 'POLYLINE':
            points = [(vertex.dxf.location[0], vertex.dxf.location[1]) 
                     for vertex in entity.vertices]
            if len(points) > 1:
                if entity.is_closed:
                    points.append(points[0])
                    return Polygon(points), attrs
                return LineString(points), attrs
        
        elif dxftype == 'ARC':
            return self._convert_arc_to_linestring(entity), attrs
        
        elif dxftype == 'SPLINE':
            points = [(point[0], point[1]) for point in entity.control_points]
            if len(points) > 1:
                if entity.closed:
                    points.append(points[0])
                    return Polygon(points), attrs
                return LineString(points), attrs
        
        elif dxftype == 'HATCH':
            boundaries = []
            for path in entity.paths:
                points = [(vertex[0], vertex[1]) for vertex in path.vertices]
                if len(points) > 2:
                    points.append(points[0])
                    boundaries.append(Polygon(points))
            if boundaries:
                return MultiPolygon(boundaries), attrs

        return None, attrs

    def _convert_arc_to_linestring(self, entity):
        """Convert an arc entity to a LineString with segments"""
        start_angle = math.degrees(entity.dxf.start_angle)
        end_angle = math.degrees(entity.dxf.end_angle)
        radius = entity.dxf.radius
        center = entity.dxf.center
        
        num_segments = 32
        if end_angle < start_angle:
            end_angle += 360
        angles = np.linspace(start_angle, end_angle, num_segments)
        
        points = []
        for angle in angles:
            rad_angle = math.radians(angle)
            x = center[0] + radius * math.cos(rad_angle)
            y = center[1] + radius * math.sin(rad_angle)
            points.append((x, y))
            
        return LineString(points)

    def _transfer_entities(self, from_doc, to_doc, from_layer, to_layer=None, entity_types=None, entity_filter=None):
        """Transfer entities between documents"""
        entity_counts = {}
        
        if from_layer == '*':
            layers = from_doc.layers
        else:
            layers = [from_doc.layers.get(from_layer)]
            
        to_layer = to_layer or 'same'
        
        for layer in layers:
            source_layer_name = layer.dxf.name
            target_layer_name = source_layer_name if to_layer == 'same' else to_layer
            
            if not layer:
                log_warning(f"Source layer not found: {source_layer_name}")
                continue
            
            entities = from_doc.modelspace().query(f'*[layer=="{source_layer_name}"]')
            
            if entity_types:
                entities = [e for e in entities if e.dxftype() in entity_types]
            
            if entity_filter:
                entities = self._apply_filter(entities, entity_filter)
            
            self._copy_entities(entities, to_doc.modelspace(), target_layer_name, entity_counts)
        
        self._log_transfer_summary(entity_counts)
        return entity_counts

    def _copy_entities(self, entities, msp, target_layer, entity_counts):
        """Copy entities to target modelspace"""
        for entity in entities:
            try:
                dxftype = entity.dxftype()
                dxfattribs = {k: v for k, v in entity.dxfattribs().items() if k != 'handle'}
                dxfattribs['layer'] = target_layer
                
                new_entity = self._create_entity_copy(entity, msp, dxfattribs)
                
                if new_entity:
                    attach_custom_data(new_entity, 'DXFEXPORTER')
                    entity_counts[dxftype] = entity_counts.get(dxftype, 0) + 1
                
            except Exception as e:
                log_warning(f"Failed to copy {dxftype}: {str(e)}")

    def _create_entity_copy(self, entity, msp, dxfattribs):
        """Create a copy of an entity in the target modelspace"""
        dxftype = entity.dxftype()
        
        if dxftype == 'LINE':
            return msp.add_line(start=entity.dxf.start, end=entity.dxf.end, dxfattribs=dxfattribs)
        elif dxftype == 'POINT':
            return msp.add_point(location=entity.dxf.location, dxfattribs=dxfattribs)
        elif dxftype == 'CIRCLE':
            return msp.add_circle(center=entity.dxf.center, radius=entity.dxf.radius, dxfattribs=dxfattribs)
        elif dxftype == 'ARC':
            return msp.add_arc(center=entity.dxf.center, radius=entity.dxf.radius,
                             start_angle=entity.dxf.start_angle, end_angle=entity.dxf.end_angle,
                             dxfattribs=dxfattribs)
        elif dxftype == 'LWPOLYLINE':
            return msp.add_lwpolyline(points=entity.get_points(), dxfattribs=dxfattribs)
        elif dxftype == 'TEXT':
            return msp.add_text(text=entity.dxf.text, dxfattribs=dxfattribs)
        elif dxftype == 'MTEXT':
            return msp.add_mtext(text=entity.text, dxfattribs=dxfattribs)
        elif dxftype == 'INSERT':
            return msp.add_blockref(name=entity.dxf.name, insert=entity.dxf.insert, dxfattribs=dxfattribs)
        
        log_warning(f"Unsupported entity type for copy: {dxftype}")
        return None

    def _apply_filter(self, entities, filter_config):
        """Apply filter configuration to entities"""
        filtered = entities
        
        if 'created_by_script' in filter_config:
            created_by_script = filter_config['created_by_script']
            filtered = [e for e in filtered if hasattr(e, 'has_xdata') and 
                       bool(e.get_xdata('DXFEXPORTER')) == created_by_script]
        
        return filtered

    def _log_transfer_summary(self, entity_counts):
        """Log summary of transferred entities"""
        log_info("=== Entity Transfer Summary ===")
        if not entity_counts:
            log_info("No entities were transferred")
        else:
            for entity_type, count in entity_counts.items():
                log_info(f"Transferred {count} {entity_type} entities")
        log_info("===========================") 