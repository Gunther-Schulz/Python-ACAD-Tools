"""
DXF exporter for handling DXF file operations.
"""
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import ezdxf
import traceback
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point
from ...core.exceptions import ProcessingError
from ...core.project import Project
from ...processing import LayerProcessor
from ...style import StyleManager
from ...utils.path import resolve_path, ensure_path_exists
from .utils import (
    attach_custom_data, ensure_layer_exists,
    update_layer_properties, set_drawing_properties,
    sanitize_layer_name
)
from ...utils.logging import log_debug, log_warning, log_info, log_error
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN


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
        self.template_doc = None
        self.layer_properties = {}
        self.colors = {}

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

        # Initialize layer properties
        self._initialize_layer_properties()

    def _initialize_layer_properties(self) -> None:
        """Initialize layer properties from project settings."""
        # Process all layer types
        layer_types = ['geomLayers', 'wmtsLayers', 'wmsLayers']
        for layer_type in layer_types:
            for layer in self.project_settings.get(layer_type, []):
                self._setup_single_layer(layer)

    def _setup_single_layer(self, layer: Dict[str, Any]) -> None:
        """Setup properties for a single layer."""
        layer_name = sanitize_layer_name(layer['name'])

        # Skip if already initialized
        if layer_name in self.layer_properties:
            return

        # Initialize with default properties
        default_properties = {
            'layer': {
                'color': 'White',
                'linetype': 'CONTINUOUS',
                'lineweight': 0.13,
                'plot': True,
                'locked': False,
                'frozen': False,
                'is_on': True
            },
            'entity': {
                'close': False
            }
        }
        self.layer_properties[layer_name] = default_properties
        self.colors[layer_name] = default_properties['layer']['color']

        # Process layer style if it exists
        if 'style' in layer:
            style, warning = self.style_manager.get_style(layer['style'])
            if style:
                self.layer_properties[layer_name]['layer'].update(style.get('layer', {}))
                self.layer_properties[layer_name]['entity'].update(style.get('entity', {}))

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
            log_info(f"Loading existing DXF file: {self.dxf_filename}")
            try:
                self.doc = ezdxf.readfile(self.dxf_filename)
                self._load_existing_layers()
                set_drawing_properties(self.doc)
            except Exception as e:
                log_error(f"Error loading existing DXF file: {str(e)}")
                # If loading fails, create new document
                log_info("Creating new DXF file due to loading error")
                self.doc = ezdxf.new(dxfversion=dxf_version)
                set_drawing_properties(self.doc)
        elif self.template_filename and Path(self.template_filename).exists():
            # Use template if available
            log_info(f"Using template DXF file: {self.template_filename}")
            try:
                self.doc = ezdxf.readfile(self.template_filename)
                set_drawing_properties(self.doc)
            except Exception as e:
                log_error(f"Error loading template DXF file: {str(e)}")
                # If loading fails, create new document
                log_info("Creating new DXF file due to template loading error")
                self.doc = ezdxf.new(dxfversion=dxf_version)
                set_drawing_properties(self.doc)
        else:
            # Create new document
            if self.template_filename:
                log_warning(f"Template file not found at: {self.template_filename}")
            log_info(f"Creating new DXF file with version: {dxf_version}")
            self.doc = ezdxf.new(dxfversion=dxf_version)
            set_drawing_properties(self.doc)

        return self.doc

    def _load_existing_layers(self) -> None:
        """Load existing layers from DXF file."""
        # Only load layers that aren't already in the layer processor
        for layer in self.doc.layers:
            layer_name = layer.dxf.name
            if layer_name not in self.layer_processor.layers:
                self.layer_processor.layers[layer_name] = {
                    'config': {},
                    'geometry': None,
                    'style': None
                }
                # Also initialize layer properties if needed
                if layer_name not in self.layer_properties:
                    self._setup_single_layer({'name': layer_name})

    def export_to_dxf(
        self,
        skip_dxf_processor: bool = False,
        doc: Optional[Drawing] = None,
        processed_layers: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Export to DXF format.

        Args:
            skip_dxf_processor: Whether to skip DXF processor operations
            doc: Optional DXF document to use instead of loading/creating a new one
            processed_layers: Optional dictionary of already processed layers
        """
        try:
            # Use provided document or load/create new one
            if doc is not None:
                self.doc = doc
            else:
                self.doc = self._load_or_create_dxf(skip_dxf_processor)

            # Process layers
            msp = self.doc.modelspace()

            # Use provided processed layers or process them again
            layers_to_process = processed_layers if processed_layers is not None else self.layer_processor.layers

            for layer_name, layer_data in layers_to_process.items():
                self._process_layer(layer_name, layer_data, msp)

            # Ensure output directory exists
            output_dir = str(Path(self.dxf_filename).parent)
            ensure_path_exists(output_dir)

            # Audit and save document with error handling
            try:
                # Run audit to check and fix potential issues
                auditor = self.doc.audit()
                if auditor.has_errors:
                    log_warning("DXF audit found and fixed issues:")
                    for error in auditor.errors:
                        log_warning(f"  - {error.message}")
                        if error.entity:
                            log_warning(f"    Entity: {error.entity.dxf.handle}")
                        if error.details:
                            log_warning(f"    Details: {error.details}")
                if auditor.has_fixes:
                    log_info("DXF audit applied fixes:")
                    for fix in auditor.fixes:
                        log_info(f"  - {fix.message}")
                        if fix.entity:
                            log_info(f"    Entity: {fix.entity.dxf.handle}")
                        if fix.details:
                            log_info(f"    Details: {fix.details}")

                # Save the audited document
                self.doc.saveas(self.dxf_filename)
                log_info(f"Successfully saved DXF file to: {self.dxf_filename}")
            except Exception as e:
                log_error(f"Error saving DXF file: {str(e)}")
                raise ProcessingError(f"Error saving DXF file: {str(e)}")

        except Exception as e:
            log_error(f"Error exporting to DXF: {str(e)}")
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
            # Get layer properties
            layer_properties = self.layer_properties.get(layer_name, {})
            layer_config = layer_properties.get('layer', {})

            # Ensure layer exists
            layer = ensure_layer_exists(self.doc, layer_name)

            # Update layer properties
            if layer_config:
                update_layer_properties(layer, layer_config)

            # Process geometry
            geometry = layer_data.get('geometry')
            if geometry:
                self._process_geometry(geometry, layer_name, msp)

        except Exception as e:
            log_error(f"Error processing layer {layer_name}: {str(e)}")
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
            log_error(f"Error processing geometry: {str(e)}")
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
        if not coords:
            return

        # Get layer properties
        layer_properties = self.layer_properties.get(layer_name, {})
        entity_properties = layer_properties.get('entity', {})

        # Prepare dxfattribs
        dxfattribs = {
            'layer': layer_name,
            'closed': entity_properties.get('close', close)
        }

        # Add any other entity-level properties
        if 'linetypeScale' in entity_properties:
            dxfattribs['ltscale'] = entity_properties['linetypeScale']
        if 'linetypeGeneration' in entity_properties:
            dxfattribs['flags'] = entity_properties['linetypeGeneration']

        # Create polyline
        polyline = msp.add_lwpolyline(coords, dxfattribs=dxfattribs)

        # Apply linetype generation setting
        if entity_properties.get('linetypeGeneration'):
            polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
        else:
            polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

        # Attach custom data
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
            # Process exterior
            exterior_coords = list(geometry.exterior.coords)
            if len(exterior_coords) > 2:
                self._add_polyline(exterior_coords, layer_name, msp, close=True)

            # Process interiors
            for interior in geometry.interiors:
                interior_coords = list(interior.coords)
                if len(interior_coords) > 2:
                    self._add_polyline(interior_coords, layer_name, msp, close=True)

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
