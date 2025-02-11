from typing import Dict, Any, List, Optional, Union, Tuple
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from shapely.geometry import LineString, Point, Polygon, MultiPolygon, MultiLineString
import geopandas as gpd
from pathlib import Path

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error
from ..utils.dxf import (
    create_document, load_document, save_document,
    cleanup_document, get_layout, copy_entity
)

class DXFExporter(BaseProcessor):
    """Processor for exporting geometries to DXF format."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the DXF exporter.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self.template_doc: Optional[Drawing] = None
        self._initialize()

    def _initialize(self) -> None:
        """Initialize DXF exporter resources."""
        # Load template if specified
        if self.config.project_config.template_dxf:
            try:
                self.template_doc = load_document(
                    self.config.project_config.template_dxf
                )
                log_info(f"Loaded template DXF: {self.config.project_config.template_dxf}")
            except Exception as e:
                log_error(f"Error loading template DXF: {str(e)}")
                self.template_doc = None

    def export_to_dxf(self, processed_layers: Dict[str, gpd.GeoDataFrame]) -> None:
        """Export processed layers to DXF.
        
        Args:
            processed_layers: Dictionary of layer name to GeoDataFrame
        """
        # Create or load base document
        self.doc = self._load_or_create_dxf()
        if not self.doc:
            return

        try:
            # Process each layer
            for layer_name, gdf in processed_layers.items():
                self._export_layer(layer_name, gdf)

            # Apply DXF operations if configured
            if self.config.project_config.dxf_operations:
                self._apply_dxf_operations()

            # Clean up and save
            cleanup_document(self.doc)
            save_document(
                self.doc,
                self.config.project_config.dxf_filename,
                encoding='utf-8'
            )
            log_info(f"Exported DXF to {self.config.project_config.dxf_filename}")

        except Exception as e:
            log_error(f"Error exporting to DXF: {str(e)}")
            raise

    def _load_or_create_dxf(self) -> Optional[Drawing]:
        """Load existing DXF or create new one.
        
        Returns:
            DXF document or None if creation fails
        """
        dxf_path = Path(self.config.project_config.dxf_filename)
        
        try:
            if self.template_doc:
                # Use template as base
                doc = self.template_doc
                log_info("Using template as base document")
            elif dxf_path.exists():
                # Load existing file
                doc = load_document(dxf_path)
                log_info(f"Loaded existing DXF: {dxf_path}")
            else:
                # Create new document
                doc = create_document(self.config.project_config.dxf_version)
                log_info(f"Created new DXF document with version {self.config.project_config.dxf_version}")
            
            return doc

        except Exception as e:
            log_error(f"Error creating/loading DXF document: {str(e)}")
            return None

    def _export_layer(self, layer_name: str, gdf: gpd.GeoDataFrame) -> None:
        """Export a GeoDataFrame to a DXF layer.
        
        Args:
            layer_name: Name of the layer
            gdf: GeoDataFrame to export
        """
        if not self.validate_document():
            return

        # Ensure layer exists
        if layer_name not in self.doc.layers:
            self.doc.layers.new(layer_name)
            log_debug(f"Created new layer: {layer_name}")

        # Get target layout
        layout = get_layout(self.doc)

        # Export each geometry
        for geom in gdf.geometry:
            try:
                self._export_geometry(geom, layout, layer_name)
            except Exception as e:
                log_warning(f"Error exporting geometry in layer {layer_name}: {str(e)}")

    def _export_geometry(self, geom: Union[Point, LineString, Polygon],
                        layout: Layout, layer_name: str) -> None:
        """Export a single geometry to DXF.
        
        Args:
            geom: Geometry to export
            layout: Target layout
            layer_name: Target layer name
        """
        if isinstance(geom, Point):
            self._export_point(geom, layout, layer_name)
        elif isinstance(geom, LineString):
            self._export_linestring(geom, layout, layer_name)
        elif isinstance(geom, Polygon):
            self._export_polygon(geom, layout, layer_name)
        elif isinstance(geom, (MultiPolygon, MultiLineString)):
            for part in geom.geoms:
                self._export_geometry(part, layout, layer_name)
        else:
            log_warning(f"Unsupported geometry type: {type(geom)}")

    def _export_point(self, point: Point, layout: Layout, layer_name: str) -> None:
        """Export a point geometry to DXF.
        
        Args:
            point: Point to export
            layout: Target layout
            layer_name: Target layer name
        """
        layout.add_point(
            point.coords[0],
            dxfattribs={'layer': layer_name}
        )

    def _export_linestring(self, line: LineString, layout: Layout, layer_name: str) -> None:
        """Export a linestring geometry to DXF.
        
        Args:
            line: LineString to export
            layout: Target layout
            layer_name: Target layer name
        """
        coords = list(line.coords)
        if len(coords) == 2:
            # Simple line
            layout.add_line(
                start=coords[0],
                end=coords[1],
                dxfattribs={'layer': layer_name}
            )
        else:
            # Polyline
            polyline = layout.add_lwpolyline(
                points=coords,
                dxfattribs={'layer': layer_name}
            )
            if coords[0] == coords[-1]:
                polyline.closed = True

    def _export_polygon(self, polygon: Polygon, layout: Layout, layer_name: str) -> None:
        """Export a polygon geometry to DXF.
        
        Args:
            polygon: Polygon to export
            layout: Target layout
            layer_name: Target layer name
        """
        # Export exterior ring
        exterior_coords = list(polygon.exterior.coords)
        exterior = layout.add_lwpolyline(
            points=exterior_coords,
            dxfattribs={'layer': layer_name}
        )
        exterior.closed = True

        # Export interior rings (holes)
        for interior in polygon.interiors:
            interior_coords = list(interior.coords)
            interior_line = layout.add_lwpolyline(
                points=interior_coords,
                dxfattribs={'layer': layer_name}
            )
            interior_line.closed = True

    def _apply_dxf_operations(self) -> None:
        """Apply configured DXF operations."""
        operations = self.config.project_config.dxf_operations
        if not operations:
            return

        try:
            # Handle extracts (copying entities between layers)
            for extract in operations.get('extracts', []):
                self._apply_extract(extract)

            # Handle transfers (moving entities between layouts)
            for transfer in operations.get('transfers', []):
                self._apply_transfer(transfer)

        except Exception as e:
            log_error(f"Error applying DXF operations: {str(e)}")
            raise

    def _apply_extract(self, extract: Dict[str, Any]) -> None:
        """Apply an extract operation.
        
        Args:
            extract: Extract operation configuration
        """
        source_layer = extract.get('sourceLayer')
        target_layer = extract.get('targetLayer')
        
        if not source_layer or not target_layer:
            log_warning("Extract operation missing source or target layer")
            return

        # Ensure target layer exists
        if target_layer not in self.doc.layers:
            self.doc.layers.new(target_layer)

        # Get source entities
        layout = get_layout(self.doc)
        entities = layout.query(f'*[layer=="{source_layer}"]')

        # Copy entities to target layer
        for entity in entities:
            try:
                copy_entity(entity, layout, {'layer': target_layer})
            except Exception as e:
                log_warning(f"Error copying entity: {str(e)}")

    def _apply_transfer(self, transfer: Dict[str, Any]) -> None:
        """Apply a transfer operation.
        
        Args:
            transfer: Transfer operation configuration
        """
        source_layout = transfer.get('sourceLayout', 'Model')
        target_layout = transfer.get('targetLayout', 'Model')
        layers = transfer.get('layers', [])

        if not layers:
            log_warning("Transfer operation has no layers specified")
            return

        try:
            source = get_layout(self.doc, source_layout)
            target = get_layout(self.doc, target_layout)

            # Transfer entities from specified layers
            for layer in layers:
                entities = source.query(f'*[layer=="{layer}"]')
                for entity in entities:
                    copy_entity(entity, target)
        except Exception as e:
            log_error(f"Error applying transfer operation: {str(e)}")
            raise 