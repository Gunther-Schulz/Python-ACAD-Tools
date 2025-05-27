"""Adapter for ezdxf library integration."""
from typing import Optional, Any, Dict, List, Tuple
import os
# import geopandas as gpd # Only if extract_entities_from_layer returns GeoDataFrame
# from shapely.geometry import Point, LineString, Polygon # Only if _extract_entity_data is used and returns Shapely

from ..interfaces.dxf_adapter_interface import IDXFAdapter
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import DXFProcessingError, DXFLibraryNotInstalledError

try:
    import ezdxf
    from ezdxf import DXFValueError, DXFStructureError
    from ezdxf.document import Drawing
    from ezdxf.layouts import Modelspace
    from ezdxf.entities.ltype import Linetype
    from ezdxf.entities.textstyle import Textstyle as TextStyle
    from ezdxf.entities.layer import Layer
    from ezdxf.entities import Text, MText, Point as DXFPoint, Line as DXFLine, LWPolyline, Hatch
    from ezdxf.enums import MTextEntityAlignment # For MTEXT
    from ezdxf import const as ezdxf_const # For hatch flags and other constants
    EZDXF_AVAILABLE = True
except ImportError:
    ezdxf = None
    DXFValueError = Exception # type: ignore
    DXFStructureError = Exception # type: ignore
    Drawing = Any # type: ignore
    Modelspace = Any # type: ignore
    Linetype = Any # type: ignore
    TextStyle = Any # type: ignore
    Layer = Any # type: ignore
    Text, MText, DXFPoint, DXFLine, LWPolyline, Hatch = type(None), type(None), type(None), type(None), type(None), type(None) # type: ignore
    MTextEntityAlignment = type(None) # type: ignore
    ezdxf_const = None # type: ignore
    EZDXF_AVAILABLE = False

# Add GEOPANDAS_AVAILABLE flag
try:
    import geopandas as gpd
    from shapely.geometry import Point, LineString, Polygon # Optional, but often used with GeoDataFrame
    GEOPANDAS_AVAILABLE = True
except ImportError:
    gpd = None # type: ignore
    Point, LineString, Polygon = type(None), type(None), type(None) # type: ignore
    GEOPANDAS_AVAILABLE = False


class EzdxfAdapter(IDXFAdapter):
    """Adapter for ezdxf library operations."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize adapter with injected logger service."""
        self._logger = logger_service.get_logger(__name__)
        if not EZDXF_AVAILABLE:
            self._logger.error("ezdxf library is not installed. DXF operations will fail.")

    def _ensure_ezdxf(self):
        if not EZDXF_AVAILABLE:
            self._logger.error("Attempted DXF operation, but ezdxf library is not installed.")
            raise DXFLibraryNotInstalledError("ezdxf library is not installed. Please install it to use DXF features.")

    def is_available(self) -> bool:
        """Check if ezdxf library is available."""
        return EZDXF_AVAILABLE

    def load_dxf_file(self, file_path: str) -> Optional[Drawing]:
        """Load a DXF file using ezdxf."""
        self._ensure_ezdxf()
        if not os.path.exists(file_path):
            self._logger.error(f"DXF file not found for loading: {file_path}")
            # Using the domain exception for consistency if defined
            raise DXFProcessingError(f"DXF file not found: {file_path}")
        try:
            self._logger.info(f"Loading DXF file: {file_path}")
            doc = ezdxf.readfile(file_path)
            return doc
        except DXFStructureError as e:
            self._logger.error(f"DXF Structure Error while loading {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid DXF file structure: {file_path}. Error: {e}")
        except IOError as e:
            self._logger.error(f"IOError while loading DXF file {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Could not read DXF file: {file_path}. Error: {e}")
        except Exception as e:
            self._logger.error(f"Unexpected error loading DXF file {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Unexpected error loading DXF file {file_path}. Error: {e}")

    def extract_entities_from_layer(
        self,
        dxf_document: Drawing,
        layer_name: str,
        crs: str # This was in the interface, but not used here.
    ) -> Optional[List[Any]]: # Returning list of ezdxf entities
        self._ensure_ezdxf()
        if not dxf_document:
            raise DXFProcessingError("DXF Document is None")
        try:
            msp = dxf_document.modelspace()
            entities = list(msp.query(f'''*[layer=="{layer_name}"]'''))
            self._logger.info(f"Extracted {len(entities)} entities from layer: {layer_name}")
            return entities
        except Exception as e:
            error_msg = f"Failed to extract entities from layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def save_document(self, doc: Drawing, file_path: str) -> None: # Renamed from save_dxf_file
        """Save a DXF document to file."""
        self._ensure_ezdxf()
        if not doc:
            raise DXFProcessingError("DXF document is None, cannot save.")
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self._logger.debug(f"Saving DXF file: {file_path}")

            doc.saveas(file_path)
            self._logger.info(f"Successfully saved DXF file: {file_path}")
        except Exception as e:
            error_msg = f"Failed to save DXF file {file_path}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def create_dxf_layer(self, dxf_document: Drawing, layer_name: str, **properties) -> None:
        """Create or update a DXF layer with specified properties."""
        self._ensure_ezdxf()
        if not dxf_document:
            raise DXFProcessingError("DXF Document is None, cannot create layer.")
        try:
            layers = dxf_document.layers
            if layer_name not in layers:
                layer = layers.add(layer_name)
                self._logger.debug(f"Created new DXF layer: {layer_name}")
            else:
                layer = layers.get(layer_name)
                self._logger.debug(f"Ensured DXF layer exists: {layer_name}")

            if 'color' in properties and properties['color'] is not None:
                layer.color = properties['color']
            if 'linetype' in properties and properties['linetype'] is not None:
                layer.dxf.linetype = properties['linetype'].upper()
            if 'lineweight' in properties and properties['lineweight'] is not None:
                layer.lineweight = properties['lineweight']
            if 'plot' in properties and properties['plot'] is not None:
                layer.plot = int(properties['plot'])
            if 'true_color' in properties and properties['true_color'] is not None:
                layer.true_color = properties['true_color']

        except DXFValueError as e:
            error_msg = f"DXFValueError for DXF layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create/update DXF layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def add_geodataframe_to_dxf(
        self,
        dxf_document: Drawing,
        gdf: 'gpd.GeoDataFrame',
        layer_name: str,
        **style_properties
    ) -> None:
        self._ensure_ezdxf()
        if not dxf_document:
            raise DXFProcessingError("DXF Document is None.")
        if gdf is None or gdf.empty:
            self._logger.info(f"GeoDataFrame is empty or None for layer {layer_name}. Nothing to add.")
            return
        try:
            msp = dxf_document.modelspace()
            for _idx, row in gdf.iterrows():
                geometry = row.geometry
                attributes = {'layer': layer_name}

                if geometry.geom_type == 'Point':
                    msp.add_point((geometry.x, geometry.y), dxfattribs=attributes)
                elif geometry.geom_type == 'LineString':
                    points = [(pt[0], pt[1]) for pt in geometry.coords]
                    msp.add_lwpolyline(points, dxfattribs=attributes)
                elif geometry.geom_type == 'Polygon':
                    points_ext = [(pt[0], pt[1]) for pt in geometry.exterior.coords]
                    hatch = msp.add_hatch(color=style_properties.get('color'), dxfattribs=attributes)
                    hatch.paths.add_polyline_path(points_ext, is_closed=True)
            self._logger.info(f"Added {len(gdf)} geometries to DXF layer: {layer_name}")
        except Exception as e:
            error_msg = f"Failed to add geometries from GeoDataFrame to DXF layer {layer_name}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def create_document(self, dxf_version: Optional[str] = None) -> Drawing:
        self._ensure_ezdxf()
        effective_dxf_version = dxf_version if dxf_version else "AC1027"
        try:
            self._logger.debug(f"Creating new DXF document, version: {effective_dxf_version}")
            doc = ezdxf.new(dxfversion=effective_dxf_version)
            if "0" not in doc.layers:
                 doc.layers.add("0")
            self._logger.info(f"Successfully created new DXF document (version {effective_dxf_version}).")
            return doc
        except Exception as e:
            error_msg = f"Failed to create new DXF document (version {effective_dxf_version}): {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def get_modelspace(self, doc: Drawing) -> Modelspace:
        self._ensure_ezdxf()
        if not doc:
            raise DXFProcessingError("DXF document is None, cannot get modelspace.")
        try:
            return doc.modelspace()
        except Exception as e:
            error_msg = f"Failed to get modelspace from DXF document: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def create_text_style(self, doc: Drawing, style_name: str, font_name: str) -> TextStyle:
        self._ensure_ezdxf()
        if not doc:
            raise DXFProcessingError("DXF document is None, cannot create text style.")
        try:
            self._logger.debug(f"Ensuring text style '{style_name}' with font '{font_name}'.")
            if style_name in doc.styles:
                existing_style = doc.styles.get(style_name)
                if existing_style.dxf.font.lower() == font_name.lower():
                    self._logger.debug(f"Text style '{style_name}' already exists with font '{font_name}'.")
                    return existing_style
                else:
                    self._logger.warning(f"Text style '{style_name}' exists with different font. Overwriting not implemented, returning existing.")
                    return existing_style
            style = doc.styles.new(style_name, dxfattribs={'font': font_name})
            self._logger.info(f"Successfully created text style '{style_name}'.")
            return style
        except DXFValueError as e:
            error_msg = f"DXFValueError creating text style '{style_name}': {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create text style '{style_name}': {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def create_linetype(self, doc: Drawing, ltype_name: str, pattern: List[float], description: Optional[str] = None) -> Linetype:
        self._ensure_ezdxf()
        if not doc:
            raise DXFProcessingError("DXF document is None, cannot create linetype.")
        try:
            self._logger.debug(f"Ensuring linetype '{ltype_name}'.")
            if ltype_name in doc.linetypes:
                self._logger.debug(f"Linetype '{ltype_name}' already exists.")
                return doc.linetypes.get(ltype_name)
            effective_description = description if description else f"Linetype {ltype_name}"
            ltype = doc.linetypes.new(ltype_name, dxfattribs={
                'description': effective_description,
                'pattern': pattern,
            })
            self._logger.info(f"Successfully created linetype '{ltype_name}'.")
            return ltype
        except DXFValueError as e:
            error_msg = f"DXFValueError creating linetype '{ltype_name}': {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create linetype '{ltype_name}': {e}"
            self._logger.error(error_msg, exc_info=True)
            raise DXFProcessingError(error_msg) from e

    def _convert_transparency_to_dxf_format(self, transparency_value: float) -> int:
        """Converts a float (0.0=opaque, 1.0=transparent) to DXF integer format."""
        # DXF transparency: 0x020000TT = recommended format
        # TT is transparency value from 0 (opaque) to 0xFF (100% transparent)

        if not (0.0 <= transparency_value <= 1.0):
            self._logger.warning(f"Transparency value {transparency_value} out of 0.0-1.0 range. Clamping.")
            transparency_value = max(0.0, min(1.0, transparency_value))

        tt_byte = int(transparency_value * 255)  # 0 (opaque) to 255 (fully transparent)

        # Recommended DXF format: 0x020000TT
        # This ensures that the transparency is interpreted directly and not as ByLayer or ByBlock
        # or an ACI color index.
        dxf_transparency_integer = (2 << 24) | tt_byte
        self._logger.debug(f"Converted transparency float {transparency_value:.2f} to DXF integer 0x{dxf_transparency_integer:08X} (TT byte: {tt_byte})")
        return dxf_transparency_integer

    def set_entity_properties(
        self,
        entity: Any,
        layer: Optional[str] = None,
        color: Optional[int] = None,
        linetype: Optional[str] = None,
        lineweight: Optional[int] = None,
        transparency: Optional[float] = None,
    ) -> None:
        self._ensure_ezdxf()
        if not entity:
            self._logger.warning("Attempted to set properties on a None entity.")
            return
        try:
            dxfattribs = {}
            if layer is not None:
                dxfattribs['layer'] = layer
            if color is not None:
                dxfattribs['color'] = color
            if linetype is not None:
                dxfattribs['linetype'] = linetype.upper()
            if lineweight is not None:
                dxfattribs['lineweight'] = lineweight
            if transparency is not None:
                if hasattr(entity.dxf, "transparency"):
                    dxfattribs['transparency'] = self._convert_transparency_to_dxf_format(transparency)
                else:
                    self._logger.debug(f"Entity type {entity.dxftype()} may not directly support 'transparency' attribute. Property not set.")

            if dxfattribs:
                # entity.dxf_attrib_exists # This is not a method, but an attribute check
                for key, value in dxfattribs.items():
                    try:
                        entity.dxf.set(key, value)
                    except (DXFValueError, AttributeError) as e_set:
                        self._logger.warning(f"Could not set DXF attribute '{key}' to '{value}' for entity {entity.dxf.handle if hasattr(entity.dxf, 'handle') else type(entity)}: {e_set}")
            self._logger.debug(f"Set properties for entity: {dxfattribs}")
        except AttributeError as e:
            self._logger.error(f"AttributeError setting properties for entity: {e}", exc_info=True)
            if entity:
                raise DXFProcessingError(f"Failed to set properties on entity: {e}")
        except Exception as e:
            self._logger.error(f"Unexpected error setting entity properties: {e}", exc_info=True)
            raise DXFProcessingError(f"Unexpected error setting entity properties: {e}")

    def add_text(
        self,
        msp: Modelspace,
        text: str,
        dxfattribs: Optional[Dict[str, Any]] = None,
        point: Tuple[float, float, float] = (0, 0, 0),
        height: float = 2.5,
        rotation: float = 0,
        style: Optional[str] = None,
    ) -> Text:
        self._ensure_ezdxf()
        if msp is None: raise DXFProcessingError("Modelspace is None, cannot add TEXT entity.")
        try:
            current_dxfattribs = dxfattribs.copy() if dxfattribs else {}
            current_dxfattribs['insert'] = point
            # text content is passed directly to add_text, not as dxfattrib
            current_dxfattribs['height'] = height
            current_dxfattribs['rotation'] = rotation
            if style:
                current_dxfattribs['style'] = style
            if 'layer' not in current_dxfattribs:
                current_dxfattribs['layer'] = "0"

            text_entity = msp.add_text(text=text, dxfattribs=current_dxfattribs)
            self._logger.debug(f"Added TEXT entity: '{text}' at {point}")
            return text_entity
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding TEXT entity: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding TEXT: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add TEXT entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add TEXT entity: {e}")

    def add_mtext(
        self,
        msp: Modelspace,
        text: str,
        dxfattribs: Optional[Dict[str, Any]] = None,
        insert: Tuple[float, float, float] = (0, 0, 0),
        char_height: float = 2.5,
        width: Optional[float] = None,
        style: Optional[str] = None,
    ) -> MText:
        self._ensure_ezdxf()
        if msp is None: raise DXFProcessingError("Modelspace is None, cannot add MTEXT entity.")
        try:
            current_dxfattribs = dxfattribs.copy() if dxfattribs else {}
            current_dxfattribs['insert'] = insert
            current_dxfattribs['char_height'] = char_height
            if style:
                current_dxfattribs['style'] = style
            if width is not None:
                current_dxfattribs['width'] = width
            if 'layer' not in current_dxfattribs:
                current_dxfattribs['layer'] = "0"

            # MTEXT content is passed directly
            mtext_entity = msp.add_mtext(text=text, dxfattribs=current_dxfattribs)
            self._logger.debug(f"Added MTEXT entity at {insert}")
            return mtext_entity
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding MTEXT entity: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding MTEXT: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add MTEXT entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add MTEXT entity: {e}")

    def add_point(
        self,
        msp: Modelspace,
        location: Tuple[float, float, float],
        dxfattribs: Optional[Dict[str, Any]] = None
    ) -> DXFPoint:
        self._ensure_ezdxf()
        if msp is None: raise DXFProcessingError("Modelspace is None, cannot add POINT entity.")
        try:
            current_dxfattribs = dxfattribs.copy() if dxfattribs else {}
            # location is passed directly
            if 'layer' not in current_dxfattribs: current_dxfattribs['layer'] = "0"
            point_entity = msp.add_point(location=location, dxfattribs=current_dxfattribs)
            self._logger.debug(f"Added POINT entity at {location}")
            return point_entity
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding POINT entity: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding POINT: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add POINT entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add POINT entity: {e}")

    def add_line(
        self,
        msp: Modelspace,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        dxfattribs: Optional[Dict[str, Any]] = None,
    ) -> DXFLine:
        self._ensure_ezdxf()
        if msp is None: raise DXFProcessingError("Modelspace is None, cannot add LINE entity.")
        try:
            current_dxfattribs = dxfattribs.copy() if dxfattribs else {}
            # start and end are passed directly
            if 'layer' not in current_dxfattribs: current_dxfattribs['layer'] = "0"
            line_entity = msp.add_line(start=start, end=end, dxfattribs=current_dxfattribs)
            self._logger.debug(f"Added LINE entity from {start} to {end}")
            return line_entity
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding LINE entity: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding LINE: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add LINE entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add LINE entity: {e}")

    def add_lwpolyline(
        self,
        msp: Modelspace,
        points: List[Tuple[float, float]],
        format_str: str = "xy",
        close: bool = False,
        dxfattribs: Optional[Dict[str, Any]] = None,
    ) -> LWPolyline:
        self._ensure_ezdxf()
        if msp is None: raise DXFProcessingError("Modelspace is None, cannot add LWPOLYLINE entity.")
        if not points: raise DXFProcessingError("Points list is empty for LWPOLYLINE.")
        try:
            current_dxfattribs = dxfattribs.copy() if dxfattribs else {}
            if 'layer' not in current_dxfattribs: current_dxfattribs['layer'] = "0"
            lwpolyline_entity = msp.add_lwpolyline(
                points=points, format=format_str, close=close, dxfattribs=current_dxfattribs
            )
            self._logger.debug(f"Added LWPOLYLINE entity with {len(points)} points.")
            return lwpolyline_entity
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding LWPOLYLINE entity: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding LWPOLYLINE: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add LWPOLYLINE entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add LWPOLYLINE entity: {e}")

    def add_hatch(
        self,
        msp: Modelspace,
        color: Optional[int] = None,
        dxfattribs: Optional[Dict[str, Any]] = None
    ) -> Hatch:
        self._ensure_ezdxf()
        if msp is None: raise DXFProcessingError("Modelspace is None, cannot add HATCH entity.")
        try:
            current_dxfattribs = dxfattribs.copy() if dxfattribs else {}
            if color is not None:
                current_dxfattribs['color'] = color
            if 'layer' not in current_dxfattribs: current_dxfattribs['layer'] = "0"
            if 'pattern_name' not in current_dxfattribs: current_dxfattribs['pattern_name'] = "SOLID"

            hatch_entity = msp.add_hatch(dxfattribs=current_dxfattribs)
            self._logger.debug(f"Added HATCH entity. Pattern: {current_dxfattribs.get('pattern_name')}")
            return hatch_entity
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding HATCH entity: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding HATCH: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add HATCH entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add HATCH entity: {e}")

    def add_hatch_boundary_path(
        self,
        hatch_entity: Hatch,
        points: List[Tuple[float, float]],
        flags: int = ezdxf_const.BOUNDARY_PATH_POLYLINE if EZDXF_AVAILABLE else 1
    ) -> None:
        self._ensure_ezdxf()
        if not hatch_entity:
            raise DXFProcessingError("Hatch entity is None, cannot add boundary path.")
        try:
            hatch_entity.paths.add_polyline_path(points, flags=flags, is_closed=True)
            self._logger.debug(f"Added boundary path with {len(points)} points to HATCH entity.")
        except DXFValueError as e:
            self._logger.error(f"DXFValueError adding boundary path to HATCH: {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError adding boundary path to HATCH: {e}")
        except Exception as e:
            self._logger.error(f"Failed to add boundary path to HATCH entity: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add boundary path to HATCH entity: {e}")

    def get_layer(self, doc: Drawing, layer_name: str) -> Optional[Layer]:
        self._ensure_ezdxf()
        if not doc:
            raise DXFProcessingError("DXF document is None, cannot get layer.")
        try:
            if layer_name in doc.layers:
                layer = doc.layers.get(layer_name)
                self._logger.debug(f"Retrieved layer: '{layer_name}'.")
                return layer
            else:
                self._logger.debug(f"Layer '{layer_name}' not found.")
                return None
        except DXFValueError as e:
            self._logger.error(f"DXFValueError getting layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError getting layer '{layer_name}': {e}")
        except Exception as e:
            self._logger.error(f"Failed to get layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to get layer '{layer_name}': {e}")

    def set_layer_properties(
        self,
        doc: Drawing,
        layer_name: str,
        color: Optional[int] = None,
        linetype: Optional[str] = None,
        lineweight: Optional[int] = None,
        plot: Optional[bool] = None,
        on: Optional[bool] = None,
        frozen: Optional[bool] = None,
        locked: Optional[bool] = None
    ) -> None:
        self._ensure_ezdxf()
        layer_to_modify = doc.layers.get(layer_name)
        if not layer_to_modify:
            self._logger.error(f"Layer '{layer_name}' not found in document, cannot set properties.")
            raise DXFProcessingError(f"Layer '{layer_name}' not found in document for property setting.")

        try:
            if color is not None:
                layer_to_modify.color = color

            if linetype is not None:
                uppercase_linetype = linetype.upper()
                if uppercase_linetype in doc.linetypes:
                    layer_to_modify.dxf.linetype = uppercase_linetype
                    self._logger.debug(f"LAYER_PROP_SET: Layer '{layer_name}' linetype set to '{uppercase_linetype}'. Actual after set: '{layer_to_modify.dxf.linetype}'")
                else:
                    self._logger.error(f"LAYER_PROP_SET: Linetype '{uppercase_linetype}' not found in doc.linetypes for layer '{layer_name}'. Linetype not changed.")

            if lineweight is not None:
                layer_to_modify.dxf.lineweight = lineweight
                self._logger.debug(f"LAYER_PROP_SET: Layer '{layer_name}' lineweight set to '{lineweight}' via .dxf.lineweight. Actual after set: '{layer_to_modify.dxf.lineweight}'")

            if plot is not None:
                layer_to_modify.plot = int(plot)

            if on is not None:
                if on:
                    layer_to_modify.is_on = True
                else:
                    layer_to_modify.is_off = True
            if frozen is not None:
                if frozen:
                    layer_to_modify.freeze()
                else:
                    layer_to_modify.thaw()
            if locked is not None:
                if locked:
                    layer_to_modify.lock()
                else:
                    layer_to_modify.unlock()

            self._logger.debug(f"Set properties for layer: '{layer_name}'. Color: {color}, LType: {linetype}, LW: {lineweight}, Plot: {plot}, On: {on}, Frozen: {frozen}, Locked: {locked}")

        except DXFValueError as e:
            self._logger.error(f"DXFValueError setting properties for layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"DXFValueError setting properties for layer '{layer_name}': {e}")
        except AttributeError as e:
            self._logger.error(f"AttributeError setting properties for layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid layer entity or attribute issue for '{layer_name}': {e}")
        except Exception as e:
            self._logger.error(f"Failed to set properties for layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to set properties for layer '{layer_name}': {e}")

    def query_entities(self, modelspace_or_block: Any, query_string: str = "*") -> List[Any]:
        self._ensure_ezdxf()
        self._logger.debug(f"Querying entities in {'modelspace/block'} with query: {query_string}")
        try:
            # Assuming modelspace_or_block is a valid ezdxf layout object
            return list(modelspace_or_block.query(query_string))
        except DXFValueError as e:
            self._logger.error(f"DXFValueError during entity query '{query_string}': {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid query string or entity type for query: {query_string}. Error: {e}") from e
        except Exception as e:
            self._logger.error(f"Unexpected error during entity query '{query_string}': {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to query entities with '{query_string}'. Error: {e}") from e

    def set_hatch_pattern_fill(
        self,
        hatch_entity: Any, # Should be ezdxf.entities.Hatch
        pattern_name: str,
        color: Optional[int] = None,
        scale: Optional[float] = None,
        angle: Optional[float] = None
    ) -> None:
        self._ensure_ezdxf()
        if not isinstance(hatch_entity, ezdxf.entities.Hatch): # Basic type check
            err_msg = f"Invalid entity type for set_hatch_pattern_fill. Expected ezdxf.entities.Hatch, got {type(hatch_entity)}."
            self._logger.error(err_msg)
            raise DXFProcessingError(err_msg)

        self._logger.debug(f"Setting pattern fill for HATCH (handle: {hatch_entity.dxf.handle if hasattr(hatch_entity, 'dxf') else 'N/A'}): name='{pattern_name}', color={color}, scale={scale}, angle={angle}")
        try:
            # Parameters for ezdxf's set_pattern_fill:
            # name: str, color: Optional[int] = None, angle: Optional[float] = None,
            # scale: Optional[float] = None, double: Optional[bool] = None,
            # style: Optional[int] = None, pattern_type: Optional[int] = None,
            # definition = None
            hatch_entity.set_pattern_fill(
                name=pattern_name,
                color=color,
                angle=angle,
                scale=scale
                # Not exposing double, style, pattern_type, definition in this adapter method for now
            )
            hatch_entity.dxf.solid_fill = 0 # Ensure solid_fill flag is off for pattern
        except DXFValueError as e:
            self._logger.error(f"DXFValueError setting pattern fill for HATCH: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid parameters for HATCH pattern fill. Error: {e}") from e
        except AttributeError as e: # If hatch_entity is not a valid ezdxf Hatch
            self._logger.error(f"AttributeError: Invalid HATCH entity for set_hatch_pattern_fill: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid HATCH entity provided. Error: {e}") from e
        except Exception as e:
            self._logger.error(f"Unexpected error setting pattern fill for HATCH: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to set pattern fill for HATCH. Error: {e}") from e

    def set_hatch_solid_fill(
        self,
        hatch_entity: Any, # Should be ezdxf.entities.Hatch
        color: Optional[int] = None
    ) -> None:
        self._ensure_ezdxf()
        if not isinstance(hatch_entity, ezdxf.entities.Hatch): # Basic type check
            err_msg = f"Invalid entity type for set_hatch_solid_fill. Expected ezdxf.entities.Hatch, got {type(hatch_entity)}."
            self._logger.error(err_msg)
            raise DXFProcessingError(err_msg)

        self._logger.debug(f"Setting solid fill for HATCH (handle: {hatch_entity.dxf.handle if hasattr(hatch_entity, 'dxf') else 'N/A'}): color={color}")
        try:
            # Parameters for ezdxf's set_solid_fill:
            # color: Optional[int] = None, style: Optional[int] = None,
            # rgb: Optional[Tuple[int, int, int]] = None
            hatch_entity.set_solid_fill(
                color=color
                # Not exposing style or rgb in this adapter method for now
            )
            # The ezdxf.set_solid_fill() method should also set dxf.solid_fill = 1
            # and clear pattern data, but we can be explicit if needed:
            # hatch_entity.dxf.solid_fill = 1
            # hatch_entity.pattern = None # Or clear pattern definition appropriately
        except DXFValueError as e:
            self._logger.error(f"DXFValueError setting solid fill for HATCH: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid parameters for HATCH solid fill. Error: {e}") from e
        except AttributeError as e: # If hatch_entity is not a valid ezdxf Hatch
            self._logger.error(f"AttributeError: Invalid HATCH entity for set_hatch_solid_fill: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid HATCH entity provided. Error: {e}") from e
        except Exception as e:
            self._logger.error(f"Unexpected error setting solid fill for HATCH: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to set solid fill for HATCH. Error: {e}") from e
