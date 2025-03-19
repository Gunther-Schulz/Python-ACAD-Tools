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
    sanitize_layer_name, remove_entities_by_layer
)
from ...utils.logging import log_debug, log_warning, log_info, log_error
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN
import os


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
                # Update layer properties
                layer_props = style.get('layer', {})
                self.layer_properties[layer_name]['layer'].update(layer_props)

                # Update entity properties
                entity_props = style.get('entity', {})
                self.layer_properties[layer_name]['entity'].update(entity_props)

                # Ensure text style exists if specified
                if 'text' in style and 'font' in style['text']:
                    font_name = style['text']['font']
                    if font_name not in self.doc.styles:
                        self.doc.styles.add(font_name, font=font_name)

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
                log_info(f"Successfully loaded DXF file version: {self.doc.dxfversion}")
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
                log_info(f"Successfully loaded template DXF file version: {self.doc.dxfversion}")
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

        # Initialize document and register app ID
        self._initialize_document()
        self._register_app_id()

        return self.doc

    def _initialize_document(self) -> None:
        """Initialize the DXF document with required settings."""
        if not self.doc:
            return

        # Set up required styles with proper font
        if 'Standard' not in self.doc.styles:
            self.doc.styles.add('Standard', font='Arial')
        if 'Annotative' not in self.doc.styles:
            self.doc.styles.add('Annotative', font='Arial')

        # Set up required linetypes with patterns
        linetype_patterns = {
            'CONTINUOUS': '',  # Solid line
            'DASHED': 'A,.5,-.25',  # Standard dashed line
            'DOTTED': 'A,.25,-.25',  # Standard dotted line
            'DASHDOT': 'A,.5,-.25,.25,-.25',  # Dash-dot line
            'DASHDOT2': 'A,.5,-.25,.25,-.25,.25,-.25',  # Dash-dot-dot line
            'DIVIDE': 'A,.5,-.25,.25,-.25,.25,-.25,.25,-.25'  # Dash-dot-dot-dot line
        }

        for linetype, pattern in linetype_patterns.items():
            if linetype not in self.doc.linetypes:
                self.doc.linetypes.add(linetype, pattern=pattern)
                log_debug(f"Added linetype {linetype} with pattern: {pattern}")

        # Set up required layers
        if '0' not in self.doc.layers:
            self.doc.layers.add('0')

    def _register_app_id(self) -> None:
        """Register the application ID in the DXF document."""
        if not self.doc:
            return

        if self.script_identifier not in self.doc.appids:
            self.doc.appids.add(self.script_identifier)

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
            if doc is None:
                doc = self._load_or_create_dxf()

            # Process layers if not already processed
            if processed_layers is None:
                processed_layers = self.layer_processor.process_layers()

            # Get modelspace
            msp = doc.modelspace()

            # Add each processed layer to the DXF
            for layer_name, layer_data in processed_layers.items():
                try:
                    log_info(f"Adding layer to DXF: {layer_name}")
                    self._process_layer(layer_name, layer_data, msp)
                except Exception as e:
                    log_error(f"Error adding layer {layer_name} to DXF: {str(e)}")
                    raise ProcessingError(f"Error adding layer {layer_name} to DXF: {str(e)}")

            # Ensure output directory exists
            output_dir = os.path.dirname(self.dxf_filename)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Apply audit to check for and fix potential issues
            log_info("Running DXF audit...")
            try:
                audit = doc.audit()
                if audit.has_errors:
                    log_warning("DXF audit found errors:")
                    for error in audit.errors:
                        error_msg = f"  - {error.message}"
                        if hasattr(error, 'entity') and error.entity:
                            error_msg += f" (Entity: {error.entity.dxf.handle})"
                        log_warning(error_msg)
                else:
                    log_info("DXF audit found no errors")

                if audit.has_fixes:
                    log_info("DXF audit applied fixes:")
                    for fix in audit.fixes:
                        fix_msg = f"  - {fix.message}"
                        if hasattr(fix, 'entity') and fix.entity:
                            fix_msg += f" (Entity: {fix.entity.dxf.handle})"
                        log_info(fix_msg)
                else:
                    log_info("DXF audit applied no fixes")

            except Exception as e:
                log_warning(f"Error during DXF audit: {str(e)}")
                # Continue with save even if audit fails

            # Save the audited document
            try:
                # Ensure proper DXF version
                doc.dxfversion = self.project_settings.get('dxfVersion', 'R2010')

                # Save with proper encoding
                doc.saveas(self.dxf_filename, encoding='utf-8')
                log_info(f"Successfully saved DXF file to: {self.dxf_filename}")

                # Verify the saved file
                if Path(self.dxf_filename).exists():
                    file_size = Path(self.dxf_filename).stat().st_size
                    log_info(f"DXF file size: {file_size} bytes")
                else:
                    log_error("DXF file was not created")

            except Exception as e:
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
        Process a layer and its geometry.

        Args:
            layer_name: Name of the layer to process
            layer_data: Layer data from layer processor
            msp: Modelspace to add entities to
        """
        try:
            # Check update flag
            if not layer_data['config'].get('updateDxf', False):
                log_debug(f"Skipping layer {layer_name} - updateDxf is False")
                return

            # Remove existing entities if updateDxf is true
            log_debug(f"Removing existing entities from layer {layer_name}")
            remove_entities_by_layer(msp, [layer_name])

            # Process geometry if available
            if layer_name in self.layer_processor.layers:
                geometry = self.layer_processor.layers[layer_name]['geometry']
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
                log_debug(f"Processing polygon geometry for layer: {layer_name}")
                self._process_polygon(geometry, layer_name, msp)
            elif isinstance(geometry, (LineString, MultiLineString)):
                log_debug(f"Processing line geometry for layer: {layer_name}")
                self._process_line(geometry, layer_name, msp)
            elif isinstance(geometry, Point):
                log_debug(f"Processing point geometry for layer: {layer_name}")
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
            log_warning(f"Empty coordinates for layer {layer_name}")
            return

        # Validate coordinates
        if len(coords) < 2:
            log_warning(f"Not enough coordinates for layer {layer_name}: {len(coords)}")
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

        try:
            # Create polyline
            polyline = msp.add_lwpolyline(coords, dxfattribs=dxfattribs)

            # Apply linetype generation setting
            if entity_properties.get('linetypeGeneration'):
                polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
            else:
                polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN

            # Attach custom data with proper cleanup
            try:
                # Clear any existing XDATA first
                polyline.discard_xdata(self.script_identifier)
            except:
                pass

            # Set new XDATA with proper format
            polyline.set_xdata(
                self.script_identifier,
                [(1000, self.script_identifier)]
            )

            # Ensure entity is properly added to the document database
            if hasattr(polyline, 'doc') and polyline.doc:
                polyline.doc.entitydb.add(polyline)

            # Set hyperlink
            hyperlink_text = f"{self.script_identifier}_{layer_name}"
            polyline.set_hyperlink(hyperlink_text)

            log_debug(f"Added polyline to layer {layer_name} with {len(coords)} points")
        except Exception as e:
            log_error(f"Error adding polyline to layer {layer_name}: {str(e)}")
            raise ProcessingError(f"Error adding polyline to layer {layer_name}: {str(e)}")

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
        try:
            if isinstance(geometry, MultiPolygon):
                for polygon in geometry.geoms:
                    self._process_polygon(polygon, layer_name, msp)
            else:
                # Process exterior
                exterior_coords = list(geometry.exterior.coords)
                if len(exterior_coords) > 2:
                    log_debug(f"Processing exterior with {len(exterior_coords)} points")
                    self._add_polyline(exterior_coords, layer_name, msp, close=True)

                # Process interiors
                for interior in geometry.interiors:
                    interior_coords = list(interior.coords)
                    if len(interior_coords) > 2:
                        log_debug(f"Processing interior with {len(interior_coords)} points")
                        self._add_polyline(interior_coords, layer_name, msp, close=True)
        except Exception as e:
            log_error(f"Error processing polygon for layer {layer_name}: {str(e)}")
            raise ProcessingError(f"Error processing polygon for layer {layer_name}: {str(e)}")

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
        try:
            if isinstance(geometry, MultiLineString):
                for line in geometry.geoms:
                    self._process_line(line, layer_name, msp)
            else:
                coords = list(geometry.coords)
                if len(coords) > 1:
                    log_debug(f"Processing line with {len(coords)} points")
                    self._add_polyline(coords, layer_name, msp)
                else:
                    log_warning(f"Line with insufficient points for layer {layer_name}")
        except Exception as e:
            log_error(f"Error processing line for layer {layer_name}: {str(e)}")
            raise ProcessingError(f"Error processing line for layer {layer_name}: {str(e)}")

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
        try:
            if not geometry.coords:
                log_warning(f"Empty point coordinates for layer {layer_name}")
                return

            point = msp.add_point(geometry.coords[0])
            point.dxf.layer = layer_name

            # Attach custom data with proper cleanup
            try:
                # Clear any existing XDATA first
                point.discard_xdata(self.script_identifier)
            except:
                pass

            # Set new XDATA with proper format
            point.set_xdata(
                self.script_identifier,
                [(1000, self.script_identifier)]
            )

            # Ensure entity is properly added to the document database
            if hasattr(point, 'doc') and point.doc:
                point.doc.entitydb.add(point)

            # Set hyperlink
            hyperlink_text = f"{self.script_identifier}_{layer_name}"
            point.set_hyperlink(hyperlink_text)

            log_debug(f"Added point to layer {layer_name}")
        except Exception as e:
            log_error(f"Error processing point for layer {layer_name}: {str(e)}")
            raise ProcessingError(f"Error processing point for layer {layer_name}: {str(e)}")
