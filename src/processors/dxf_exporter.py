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
from .dxf.dxf import (
    create_document, load_document, save_document,
    cleanup_document, get_layout, copy_entity
)
from .dxf.text import add_labels_from_gdf

class DXFExporter(BaseProcessor):
    """Processor for exporting geometries to DXF format."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the DXF exporter.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self.doc: Optional[Drawing] = None

    def export_to_dxf(self, processed_layers: Dict[str, gpd.GeoDataFrame]) -> None:
        """Export processed layers to DXF and apply operations.
        
        Args:
            processed_layers: Dictionary of layer name to GeoDataFrame
        """
        if not self.doc:
            log_error("No document set for export. Call set_dxf_document() first.")
            return
            
        try:
            log_info("Starting DXF export...")
            
            # Phase 1: Setup and validation
            log_debug("Setting up layers...")
            self._setup_layers(processed_layers)
            
            # Get target layout
            layout = get_layout(self.doc)
            log_debug("Using model space layout")
            
            # Phase 2: Export geometries and labels
            log_debug("Exporting geometries and labels to layers...")
            for layer_name, gdf in processed_layers.items():
                if not gdf.empty:
                    try:
                        # Export geometries
                        self._export_layer(layer_name, gdf, layout)
                        log_debug(f"Successfully exported geometries for layer: {layer_name}")
                        
                        # Add labels if configured
                        layer_config = self._get_layer_config(layer_name)
                        if layer_config and 'label' in layer_config:
                            label_layer = f"{layer_name}_Labels"
                            self._setup_label_layer(label_layer)
                            
                            # Get text style from layer config
                            text_style = self._get_text_style(layer_config)
                            
                            # Add labels
                            add_labels_from_gdf(
                                layout=layout,
                                gdf=gdf,
                                label_column=layer_config['label'],
                                layer=label_layer,
                                **text_style
                            )
                            log_debug(f"Added labels for layer: {layer_name}")
                            
                    except Exception as e:
                        log_error(f"Failed to export layer {layer_name}: {str(e)}")
                        raise
            
            # Phase 3: Apply DXF operations
            if self.config.project_config.dxf_operations:
                log_info("Applying DXF operations...")
                try:
                    self._apply_dxf_operations()
                    log_debug("DXF operations completed successfully")
                except Exception as e:
                    log_error(f"Failed to apply DXF operations: {str(e)}")
                    raise
            
            log_info("DXF export completed successfully")
            
        except Exception as e:
            log_error(f"Error during DXF export: {str(e)}")
            raise

    def _setup_layers(self, processed_layers: Dict[str, gpd.GeoDataFrame]) -> None:
        """Setup DXF layers with proper properties.
        
        Args:
            processed_layers: Dictionary of layer name to GeoDataFrame
        """
        for layer_name in processed_layers.keys():
            try:
                # Get layer config from project settings
                layer_config = next(
                    (l for l in self.config.project_config.geom_layers if l['name'] == layer_name),
                    None
                )
                
                if not layer_config:
                    log_warning(f"No configuration found for layer: {layer_name}")
                    continue
                
                # Create layer if it doesn't exist
                if layer_name not in self.doc.layers:
                    self.doc.layers.new(layer_name)
                    log_debug(f"Created new layer: {layer_name}")
                
                # Apply layer properties from style
                if 'style' in layer_config:
                    layer = self.doc.layers.get(layer_name)
                    style = self.get_style(layer_config['style'])
                    
                    # Apply basic properties
                    if 'color' in style:
                        layer.color = self.get_color_code(style['color'])
                    if 'linetype' in style:
                        layer.linetype = style['linetype']
                    if 'lineweight' in style:
                        layer.lineweight = style['lineweight']
                    
                    # Apply status properties
                    layer.plot = style.get('plot', True)
                    layer.locked = style.get('locked', False)
                    layer.frozen = style.get('frozen', False)
                    layer.off = not style.get('is_on', True)
                    
                    # Apply transparency if specified
                    if 'transparency' in style:
                        try:
                            transparency = float(style['transparency'])
                            if 0 <= transparency <= 1:
                                layer.transparency = int(transparency * 100)
                        except (ValueError, TypeError):
                            log_warning(f"Invalid transparency value for layer {layer_name}")
                    
                    log_debug(f"Applied style properties to layer: {layer_name}")
                
            except Exception as e:
                log_error(f"Error setting up layer {layer_name}: {str(e)}")
                raise

    def _export_layer(self, layer_name: str, gdf: gpd.GeoDataFrame, layout: Layout) -> None:
        """Export a GeoDataFrame to a DXF layer.
        
        Args:
            layer_name: Name of the layer
            gdf: GeoDataFrame to export
            layout: Target layout
        """
        log_debug(f"Exporting geometries to layer: {layer_name}")
        
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

    def _setup_label_layer(self, layer_name: str) -> None:
        """Setup a layer for labels with appropriate properties.
        
        Args:
            layer_name: Name of the label layer
        """
        if layer_name not in self.doc.layers:
            self.doc.layers.new(layer_name)
            log_debug(f"Created new label layer: {layer_name}")
            
        # Set default properties for label layer
        layer = self.doc.layers.get(layer_name)
        layer.color = 7  # White
        layer.linetype = "Continuous"
        layer.lineweight = -3  # Default
        layer.plot = True

    def _get_layer_config(self, layer_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a layer from project settings.
        
        Args:
            layer_name: Name of the layer
            
        Returns:
            Layer configuration dictionary or None if not found
        """
        return next(
            (l for l in self.config.project_config.geom_layers if l['name'] == layer_name),
            None
        )

    def _get_text_style(self, layer_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get text style properties from layer configuration.
        
        Args:
            layer_config: Layer configuration dictionary
            
        Returns:
            Dictionary of text style properties
        """
        style = {}
        
        # Get style from layer config
        if 'style' in layer_config:
            layer_style = self.get_style(layer_config['style'])
            if layer_style:
                # Text height
                if 'text_height' in layer_style:
                    style['text_height'] = layer_style['text_height']
                
                # Text style name
                if 'text_style' in layer_style:
                    style['text_style'] = layer_style['text_style']
                
                # Additional text properties
                if 'text_color' in layer_style:
                    style['color'] = layer_style['text_color']
                if 'text_rotation' in layer_style:
                    style['rotation'] = layer_style['text_rotation']
                if 'text_alignment' in layer_style:
                    style['alignment'] = layer_style['text_alignment']
        
        return style 