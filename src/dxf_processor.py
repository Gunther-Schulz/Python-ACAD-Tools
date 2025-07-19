import ezdxf
import traceback
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.entities.polyline import Polyline
from src.utils import log_info, log_warning, log_error, resolve_path, log_debug
from src.dxf_utils import ensure_layer_exists, attach_custom_data, sanitize_layer_name, initialize_document, atomic_save_dxf
from src.preprocessors.block_exploder import explode_blocks
from src.preprocessors.circle_extractor import extract_circle_centers
from src.preprocessors.basepoint_extractor import extract_entity_basepoints
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
import math
import numpy as np
from src.shapefile_utils import write_shapefile
from pathlib import Path

# Define a constant for the polygon closure tolerance
POLYGON_CLOSURE_TOLERANCE = 0.5

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
            'circle_extractor': extract_circle_centers,
            'basepoint_extractor': extract_entity_basepoints
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

            # Use atomic save for safety
            if atomic_save_dxf(external_doc, external_dxf, create_backup=True):
                log_info(f"Successfully saved to external DXF: {external_dxf}")
            else:
                raise RuntimeError(f"Failed to save external DXF: {external_dxf}")

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

        for extract_config in self.extracts:
            source_dxf = extract_config.get('sourceDxf')
            layers = extract_config.get('layers', [])

            if not layers:
                log_warning(f"Skipping extract configuration without layers: {extract_config}")
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

            # Process each layer configuration
            for layer_config in layers:
                source_layer = layer_config.get('sourceLayer')
                output_file = layer_config.get('outputShapeFile')
                preprocessors = layer_config.get('preprocessors', [])

                if not source_layer or not output_file:
                    log_warning(f"Skipping invalid layer configuration: {layer_config}")
                    continue

                if source_layer not in doc.layers:
                    log_warning(f"Source layer '{source_layer}' not found in DXF document")
                    continue

                self._process_single_extract(doc, source_layer, output_file, preprocessors, layer_config)

    def _process_single_extract(self, doc, source_layer, output_file, preprocessors=None, extract=None):
        """Process a single DXF extract operation"""
        try:
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)

            # Build query string based on entity types if specified
            entity_types = extract.get('entityTypes', [])
            if entity_types and len(entity_types) == 1:
                query = f'{entity_types[0]}[layer=="{source_layer}"]'
            else:
                query = f'*[layer=="{source_layer}"]'

            # Get all entities from the source layer
            entities = doc.modelspace().query(query)

            if not entities:
                log_warning(f"No entities found in layer '{source_layer}' in document: {doc.filename}")
                return

            # If multiple entity types specified, filter after query
            if entity_types and len(entity_types) > 1:
                entities = [e for e in entities if e.dxftype() in entity_types]

            # Apply filter if specified
            if extract.get('filter'):
                entities = [entity for entity in entities if eval(extract['filter'])]

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
                        try:
                            points_list = []

                            if isinstance(entity_data, LWPolyline):
                                # LWPolyline stores points as (x, y, start_width, end_width, bulge)
                                try:
                                    for point in entity_data.get_points():
                                        # Take only x,y coordinates from the 5-tuple
                                        points_list.append((point[0], point[1]))
                                except Exception as e:
                                    log_warning(f"Failed to get points from LWPOLYLINE in layer '{source_layer}': {str(e)}")
                                    continue
                            else:
                                # Regular POLYLINE needs different vertex handling
                                try:
                                    # For regular POLYLINE, vertices is a list property, not a method
                                    if hasattr(entity_data, 'vertices'):
                                        for vertex in entity_data.vertices:
                                            if hasattr(vertex, 'dxf'):
                                                # Get coordinates from DXFVertex
                                                points_list.append((vertex.dxf.location.x, vertex.dxf.location.y))
                                            else:
                                                # Direct coordinate access
                                                points_list.append((vertex[0], vertex[1]))
                                except Exception as e:
                                    log_warning(f"Failed to get vertices from POLYLINE in layer '{source_layer}': {str(e)}")
                                    continue

                            if len(points_list) >= 2:
                                # Check both the closed attribute and if endpoints match (within tolerance)
                                is_closed = (
                                    (hasattr(entity_data, 'closed') and entity_data.closed) or
                                    (len(points_list) >= 3 and
                                     abs(points_list[0][0] - points_list[-1][0]) < POLYGON_CLOSURE_TOLERANCE and
                                     abs(points_list[0][1] - points_list[-1][1]) < POLYGON_CLOSURE_TOLERANCE)
                                )

                                if is_closed and len(points_list) >= 3:
                                    # Ensure the polygon is closed by adding first point if needed
                                    if abs(points_list[0][0] - points_list[-1][0]) >= POLYGON_CLOSURE_TOLERANCE or abs(points_list[0][1] - points_list[-1][1]) >= POLYGON_CLOSURE_TOLERANCE:
                                        points_list.append(points_list[0])
                                    polygon = Polygon(points_list)
                                    if polygon.is_valid and not polygon.is_empty:
                                        # Split MultiPolygon into constituent polygons
                                        if isinstance(polygon, MultiPolygon):
                                            for p in polygon.geoms:
                                                pl.append(p)
                                                pl_attrs.append({})
                                        else:
                                            pl.append(polygon)
                                            pl_attrs.append({})
                                else:
                                    line = LineString(points_list)
                                    if line.is_valid and not line.is_empty:
                                        ln.append(line)
                                        ln_attrs.append({})
                        except Exception as e:
                            entity_type = entity_data.dxftype() if hasattr(entity_data, 'dxftype') else type(entity_data).__name__
                            entity_handle = getattr(entity_data, 'dxf', {}).get('handle', 'unknown')
                            log_warning(f"Failed to process {entity_type} entity (handle: {entity_handle}) in layer '{source_layer}': {str(e)}")
                            continue

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
            geometries_written = False

            if pt:
                point_gdf = gpd.GeoDataFrame(geometry=pt, data=pt_attrs, crs=self.crs)
                write_shapefile(point_gdf, f"{base_path}_points.shp")
                geometries_written = True
            if ln:
                line_gdf = gpd.GeoDataFrame(geometry=ln, data=ln_attrs, crs=self.crs)
                write_shapefile(line_gdf, f"{base_path}_lines.shp")
                geometries_written = True
            if pl:
                polygon_gdf = gpd.GeoDataFrame(geometry=pl, data=pl_attrs, crs=self.crs)
                write_shapefile(polygon_gdf, f"{base_path}_polygons.shp")
                geometries_written = True

            if not geometries_written:
                log_warning(f"No valid geometries found to write for layer '{source_layer}' in {doc.filename}")

        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")
            log_error(f"Traceback:\n{traceback.format_exc()}")
