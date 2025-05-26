"""Interface for DXF library adapters."""
from typing import Protocol, Optional, Any, Dict, List, Tuple
import geopandas as gpd

from ..domain.exceptions import DXFProcessingError


class IDXFAdapter(Protocol):
    """Interface for adapters that handle DXF library operations."""

    def load_dxf_file(self, file_path: str) -> Optional[Any]:
        """
        Load a DXF file using the underlying DXF library.

        Args:
            file_path: Path to the DXF file to load.

        Returns:
            DXF document object or None if loading fails.

        Raises:
            DXFProcessingError: If DXF file cannot be loaded.
        """
        ...

    def extract_entities_from_layer(
        self,
        dxf_document: Any,
        layer_name: str,
        crs: str
    ) -> Optional[gpd.GeoDataFrame]:
        """
        Extract entities from a specific DXF layer.

        Args:
            dxf_document: The DXF document object.
            layer_name: Name of the layer to extract from.
            crs: Coordinate reference system for the output.

        Returns:
            GeoDataFrame with extracted entities or None if layer not found.

        Raises:
            DXFProcessingError: If entity extraction fails.
        """
        ...

    def save_document(self, doc: Any, file_path: str) -> None:
        """
        Save a DXF document to a file.

        Args:
            doc: DXF document object.
            file_path: Path to save the DXF file.

        Raises:
            DXFProcessingError: If DXF file cannot be saved.
        """
        ...

    def create_dxf_layer(self, dxf_document: Any, layer_name: str, **properties) -> None:
        """
        Create or update a DXF layer with specified properties.

        Args:
            dxf_document: The DXF document object.
            layer_name: Name of the layer to create/update.
            **properties: Layer properties (color, linetype, etc.).

        Raises:
            DXFProcessingError: If layer creation fails.
        """
        ...

    def add_geodataframe_to_dxf(
        self,
        dxf_document: Any,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        **style_properties
    ) -> None:
        """
        Add geometries from GeoDataFrame to DXF document.

        Args:
            dxf_document: The DXF document object.
            gdf: GeoDataFrame containing geometries to add.
            layer_name: Name of the target DXF layer.
            **style_properties: Style properties to apply.

        Raises:
            DXFProcessingError: If geometry addition fails.
        """
        ...

    def is_available(self) -> bool:
        """
        Check if the DXF library is available.

        Returns:
            True if DXF library is available, False otherwise.
        """
        ...

    def create_document(self, dxf_version: Optional[str] = None) -> Any:
        """
        Create a new DXF document.

        Args:
            dxf_version: Optional DXF version string (e.g., \"AC1027\" for R2013).
                         If None, library default is used.

        Returns:
            A new DXF document object.

        Raises:
            DXFProcessingError: If document creation fails.
        """
        ...

    def get_modelspace(self, doc: Any) -> Any:
        """
        Get the modelspace of a DXF document.

        Args:
            doc: DXF document object.

        Returns:
            The modelspace object.

        Raises:
            DXFProcessingError: If modelspace cannot be retrieved.
        """
        ...

    def create_text_style(self, doc: Any, style_name: str, font_name: str) -> Any:
        """
        Creates a new text style in the DXF document.

        Args:
            doc: The DXF document.
            style_name: Name of the text style to create (e.g., "Standard_Bold").
            font_name: Name of the font file (e.g., "arial.ttf").

        Returns:
            The created text style table entry.

        Raises:
            DXFProcessingError: If the style cannot be created or already exists with incompatible settings.
        """
        ...

    def create_linetype(self, doc: Any, ltype_name: str, pattern: List[float], description: Optional[str] = None) -> Any:
        """
        Creates a new linetype in the DXF document.

        Args:
            doc: The DXF document.
            ltype_name: Name of the linetype (e.g., "DASHED").
            pattern: A list of floats describing the pattern (e.g., [0.5, -0.25, 0.0, -0.25]).
                     Positive values are line segments, negative values are gaps, 0 is a dot.
            description: Optional textual description of the linetype.

        Returns:
            The created linetype table entry.

        Raises:
            DXFProcessingError: If the linetype cannot be created.
        """
        ...

    def set_entity_properties(
        self,
        entity: Any,
        layer: Optional[str] = None,
        color: Optional[int] = None,
        linetype: Optional[str] = None,
        lineweight: Optional[int] = None,
        transparency: Optional[float] = None,
    ) -> None:
        """
        Sets common DXF properties for a given entity.

        Args:
            entity: The DXF entity to modify.
            layer: Target layer name.
            color: ACI color index.
            linetype: Name of the linetype.
            lineweight: Lineweight value (e.g., 25 for 0.25mm).
            transparency: Transparency value (0.0 for opaque, 1.0 for invisible).

        Raises:
            DXFProcessingError: If properties cannot be set.
        """
        ...

    def add_text(
        self,
        msp: Any,
        text: str,
        dxfattribs: Optional[Dict[str, Any]] = None,
        point: Tuple[float, float, float] = (0, 0, 0),
        height: float = 2.5,
        rotation: float = 0,
        style: Optional[str] = None,
    ) -> Any:
        """
        Adds a TEXT entity to the modelspace.

        Args:
            msp: Modelspace object.
            text: The text string.
            dxfattribs: Optional dictionary of DXF attributes for the TEXT entity.
                        These are applied after layer, color, linetype if those are also in dxfattribs.
                        Common attributes like 'layer', 'color', 'style', 'height', 'rotation'
                        can be set here or via dedicated parameters.
            point: Insertion point (x, y, z).
            height: Text height.
            rotation: Text rotation in degrees.
            style: Text style name.

        Returns:
            The created TEXT entity.

        Raises:
            DXFProcessingError: If the entity cannot be added.
        """
        ...

    def add_mtext(
        self,
        msp: Any,
        text: str,
        dxfattribs: Optional[Dict[str, Any]] = None,
        insert: Tuple[float, float, float] = (0, 0, 0),
        char_height: float = 2.5,
        width: Optional[float] = None,
        style: Optional[str] = None,
    ) -> Any:
        """
        Adds an MTEXT entity to the modelspace.

        Args:
            msp: Modelspace object.
            text: The text string (can include MTEXT formatting codes).
            dxfattribs: Optional dictionary of DXF attributes for the MTEXT entity.
            insert: Insertion point (x, y, z).
            char_height: Character height.
            width: Optional width of the MTEXT bounding box.
            style: Text style name.

        Returns:
            The created MTEXT entity.

        Raises:
            DXFProcessingError: If the entity cannot be added.
        """
        ...

    def add_point(
        self,
        msp: Any,
        location: Tuple[float, float, float],
        dxfattribs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Adds a POINT entity to the modelspace.

        Args:
            msp: Modelspace object.
            location: Location of the point (x, y, z).
            dxfattribs: Optional dictionary of DXF attributes for the POINT entity.

        Returns:
            The created POINT entity.

        Raises:
            DXFProcessingError: If the entity cannot be added.
        """
        ...

    def add_line(
        self,
        msp: Any,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        dxfattribs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Adds a LINE entity to the modelspace.

        Args:
            msp: Modelspace object.
            start: Start point of the line (x, y, z).
            end: End point of the line (x, y, z).
            dxfattribs: Optional dictionary of DXF attributes for the LINE entity.

        Returns:
            The created LINE entity.

        Raises:
            DXFProcessingError: If the entity cannot be added.
        """
        ...

    def add_lwpolyline(
        self,
        msp: Any,
        points: List[Tuple[float, float]],
        format_str: str = "xy",
        close: bool = False,
        dxfattribs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Adds an LWPOLYLINE entity to the modelspace.

        Args:
            msp: Modelspace object.
            points: List of (x, y) tuples defining the polyline vertices.
                    Bulge values can be included if format_str supports it (e.g., "xyb").
            format_str: Vertex format string (e.g., "xy", "xyb" for x, y, bulge).
            close: If True, the polyline is closed.
            dxfattribs: Optional dictionary of DXF attributes for the LWPOLYLINE entity.

        Returns:
            The created LWPOLYLINE entity.

        Raises:
            DXFProcessingError: If the entity cannot be added.
        """
        ...

    def add_hatch(
        self,
        msp: Any,
        color: Optional[int] = None,
        dxfattribs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Adds a HATCH entity to the modelspace. Boundary paths must be added separately.

        Args:
            msp: Modelspace object.
            color: Optional ACI color for the hatch.
            dxfattribs: Optional dictionary of DXF attributes for the HATCH entity.
                        Common ones: 'pattern_name', 'scale', 'angle'.

        Returns:
            The created HATCH entity.

        Raises:
            DXFProcessingError: If the entity cannot be added.
        """
        ...

    def add_hatch_boundary_path(
        self,
        hatch_entity: Any,
        points: List[Tuple[float, float]],
        flags: int # e.g., ezdxf.const.BOUNDARY_PATH_POLYLINE
    ) -> None:
        """
        Adds a polyline boundary path to a HATCH entity.

        Args:
            hatch_entity: The HATCH entity object.
            points: List of (x, y) coordinates for the boundary path.
            flags: Boundary path flags (e.g., from ezdxf.const).

        Raises:
            DXFProcessingError: If the boundary path cannot be added.
        """
        ...

    def get_layer(self, doc: Any, layer_name: str) -> Optional[Any]:
        """
        Retrieves a specific layer object from the DXF document.

        Args:
            doc: The DXF document object.
            layer_name: Name of the layer to retrieve.

        Returns:
            The layer object if found, otherwise None.

        Raises:
            DXFProcessingError: If there's an issue accessing layers.
        """
        ...

    def set_layer_properties(
        self,
        layer_entity: Any,
        color: Optional[int] = None,
        linetype: Optional[str] = None,
        lineweight: Optional[int] = None,
        plot: Optional[bool] = None,
        on: Optional[bool] = None,
        frozen: Optional[bool] = None,
        locked: Optional[bool] = None
    ) -> None:
        """
        Sets properties for a given DXF layer entity.

        Args:
            layer_entity: The DXF layer entity to modify.
            color: ACI color index.
            linetype: Name of the linetype.
            lineweight: Lineweight value (e.g., 25 for 0.25mm).
            plot: Plot status (True to plot, False to not plot).
            on: Layer on/off status (True for on, False for off).
            frozen: Layer frozen/thawed status (True for frozen).
            locked: Layer locked/unlocked status (True for locked).

        Raises:
            DXFProcessingError: If properties cannot be set.
        """
        ...

    def query_entities(self, modelspace_or_block: Any, query_string: str = "*") -> List[Any]:
        """
        Queries entities within a given modelspace or block layout.

        Args:
            modelspace_or_block: The modelspace or block object to query.
            query_string: The query string (e.g., entity types, layer).

        Returns:
            List of found DXF entities.

        Raises:
            DXFProcessingError: If querying fails.
        """
        ...

    def set_hatch_pattern_fill(
        self,
        hatch_entity: Any,
        pattern_name: str,
        color: Optional[int] = None,
        scale: Optional[float] = None,
        angle: Optional[float] = None
        # Potentially add other ezdxf params like:
        # double: Optional[bool] = None,
        # style: Optional[int] = None, # Hatch style (normal, outer, ignore)
        # pattern_type: Optional[int] = None, # User, predefined, custom
        # definition: Optional[List[Any]] = None # For user-defined patterns
    ) -> None:
        """
        Sets a pattern fill for a HATCH entity.

        Args:
            hatch_entity: The HATCH entity object.
            pattern_name: Name of the hatch pattern (e.g., "ANSI31").
            color: Optional ACI color index for the pattern.
            scale: Optional pattern scale factor.
            angle: Optional pattern angle in degrees.

        Raises:
            DXFProcessingError: If setting the pattern fill fails.
        """
        ...

    def set_hatch_solid_fill(
        self,
        hatch_entity: Any,
        color: Optional[int] = None
        # Potentially add other ezdxf params like:
        # style: Optional[int] = None, # Hatch style
        # rgb: Optional[Tuple[int, int, int]] = None # For true color
    ) -> None:
        """
        Sets a solid fill for a HATCH entity.

        Args:
            hatch_entity: The HATCH entity object.
            color: Optional ACI color index for the solid fill.

        Raises:
            DXFProcessingError: If setting the solid fill fails.
        """
        ...

    # TODO: Consider adding get_entity_properties if not already planned.
