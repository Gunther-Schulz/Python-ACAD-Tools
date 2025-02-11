from typing import Dict, Any, List, Optional, Union, Tuple
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, MultiPolygon, MultiLineString
import ezdxf
from pathlib import Path

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error
from ..utils.geometry import (
    buffer_geometry, smooth_geometry, offset_geometry,
    simplify_geometry, transform_geometry
)

class LayerProcessor(BaseProcessor):
    """Processor for handling layer operations."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the layer processor.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self.processed_layers: Dict[str, gpd.GeoDataFrame] = {}
        self._initialize()

    def _initialize(self) -> None:
        """Initialize layer processor resources."""
        # Create output directory if specified
        if self.config.project_config.shapefile_output_dir:
            Path(self.config.project_config.shapefile_output_dir).mkdir(
                parents=True, exist_ok=True
            )

    def process_layers(self) -> None:
        """Process all configured layers."""
        if not self.validate_document():
            return

        for layer_config in self.config.project_config.geom_layers:
            try:
                self._process_layer(layer_config)
            except Exception as e:
                log_error(f"Error processing layer {layer_config.get('name', 'unknown')}: {str(e)}")
                raise

    def _process_layer(self, layer_config: Dict[str, Any]) -> None:
        """Process a single layer configuration.
        
        Args:
            layer_config: Layer configuration dictionary
        """
        layer_name = layer_config.get('name')
        if not layer_name:
            log_error("Layer configuration missing required 'name' field")
            return

        log_info(f"Processing layer: {layer_name}")

        # Load source data
        gdf = self._load_source_data(layer_config)
        if gdf is None or len(gdf) == 0:
            log_warning(f"No data loaded for layer {layer_name}")
            return

        # Apply operations
        if 'operations' in layer_config:
            gdf = self._apply_operations(gdf, layer_config['operations'])

        # Apply style
        if 'style' in layer_config:
            style = self.get_style(layer_config['style'])
            self._apply_layer_style(layer_name, style)

        # Store processed layer
        self.processed_layers[layer_name] = gdf

        # Export to shapefile if configured
        if 'outputShapeFile' in layer_config:
            output_path = self.resolve_path(layer_config['outputShapeFile'])
            gdf.to_file(output_path)
            log_info(f"Exported layer {layer_name} to {output_path}")

    def _load_source_data(self, layer_config: Dict[str, Any]) -> Optional[gpd.GeoDataFrame]:
        """Load source data for a layer.
        
        Args:
            layer_config: Layer configuration dictionary
            
        Returns:
            GeoDataFrame with source data or None if loading fails
        """
        if 'shapeFile' in layer_config:
            shapefile = self.resolve_path(layer_config['shapeFile'])
            try:
                return gpd.read_file(shapefile)
            except Exception as e:
                log_error(f"Error loading shapefile {shapefile}: {str(e)}")
                return None
        elif 'dxfLayer' in layer_config:
            return self._load_from_dxf(layer_config['dxfLayer'])
        else:
            log_warning(f"No source data specified for layer {layer_config.get('name')}")
            return None

    def _load_from_dxf(self, layer_name: str) -> gpd.GeoDataFrame:
        """Load geometries from a DXF layer.
        
        Args:
            layer_name: Name of the DXF layer
            
        Returns:
            GeoDataFrame with layer geometries
        """
        if not self.doc:
            raise ValueError("No DXF document set")

        geometries = []
        for entity in self.doc.modelspace().query(f'*[layer=="{layer_name}"]'):
            try:
                geom = self._entity_to_geometry(entity)
                if geom is not None:
                    geometries.append(geom)
            except Exception as e:
                log_warning(f"Error converting entity in layer {layer_name}: {str(e)}")

        return gpd.GeoDataFrame(geometry=geometries)

    def _entity_to_geometry(self, entity: ezdxf.entities.DXFGraphic) -> Optional[Union[Point, LineString, Polygon]]:
        """Convert a DXF entity to a Shapely geometry.
        
        Args:
            entity: DXF entity to convert
            
        Returns:
            Shapely geometry or None if conversion fails
        """
        dxftype = entity.dxftype()
        
        try:
            if dxftype == 'POINT':
                return Point(entity.dxf.location[:2])
            elif dxftype == 'LINE':
                return LineString([entity.dxf.start[:2], entity.dxf.end[:2]])
            elif dxftype == 'LWPOLYLINE':
                points = list(entity.get_points())
                if entity.closed:
                    points.append(points[0])
                return LineString(points) if len(points) >= 2 else None
            elif dxftype == 'POLYLINE':
                points = [vertex.dxf.location[:2] for vertex in entity.vertices]
                if entity.is_closed:
                    points.append(points[0])
                return LineString(points) if len(points) >= 2 else None
            elif dxftype == 'CIRCLE':
                center = Point(entity.dxf.center[:2])
                return center.buffer(entity.dxf.radius)
            else:
                log_debug(f"Unsupported entity type: {dxftype}")
                return None
        except Exception as e:
            log_warning(f"Error converting {dxftype} entity: {str(e)}")
            return None

    def _apply_operations(self, gdf: gpd.GeoDataFrame, 
                         operations: List[Dict[str, Any]]) -> gpd.GeoDataFrame:
        """Apply operations to a GeoDataFrame.
        
        Args:
            gdf: Input GeoDataFrame
            operations: List of operations to apply
            
        Returns:
            Processed GeoDataFrame
        """
        result = gdf.copy()
        
        for op in operations:
            op_type = op.get('type', '').lower()
            
            try:
                if op_type == 'buffer':
                    result = self._apply_buffer(result, op)
                elif op_type == 'smooth':
                    result = self._apply_smooth(result, op)
                elif op_type == 'simplify':
                    result = self._apply_simplify(result, op)
                elif op_type == 'offset':
                    result = self._apply_offset(result, op)
                elif op_type == 'transform':
                    result = self._apply_transform(result, op)
                elif op_type == 'filter':
                    result = self._apply_filter(result, op)
                else:
                    log_warning(f"Unknown operation type: {op_type}")
            except Exception as e:
                log_error(f"Error applying {op_type} operation: {str(e)}")
                raise
        
        return result

    def _apply_buffer(self, gdf: gpd.GeoDataFrame, op: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply buffer operation to geometries.
        
        Args:
            gdf: Input GeoDataFrame
            op: Buffer operation parameters
            
        Returns:
            GeoDataFrame with buffered geometries
        """
        distance = op.get('distance', 0.0)
        resolution = op.get('resolution', 16)
        cap_style = op.get('capStyle', 1)
        join_style = op.get('joinStyle', 1)
        mitre_limit = op.get('mitreLimit', 5.0)

        gdf.geometry = gdf.geometry.apply(lambda g: buffer_geometry(
            g, distance, resolution, cap_style, join_style, mitre_limit
        ))
        return gdf

    def _apply_smooth(self, gdf: gpd.GeoDataFrame, op: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply smoothing operation to geometries.
        
        Args:
            gdf: Input GeoDataFrame
            op: Smooth operation parameters
            
        Returns:
            GeoDataFrame with smoothed geometries
        """
        smoothing = op.get('smoothing', 0.5)
        preserve_topology = op.get('preserveTopology', True)

        gdf.geometry = gdf.geometry.apply(lambda g: smooth_geometry(
            g, smoothing, preserve_topology
        ))
        return gdf

    def _apply_simplify(self, gdf: gpd.GeoDataFrame, op: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply simplification operation to geometries.
        
        Args:
            gdf: Input GeoDataFrame
            op: Simplify operation parameters
            
        Returns:
            GeoDataFrame with simplified geometries
        """
        tolerance = op.get('tolerance', 0.1)
        preserve_topology = op.get('preserveTopology', True)

        gdf.geometry = gdf.geometry.apply(lambda g: simplify_geometry(
            g, tolerance, preserve_topology
        ))
        return gdf

    def _apply_offset(self, gdf: gpd.GeoDataFrame, op: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply offset operation to geometries.
        
        Args:
            gdf: Input GeoDataFrame
            op: Offset operation parameters
            
        Returns:
            GeoDataFrame with offset geometries
        """
        distance = op.get('distance', 0.0)
        side = op.get('side', 'both')
        resolution = op.get('resolution', 16)
        join_style = op.get('joinStyle', 1)
        mitre_limit = op.get('mitreLimit', 5.0)

        gdf.geometry = gdf.geometry.apply(lambda g: offset_geometry(
            g, distance, side, resolution, join_style, mitre_limit
        ))
        return gdf

    def _apply_transform(self, gdf: gpd.GeoDataFrame, op: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply transformation operation to geometries.
        
        Args:
            gdf: Input GeoDataFrame
            op: Transform operation parameters
            
        Returns:
            GeoDataFrame with transformed geometries
        """
        translation = (
            op.get('translate', {}).get('x', 0.0),
            op.get('translate', {}).get('y', 0.0)
        ) if 'translate' in op else None

        rotation = op.get('rotate', {}).get('angle') if 'rotate' in op else None

        scale_factors = (
            op.get('scale', {}).get('x', 1.0),
            op.get('scale', {}).get('y', 1.0)
        ) if 'scale' in op else None

        origin = op.get('origin', 'center')

        gdf.geometry = gdf.geometry.apply(lambda g: transform_geometry(
            g, translation, rotation, scale_factors, origin
        ))
        return gdf

    def _apply_filter(self, gdf: gpd.GeoDataFrame, op: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply filter operation to geometries.
        
        Args:
            gdf: Input GeoDataFrame
            op: Filter operation parameters
            
        Returns:
            Filtered GeoDataFrame
        """
        if 'expression' in op:
            try:
                return gdf.query(op['expression'])
            except Exception as e:
                log_error(f"Error applying filter expression: {str(e)}")
                return gdf
        return gdf

    def _apply_layer_style(self, layer_name: str, style: Dict[str, Any]) -> None:
        """Apply style properties to a DXF layer.
        
        Args:
            layer_name: Name of the layer
            style: Style properties to apply
        """
        self.apply_layer_properties(layer_name, style) 