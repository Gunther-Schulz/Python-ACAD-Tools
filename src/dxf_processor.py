import ezdxf
import traceback
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.entities.polyline import Polyline
from src.utils import log_info, log_warning, log_error, resolve_path, log_debug
from src.dxf_utils import ensure_layer_exists, attach_custom_data, sanitize_layer_name, initialize_document
from src.preprocessors.block_exploder import explode_blocks
from src.preprocessors.circle_extractor import extract_circle_centers
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
import math
import numpy as np
from src.shapefile_utils import write_shapefile
from pathlib import Path

class DXFProcessor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.crs = project_loader.crs
        
        # Configure operations from project settings
        dxf_operations = project_loader.project_settings.get('dxfOperations', {})
        self.transfers = dxf_operations.get('transfers', [])
        self.extracts = dxf_operations.get('extracts', [])
        
        # Register preprocessors
        self.preprocessors = {
            'block_exploder': explode_blocks,
            'circle_extractor': extract_circle_centers
        }
        
        log_debug(f"DXFProcessor initialized with {len(self.transfers)} transfers and {len(self.extracts)} extracts")

    def process_all(self, working_doc):
        """Process all DXF operations (transfers and extracts)"""
        log_debug(f"Starting DXF operations processing on document: {working_doc.filename}")
        
        if self.transfers:
            log_debug("Processing transfers...")
            self.process_transfers(working_doc)
        else:
            log_debug("No transfers to process")
            
        if self.extracts:
            log_debug("Processing extracts...")
            self.process_extracts(working_doc)
        else:
            log_debug("No extracts to process")

    def process_transfers(self, working_doc):
        """Process all DXF transfers defined in configuration"""
        if not self.transfers:
            return

        for transfer in self.transfers:
            try:
                external_dxf = resolve_path(transfer.get('externalDxf'), self.project_loader.folder_prefix)
                direction = transfer.get('direction', '').lower()
                
                log_debug(f"Processing transfer:")
                log_debug(f"- External DXF: {external_dxf}")
                log_debug(f"- Direction: {direction}")
                
                if direction not in ['load', 'save']:
                    log_warning(f"Invalid transfer direction: {direction}")
                    continue

                if direction == 'load':
                    self._process_load(external_dxf, transfer, working_doc)
                else:
                    self._process_save(external_dxf, transfer, working_doc)
                    
            except Exception as e:
                log_error(f"Error processing DXF transfer: {str(e)}")
                log_error(f"Traceback:\n{traceback.format_exc()}")

    def _process_load(self, external_dxf, transfer_config, working_doc):
        """Load entities from external DXF into working document"""
        try:
            external_doc = ezdxf.readfile(external_dxf)
            log_debug(f"Loading from external DXF: {external_dxf}")
            
            for operation in transfer_config.get('operations', []):
                from_layer = sanitize_layer_name(operation.get('fromLayer'))
                to_layer = sanitize_layer_name(operation.get('toLayer', from_layer))
                
                self._transfer_entities(
                    from_doc=external_doc,
                    to_doc=working_doc,
                    from_layer=from_layer,
                    to_layer=to_layer,
                    entity_types=operation.get('entityTypes'),
                    entity_filter=operation.get('filter')
                )
                
        except Exception as e:
            log_error(f"Error loading from {external_dxf}: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")

    def _process_save(self, external_dxf, transfer_config, working_doc):
        """Save entities from working document to external DXF"""
        try:
            # Try to open existing file first
            try:
                external_doc = ezdxf.readfile(external_dxf)
                log_debug(f"Opened existing external DXF: {external_dxf}")
            except:
                # If file doesn't exist, create new
                external_doc = ezdxf.new()
                log_debug("Created new empty DXF file")
            
            # Initialize the document with standard styles
            initialize_document(external_doc)
            
            for operation in transfer_config.get('operations', []):
                from_layer = sanitize_layer_name(operation.get('fromLayer'))
                to_layer = sanitize_layer_name(operation.get('toLayer', from_layer))
                
                self._transfer_entities(
                    from_doc=working_doc,
                    to_doc=external_doc,
                    from_layer=from_layer,
                    to_layer=to_layer,
                    entity_types=operation.get('entityTypes'),
                    entity_filter=operation.get('filter')
                )
            
            external_doc.saveas(external_dxf)
            log_debug(f"Saved to external DXF: {external_dxf}")
            
        except Exception as e:
            log_error(f"Error saving to {external_dxf}: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")

    def _transfer_entities(self, from_doc, to_doc, from_layer, to_layer=None, entity_types=None, entity_filter=None):
        """Transfer entities between documents"""
        try:
            msp_from = from_doc.modelspace()
            msp_to = to_doc.modelspace()
            entity_counts = {}
            
            # Build query string
            if entity_types and len(entity_types) == 1:
                query = f'{entity_types[0]}[layer=="{from_layer}"]'
            elif entity_types:
                # Process multiple entity types separately
                for entity_type in entity_types:
                    self._transfer_entities(from_doc, to_doc, from_layer, to_layer, [entity_type], entity_filter)
                return
            else:
                query = f'*[layer=="{from_layer}"]'
            
            log_debug(f"Using query: {query}")
            entities = msp_from.query(query)
            log_debug(f"Found {len(entities)} entities matching query")
            
            # Ensure target layer exists
            ensure_layer_exists(to_doc, to_layer if to_layer != 'same' else from_layer)
            
            for entity in entities:
                if entity_filter and not eval(entity_filter):
                    continue
                
                try:
                    dxftype = entity.dxftype()
                    dxfattribs = {k: v for k, v in entity.dxfattribs().items() if k != 'handle'}
                    dxfattribs['layer'] = to_layer if to_layer != 'same' else from_layer
                    
                    new_entity = None
                    
                    if dxftype == 'LINE':
                        new_entity = msp_to.add_line(
                            start=entity.dxf.start,
                            end=entity.dxf.end,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'CIRCLE':
                        new_entity = msp_to.add_circle(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'POINT':
                        new_entity = msp_to.add_point(
                            location=entity.dxf.location,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'LWPOLYLINE':
                        new_entity = msp_to.add_lwpolyline(
                            points=entity.get_points(),
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'TEXT':
                        new_entity = msp_to.add_text(
                            text=entity.dxf.text,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'MTEXT':
                        new_entity = msp_to.add_mtext(
                            text=entity.text,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'INSERT':
                        new_entity = msp_to.add_blockref(
                            name=entity.dxf.name,
                            insert=entity.dxf.insert,
                            dxfattribs=dxfattribs
                        )
                    elif dxftype == 'ARC':
                        new_entity = msp_to.add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=entity.dxf.start_angle,
                            end_angle=entity.dxf.end_angle,
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
                        new_entity = msp_to.add_hatch(
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
                    else:
                        log_warning(f"Unsupported entity type for copy: {dxftype}")
                        continue
                    
                    if new_entity:
                        attach_custom_data(new_entity, 'DXFEXPORTER')
                        entity_counts[dxftype] = entity_counts.get(dxftype, 0) + 1
                    
                except Exception as e:
                    log_warning(f"Failed to copy entity of type {dxftype}: {str(e)}")
                    continue
            
            # Log final counts
            log_info("=== Entity Transfer Summary ===")
            if not entity_counts:
                log_info("No entities were transferred")
            else:
                for entity_type, count in entity_counts.items():
                    log_info(f"Transferred {count} {entity_type} entities")
            log_info("===========================")
            
        except Exception as e:
            log_error(f"Error in _transfer_entities: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")

    def process_extracts(self, working_doc):
        """Process all DXF extracts defined in configuration"""
        if not self.extracts:
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
            doc = working_doc
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

    def _process_single_extract(self, doc, source_layer, output_file, preprocessors=None):
        """Process a single DXF extract operation"""
        try:
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)
            
            # Get all entities from the source layer
            entities = doc.modelspace().query(f'*[layer=="{source_layer}"]')
            
            if not entities:
                log_warning(f"No entities found in layer: {source_layer}")
                return
            
            # Apply preprocessors if any
            if preprocessors:
                for preprocessor_name in preprocessors:
                    preprocessor = self.preprocessors.get(preprocessor_name)
                    if preprocessor:
                        # Pass both entities and layer_name to preprocessor
                        entities = preprocessor(entities, source_layer)
                        log_debug(f"Applied preprocessor: {preprocessor_name}")
                    else:
                        log_warning(f"Preprocessor not found: {preprocessor_name}")
            
            # Separate geometries by type
            pt = []  # Points
            ln = []  # Lines
            pl = []  # Polygons
            pt_attrs = []
            ln_attrs = []
            pl_attrs = []

            for entity_data in entities:
                if isinstance(entity_data, dict):
                    # Handle preprocessed data (e.g., from circle_extractor)
                    if 'coords' in entity_data:
                        point = Point(entity_data['coords'])
                        if point.is_valid and not point.is_empty:
                            pt.append(point)
                            pt_attrs.append(entity_data.get('attributes', {}))
                else:
                    # Handle regular entities
                    if isinstance(entity_data, (LWPolyline, Polyline)):
                        points_list = list(entity_data.vertices())
                        if len(points_list) >= 2:
                            is_closed = (
                                (hasattr(entity_data, 'closed') and entity_data.closed) or
                                (len(points_list) >= 3 and 
                                 abs(points_list[0][0] - points_list[-1][0]) < 1e-10 and 
                                 abs(points_list[0][1] - points_list[-1][1]) < 1e-10)
                            )
                            
                            if is_closed and len(points_list) >= 3:
                                if abs(points_list[0][0] - points_list[-1][0]) >= 1e-10 or abs(points_list[0][1] - points_list[-1][1]) >= 1e-10:
                                    points_list.append(points_list[0])
                                polygon = Polygon(points_list)
                                if polygon.is_valid and not polygon.is_empty:
                                    pl.append(polygon)
                                    pl_attrs.append({})
                            else:
                                line = LineString(points_list)
                                if line.is_valid and not line.is_empty:
                                    ln.append(line)
                                    ln_attrs.append({})
                    elif isinstance(entity_data, ezdxf.entities.Line):
                        line = LineString([entity_data.dxf.start, entity_data.dxf.end])
                        if line.is_valid and not line.is_empty:
                            ln.append(line)
                            ln_attrs.append({})
                    elif isinstance(entity_data, ezdxf.entities.Point):
                        point = Point(entity_data.dxf.location[:2])
                        if point.is_valid and not point.is_empty:
                            pt.append(point)
                            pt_attrs.append({})

            # Write separate shapefiles for each geometry type
            base_path = str(Path(full_output_path).with_suffix(''))
            if pt:
                point_gdf = gpd.GeoDataFrame(geometry=pt, data=pt_attrs, crs=self.crs)
                write_shapefile(point_gdf, f"{base_path}_points.shp")
            if ln:
                line_gdf = gpd.GeoDataFrame(geometry=ln, data=ln_attrs, crs=self.crs)
                write_shapefile(line_gdf, f"{base_path}_lines.shp")
            if pl:
                polygon_gdf = gpd.GeoDataFrame(geometry=pl, data=pl_attrs, crs=self.crs)
                write_shapefile(polygon_gdf, f"{base_path}_polygons.shp")

        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}") 