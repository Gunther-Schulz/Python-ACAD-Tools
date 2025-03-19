"""
DXF exporter for handling DXF file operations.
"""
from typing import Dict, Any, List, Tuple
from pathlib import Path
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ...core.exceptions import ProcessingError
from ...core.project import Project
from ...processing import LayerProcessor
from ...style import StyleManager
from ...utils.path import resolve_path, ensure_path_exists
from .utils import (
    attach_custom_data, ensure_layer_exists,
    update_layer_properties, set_drawing_properties
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
        self.script_identifier = "PyCAD"
        self.loaded_styles = set()

        # Get project settings
        self.project_settings = project.settings
        self.folder_prefix = project.folder_prefix

        # Resolve paths with folder prefix
        self.dxf_filename = resolve_path(
            self.project_settings['dxfFilename'],
            self.folder_prefix
        )
        self.template_filename = resolve_path(
            self.project_settings.get('templateDxfFilename', ''),
            self.folder_prefix
        )

    def _load_or_create_dxf(self, skip_dxf_processor: bool = False) -> Drawing:
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

            # Ensure output directory exists
            output_dir = str(Path(self.dxf_filename).parent)
            ensure_path_exists(output_dir)

            # Save document
            self.doc.saveas(self.dxf_filename)

        except Exception as e:
            raise ProcessingError(f"Error exporting to DXF: {str(e)}")

    def _process_layer(
        self,
        layer_name: str,
        layer_data: Dict[str, Any],
        msp: Modelspace
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
            layer = ensure_layer_exists(self.doc, layer_name)

            # Get layer properties
            layer_properties = layer_data.get('config', {})
            style = layer_data.get('style')

            # Update layer properties
            if layer_properties or style:
                update_layer_properties(layer, layer_properties)

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
        msp: Modelspace
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
                raise ProcessingError(
                    f"Unsupported geometry type: {type(geometry)}"
                )

        except Exception as e:
            raise ProcessingError(f"Error processing geometry: {str(e)}")

    def _add_polyline(
        self,
        coords: List[Tuple[float, float]],
        layer_name: str,
        msp: Modelspace,
        close: bool = False
    ) -> None:
        """
        Add a polyline to the modelspace.

        Args:
            coords: List of coordinate tuples
            layer_name: Name of the layer
            msp: Modelspace to add entities to
            close: Whether to close the polyline
        """
        if coords:
            polyline = msp.add_lwpolyline(coords)
            polyline.dxf.layer = layer_name
            if close:
                polyline.close(True)
            attach_custom_data(polyline, {'created_by': self.script_identifier})

    def _process_polygon(
        self,
        geometry: object,
        layer_name: str,
        msp: Modelspace
    ) -> None:
        """
        Process a polygon geometry.

        Args:
            geometry: Polygon geometry to process
            layer_name: Name of the layer
            msp: Modelspace to add entities to
        """
        if isinstance(geometry, MultiPolygon):
            for polygon in geometry.geoms:
                self._process_polygon(polygon, layer_name, msp)
        else:
            coords = list(geometry.exterior.coords)
            self._add_polyline(coords, layer_name, msp, close=True)

    def _process_line(
        self,
        geometry: object,
        layer_name: str,
        msp: Modelspace
    ) -> None:
        """
        Process a line geometry.

        Args:
            geometry: Line geometry to process
            layer_name: Name of the layer
            msp: Modelspace to add entities to
        """
        if isinstance(geometry, MultiLineString):
            for line in geometry.geoms:
                self._process_line(line, layer_name, msp)
        else:
            coords = list(geometry.coords)
            self._add_polyline(coords, layer_name, msp)

    def _process_point(
        self,
        geometry: object,
        layer_name: str,
        msp: Modelspace
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
