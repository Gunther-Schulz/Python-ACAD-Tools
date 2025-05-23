"""Adapter for ezdxf library integration."""
from typing import Optional, Any, Dict
import os
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

from ..interfaces.dxf_adapter_interface import IDXFAdapter
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import DXFProcessingError

try:
    import ezdxf
    from ezdxf.document import Drawing
    EZDXF_AVAILABLE = True
except ImportError:
    ezdxf = None
    Drawing = type(None)
    EZDXF_AVAILABLE = False


class EzdxfAdapter(IDXFAdapter):
    """Adapter for ezdxf library operations."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize adapter with injected logger service."""
        self._logger = logger_service.get_logger(__name__)

    def is_available(self) -> bool:
        """Check if ezdxf library is available."""
        return EZDXF_AVAILABLE

    def load_dxf_file(self, file_path: str) -> Optional[Drawing]:
        """Load a DXF file using ezdxf."""
        if not self.is_available():
            raise DXFProcessingError("ezdxf library not available")

        if not os.path.exists(file_path):
            raise DXFProcessingError(f"DXF file not found: {file_path}")

        try:
            self._logger.debug(f"Loading DXF file: {file_path}")
            doc = ezdxf.readfile(file_path)
            self._logger.info(f"Successfully loaded DXF file: {file_path}")
            return doc
        except Exception as e:
            error_msg = f"Failed to load DXF file {file_path}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def extract_entities_from_layer(
        self,
        dxf_document: Drawing,
        layer_name: str,
        crs: str
    ) -> Optional[gpd.GeoDataFrame]:
        """Extract entities from a specific DXF layer."""
        if not self.is_available():
            raise DXFProcessingError("ezdxf library not available")

        try:
            msp = dxf_document.modelspace()
            entities = []

            # Query entities from the specified layer
            for entity in msp.query(f'*[layer=="{layer_name}"]'):
                entity_data = self._extract_entity_data(entity)
                if entity_data:
                    entities.append(entity_data)

            if not entities:
                self._logger.warning(f"No entities found in layer: {layer_name}")
                return None

            # Create GeoDataFrame
            gdf = gpd.GeoDataFrame(entities, crs=crs)
            self._logger.info(f"Extracted {len(entities)} entities from layer: {layer_name}")
            return gdf

        except Exception as e:
            error_msg = f"Failed to extract entities from layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def save_dxf_file(self, dxf_document: Drawing, file_path: str) -> None:
        """Save a DXF document to file."""
        if not self.is_available():
            raise DXFProcessingError("ezdxf library not available")

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            self._logger.debug(f"Saving DXF file: {file_path}")
            dxf_document.saveas(file_path)
            self._logger.info(f"Successfully saved DXF file: {file_path}")

        except Exception as e:
            error_msg = f"Failed to save DXF file {file_path}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def create_dxf_layer(self, dxf_document: Drawing, layer_name: str, **properties) -> None:
        """Create or update a DXF layer with specified properties."""
        if not self.is_available():
            raise DXFProcessingError("ezdxf library not available")

        try:
            layers = dxf_document.layers

            if layer_name not in layers:
                layer = layers.add(layer_name)
                self._logger.debug(f"Created new DXF layer: {layer_name}")
            else:
                layer = layers.get(layer_name)
                self._logger.debug(f"Updated existing DXF layer: {layer_name}")

            # Apply properties
            if 'color' in properties:
                layer.color = properties['color']
            if 'linetype' in properties:
                layer.linetype = properties['linetype']
            if 'lineweight' in properties:
                layer.lineweight = properties['lineweight']

        except Exception as e:
            error_msg = f"Failed to create/update DXF layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def add_geodataframe_to_dxf(
        self,
        dxf_document: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        **style_properties
    ) -> None:
        """Add geometries from GeoDataFrame to DXF document."""
        if not self.is_available():
            raise DXFProcessingError("ezdxf library not available")

        try:
            msp = dxf_document.modelspace()

            for idx, row in gdf.iterrows():
                geometry = row.geometry
                attributes = {'layer': layer_name}
                attributes.update(style_properties)

                if geometry.geom_type == 'Point':
                    msp.add_point((geometry.x, geometry.y), dxfattribs=attributes)
                elif geometry.geom_type == 'LineString':
                    points = [(x, y) for x, y in geometry.coords]
                    msp.add_lwpolyline(points, dxfattribs=attributes)
                elif geometry.geom_type == 'Polygon':
                    points = [(x, y) for x, y in geometry.exterior.coords]
                    msp.add_lwpolyline(points, close=True, dxfattribs=attributes)

            self._logger.info(f"Added {len(gdf)} geometries to DXF layer: {layer_name}")

        except Exception as e:
            error_msg = f"Failed to add geometries to DXF layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def _extract_entity_data(self, entity) -> Optional[Dict]:
        """Extract data from a DXF entity."""
        try:
            entity_type = entity.dxftype()

            if entity_type == 'POINT':
                geometry = Point(entity.dxf.location.x, entity.dxf.location.y)
            elif entity_type == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                geometry = LineString([(start.x, start.y), (end.x, end.y)])
            elif entity_type == 'LWPOLYLINE':
                points = [(p[0], p[1]) for p in entity.get_points()]
                if entity.closed:
                    geometry = Polygon(points)
                else:
                    geometry = LineString(points)
            else:
                # Skip unsupported entity types
                return None

            return {
                'geometry': geometry,
                'entity_type': entity_type,
                'layer': entity.dxf.layer,
                'color': getattr(entity.dxf, 'color', None),
                'linetype': getattr(entity.dxf, 'linetype', None)
            }

        except Exception as e:
            self._logger.warning(f"Failed to extract data from entity {entity}: {e}")
            return None
