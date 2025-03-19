"""
DXF exporter for handling DXF file operations.
"""
from typing import Dict, Any, Optional
from pathlib import Path
import ezdxf
from ...core.exceptions import ProcessingError
from ...core.project import Project
from ...processing import LayerProcessor
from ...style import StyleManager
from .utils import (
    get_color_code, attach_custom_data, is_created_by_script,
    add_text, add_mtext, remove_entities_by_layer, ensure_layer_exists,
    update_layer_properties, set_drawing_properties, verify_dxf_settings,
    sanitize_layer_name
)


class DXFExporter:
    """Handles DXF file operations and exports."""

    def __init__(
        self,
        project: Project,
        layer_processor: LayerProcessor,
        style_manager: StyleManager
    ):
        """
        Initialize the DXF exporter.

        Args:
            project: Project instance
            layer_processor: Layer processor instance
            style_manager: Style manager instance
        """
        self.project = project
        self.layer_processor = layer_processor
        self.style_manager = style_manager
        self.doc = None
        self.script_identifier = "OLADPP"
        self.loaded_styles = set()

        # Get project settings
        self.project_settings = project.settings
        self.folder_prefix = project.folder_prefix

        # Resolve paths with folder prefix
        self.dxf_filename = self._resolve_path(self.project_settings['dxfFilename'])
        self.template_filename = self._resolve_path(
            self.project_settings.get('templateDxfFilename', '')
        )

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a path using the folder prefix.

        Args:
            path: Path to resolve

        Returns:
            Resolved path
        """
        if not path:
            return path
        if Path(path).is_absolute():
            return path
        return str(Path(self.folder_prefix) / path)

    def _load_or_create_dxf(self, skip_dxf_processor: bool = False) -> ezdxf.Document:
        """
        Load or create a DXF document.

        Args:
            skip_dxf_processor: Whether to skip DXF processor operations

        Returns:
            DXF document
        """
        dxf_version = self.project_settings.get('dxfVersion', 'R2010')

        # Load or create the DXF document
        if Path(self.dxf_filename).exists():
            self.doc = ezdxf.readfile(self.dxf_filename)
            self._load_existing_layers()
            set_drawing_properties(self.doc)
        elif self.template_filename and Path(self.template_filename).exists():
            # Use template if available
            self.doc = ezdxf.readfile(self.template_filename)
            set_drawing_properties(self.doc)
        else:
            # Create new document
            self.doc = ezdxf.new(dxfversion=dxf_version)
            set_drawing_properties(self.doc)

        return self.doc

    def _load_existing_layers(self) -> None:
        """Load existing layers from DXF file."""
        for layer in self.doc.layers:
            layer_name = layer.dxf.name
            if layer_name not in self.layer_processor.layers:
                self.layer_processor.layers[layer_name] = {
                    'config': {},
                    'geometry': None,
                    'style': None
                }

    def export_to_dxf(self, skip_dxf_processor: bool = False) -> None:
        """
        Export to DXF format.

        Args:
            skip_dxf_processor: Whether to skip DXF processor operations
        """
        try:
            # Load or create DXF document
            self.doc = self._load_or_create_dxf(skip_dxf_processor)

            # Process layers
            msp = self.doc.modelspace()
            for layer_name, layer_data in self.layer_processor.layers.items():
                self._process_layer(layer_name, layer_data, msp)

            # Save document
            self.doc.saveas(self.dxf_filename)

        except Exception as e:
            raise ProcessingError(f"Error exporting to DXF: {str(e)}")

    def _process_layer(
        self,
        layer_name: str,
        layer_data: Dict[str, Any],
        msp: ezdxf.Modelspace
    ) -> None:
        """
        Process a layer.

        Args:
            layer_name: Name of the layer
            layer_data: Layer data
            msp: Modelspace to add entities to
        """
        try:
            # Ensure layer exists
            ensure_layer_exists(self.doc, layer_name)

            # Get layer properties
            layer_properties = layer_data.get('config', {})
            style = layer_data.get('style')

            # Update layer properties
            if layer_properties or style:
                update_layer_properties(
                    self.doc,
                    layer_name,
                    layer_properties,
                    style
                )

            # Process geometry
            geometry = layer_data.get('geometry')
            if geometry:
                self._process_geometry(geometry, layer_name, msp)

        except Exception as e:
            raise ProcessingError(f"Error processing layer {layer_name}: {str(e)}")

    def _process_geometry(
        self,
        geometry: object,
        layer_name: str,
        msp: ezdxf.Modelspace
    ) -> None:
        """
        Process a geometry.

        Args:
            geometry: Geometry to process
            layer_name: Name of the layer
            msp: Modelspace to add entities to
        """
        try:
            from shapely.geometry import (
                Polygon, MultiPolygon, LineString, MultiLineString, Point
            )

            if isinstance(geometry, (Polygon, MultiPolygon)):
                self._process_polygon(geometry, layer_name, msp)
            elif isinstance(geometry, (LineString, MultiLineString)):
                self._process_line(geometry, layer_name, msp)
            elif isinstance(geometry, Point):
                self._process_point(geometry, layer_name, msp)
            else:
                raise ProcessingError(f"Unsupported geometry type: {type(geometry)}")

        except Exception as e:
            raise ProcessingError(f"Error processing geometry: {str(e)}")

    def _process_polygon(
        self,
        geometry: object,
        layer_name: str,
        msp: ezdxf.Modelspace
    ) -> None:
        """
        Process a polygon geometry.

        Args:
            geometry: Polygon geometry to process
            layer_name: Name of the layer
            msp: Modelspace to add entities to
        """
        from shapely.geometry import Polygon, MultiPolygon

        if isinstance(geometry, MultiPolygon):
            for polygon in geometry.geoms:
                self._process_polygon(polygon, layer_name, msp)
        else:
            coords = list(geometry.exterior.coords)
            if coords:
                polyline = msp.add_lwpolyline(coords)
                polyline.dxf.layer = layer_name
                polyline.close(True)
                attach_custom_data(polyline, {'created_by': self.script_identifier})

    def _process_line(
        self,
        geometry: object,
        layer_name: str,
        msp: ezdxf.Modelspace
    ) -> None:
        """
        Process a line geometry.

        Args:
            geometry: Line geometry to process
            layer_name: Name of the layer
            msp: Modelspace to add entities to
        """
        from shapely.geometry import LineString, MultiLineString

        if isinstance(geometry, MultiLineString):
            for line in geometry.geoms:
                self._process_line(line, layer_name, msp)
        else:
            coords = list(geometry.coords)
            if coords:
                polyline = msp.add_lwpolyline(coords)
                polyline.dxf.layer = layer_name
                attach_custom_data(polyline, {'created_by': self.script_identifier})

    def _process_point(
        self,
        geometry: object,
        layer_name: str,
        msp: ezdxf.Modelspace
    ) -> None:
        """
        Process a point geometry.

        Args:
            geometry: Point geometry to process
            layer_name: Name of the layer
            msp: Modelspace to add entities to
        """
        point = msp.add_point(geometry.coords[0])
        point.dxf.layer = layer_name
        attach_custom_data(point, {'created_by': self.script_identifier})
