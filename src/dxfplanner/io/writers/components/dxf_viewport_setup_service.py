from typing import Any, List, Optional, Tuple
import math
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ezdxf.math import BoundingBox
from ezdxf.math import ConstructionArc

from dxfplanner.config.schemas import ProjectConfig, DxfWriterConfig
from dxfplanner.config.dxf_writer_schemas import ViewportDetailConfig
from dxfplanner.domain.models.dxf_models import AnyDxfEntity, DxfPoint, DxfLine, DxfLWPolyline, DxfHatch, DxfCircle, DxfArc, DxfText, DxfMText, DxfInsert
from dxfplanner.domain.models.common import Coordinate, BoundingBox as BoundingBoxModel
from dxfplanner.domain.interfaces import IDxfViewportSetupService
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class DxfViewportSetupService(IDxfViewportSetupService):
    """Service for setting up DXF document viewports and initial views."""

    def __init__(self, project_config: ProjectConfig):
        self.project_config = project_config
        self.writer_config: DxfWriterConfig = project_config.dxf_writer
        self.logger = logger

    async def setup_drawing_view(
        self,
        doc: Drawing,
        msp: Modelspace, # Modelspace might not be strictly needed if we only configure doc-level views/vports
        entities_flat_list: List[AnyDxfEntity],
        # app_config is available via self.app_config
    ) -> None:
        """Sets up the main viewport and initial view of the DXF drawing."""
        self.logger.info("Setting up drawing view and viewport.")

        # Calculate overall bounding box from DxfEntity domain models
        overall_bbox_model = await self._calculate_overall_bbox_from_domain_models(entities_flat_list)

        if overall_bbox_model:
            self.logger.info(f"Calculated overall BBox from domain models: {overall_bbox_model}")
            await self._setup_initial_view_from_bbox(doc, overall_bbox_model)
        else:
            self.logger.warning("No entities or bounding box available to set initial view. Using default view.")
            # Potentially set a very basic default view if overall_bbox is None
            doc.header['$EXTMIN'] = (0, 0, 0)
            doc.header['$EXTMAX'] = (100, 100, 0)

        await self._setup_main_viewport(doc) # Viewport setup might be independent of extents or use them
        self.logger.info("Drawing view and viewport setup complete.")

    async def _calculate_bbox_for_dxf_entity(self, entity_model: AnyDxfEntity) -> Optional[BoundingBoxModel]:
        """Calculates a BoundingBoxModel for a single DxfEntity domain model."""
        # This is a simplified BBox calculation. Real BBox for text/mtext/insert depends on font metrics, block content etc.
        # For now, using point-based extents.
        coords: List[Coordinate] = []
        # For more complex entities, we might return a BoundingBoxModel directly
        # instead of accumulating coords, if their BBox is known without iterating points.

        if isinstance(entity_model, DxfPoint):
            coords.append(entity_model.position)
        elif isinstance(entity_model, DxfLine):
            coords.extend([entity_model.start_point, entity_model.end_point])
        elif isinstance(entity_model, DxfLWPolyline):
            coords.extend(entity_model.points)
        elif isinstance(entity_model, DxfHatch):
            for path in entity_model.paths:
                if path.is_polyline_path and path.polyline_vertices:
                    coords.extend(path.polyline_vertices)
                # TODO: Handle hatch edge paths (more complex) for BBox calculation
        elif isinstance(entity_model, DxfCircle): # Added DxfCircle BBox
            # Bounding box for a circle
            center = entity_model.center
            radius = entity_model.radius
            coords.append(Coordinate(x=center.x - radius, y=center.y - radius, z=center.z))
            coords.append(Coordinate(x=center.x + radius, y=center.y + radius, z=center.z))
        elif isinstance(entity_model, DxfArc): # Added DxfArc BBox
            try:
                # Use ezdxf.math.ConstructionArc for accurate bounding box
                arc_geo = ConstructionArc(
                    center=(entity_model.center.x, entity_model.center.y, entity_model.center.z or 0.0),
                    radius=entity_model.radius,
                    start_angle=entity_model.start_angle, # Assuming degrees
                    end_angle=entity_model.end_angle, # Assuming degrees
                    is_counter_clockwise=True # DxfArc model needs is_counter_clockwise, assume True if not present
                )
                arc_bbox_ezdxf = arc_geo.bounding_box
                coords.append(Coordinate(x=arc_bbox_ezdxf.extmin.x, y=arc_bbox_ezdxf.extmin.y, z=arc_bbox_ezdxf.extmin.z))
                coords.append(Coordinate(x=arc_bbox_ezdxf.extmax.x, y=arc_bbox_ezdxf.extmax.y, z=arc_bbox_ezdxf.extmax.z))
            except Exception as e_arc_bbox:
                self.logger.warning(f"Failed to calculate accurate BBox for DxfArc ({entity_model.layer}): {e_arc_bbox}. Falling back to points.")
                # Fallback: use center and points on circle at start/end angles as rough estimate
                coords.append(entity_model.center)
                # Basic fallback, could be improved by calculating actual start/end points
                # For now, this ensures the center is included if ConstructionArc fails. Start/end points are harder without a helper.

        elif isinstance(entity_model, (DxfText, DxfMText, DxfInsert)):
            # For text/insert, use insertion point as a minimal representation
            # A more accurate bbox would require rendering metrics or block extents
            coords.append(entity_model.insertion_point)
            # Could add a nominal size around it based on height/width if available
        # TODO: Add other DxfEntity types as needed (DxfEllipse, DxfSpline)

        if not coords:
            return None

        min_x = min(c.x for c in coords)
        min_y = min(c.y for c in coords)
        max_x = max(c.x for c in coords)
        max_y = max(c.y for c in coords)
        # Z coordinates are ignored for 2D BBox for now
        return BoundingBoxModel(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


    async def _calculate_overall_bbox_from_domain_models(self, entities: List[AnyDxfEntity]) -> Optional[BoundingBoxModel]:
        """Calculates the overall bounding box for a list of DxfEntity domain models."""
        if not entities:
            return None

        overall_min_x, overall_min_y = float('inf'), float('inf')
        overall_max_x, overall_max_y = float('-inf'), float('-inf')
        has_valid_bbox = False

        for entity_model in entities:
            bbox = await self._calculate_bbox_for_dxf_entity(entity_model)
            if bbox:
                has_valid_bbox = True
                overall_min_x = min(overall_min_x, bbox.min_x)
                overall_min_y = min(overall_min_y, bbox.min_y)
                overall_max_x = max(overall_max_x, bbox.max_x)
                overall_max_y = max(overall_max_y, bbox.max_y)

        if not has_valid_bbox:
            return None
        return BoundingBoxModel(min_x=overall_min_x, min_y=overall_min_y, max_x=overall_max_x, max_y=overall_max_y)


    async def _setup_initial_view_from_bbox(self, doc: Drawing, bbox: BoundingBoxModel) -> None:
        """Sets the initial view of the drawing based on a bounding box."""
        # Add some padding to the extents
        padding_factor = 0.1 # Default
        if self.writer_config.viewport_settings: # Use new detailed config if available
            padding_factor = self.writer_config.viewport_settings.bbox_padding_factor
        # Else, could fallback to an old flat field if one existed for this, or just use default.
        # Current DxfWriterConfig doesn't have a flat bbox_padding_factor.

        width = bbox.max_x - bbox.min_x
        height = bbox.max_y - bbox.min_y

        padding_x = width * padding_factor
        padding_y = height * padding_factor

        # Set header variables for drawing extents
        doc.header['$EXTMIN'] = (bbox.min_x - padding_x, bbox.min_y - padding_y, 0)
        doc.header['$EXTMAX'] = (bbox.max_x + padding_x, bbox.max_y + padding_y, 0)

        # Set drawing limits (optional, but can be good practice)
        # doc.header['$LIMMIN'] = doc.header['$EXTMIN'][:2]
        # doc.header['$LIMMAX'] = doc.header['$EXTMAX'][:2]

        # Set initial view (modelspace)
        # This sets the view that is active when the drawing is opened if no specific viewport is active.
        # For a 2D top-down view:
        center_x = (bbox.min_x + bbox.max_x) / 2
        center_y = (bbox.min_y + bbox.max_y) / 2

        # Determine view height based on the larger dimension of the padded bbox
        view_height = max(width + 2 * padding_x, height + 2 * padding_y)
        if view_height == 0: view_height = 100 # Default if bbox has zero area

        # Use documented ezdxf method to set initial modelspace view
        doc.set_modelspace_vport(height=view_height, center=(center_x, center_y))

        self.logger.info(f"Initial view set: Center=({center_x:.2f},{center_y:.2f}), ViewHeight={view_height:.2f}")

    async def _setup_main_viewport(self, doc: Drawing) -> None:
        """Sets up the main viewport (*PAPER_SPACE active viewport)."""

        if not self.writer_config.create_paperspace_layout:
            self.logger.info("Paperspace layout creation is disabled in DxfWriterConfig. Skipping viewport setup in paperspace.")
            return

        # Use new detailed viewport settings
        vp_detail_config: Optional[ViewportDetailConfig] = self.writer_config.viewport_settings

        if not vp_detail_config or not vp_detail_config.create_viewport:
            self.logger.info("Detailed viewport creation/configuration is disabled via viewport_settings. Skipping main viewport entity setup in paperspace.")
            # Note: Paperspace layout itself might still be created based on create_paperspace_layout
            return

        # Ensure a default PaperSpace layout exists if we are to add a viewport to it
        layout_name = self.writer_config.paperspace_layout_name or "*Paper_Space" # Use configured name or default
        if layout_name not in doc.layouts:
             ps = doc.layouts.new(layout_name)
        else:
            ps = doc.layouts.get(layout_name)

        self.logger.info(f"Setting up main viewport in layout '{layout_name}'. Center=({vp_detail_config.center_x_ps_paper},{vp_detail_config.center_y_ps_paper}), Size=({vp_detail_config.width_ps_paper}x{vp_detail_config.height_ps_paper})")

        # Define viewport properties on paper space
        center_ps = (vp_detail_config.center_x_ps_paper, vp_detail_config.center_y_ps_paper)
        width_ps = vp_detail_config.width_ps_paper
        height_ps = vp_detail_config.height_ps_paper

        # What the viewport in paper space looks at in model space
        view_center_ms_x = vp_detail_config.view_target_ms_x if vp_detail_config.view_target_ms_x is not None else doc.header.get('$VIEWCTR', (0,0,0))[0]
        view_center_ms_y = vp_detail_config.view_target_ms_y if vp_detail_config.view_target_ms_y is not None else doc.header.get('$VIEWCTR', (0,0,0))[1]
        view_center_ms = (view_center_ms_x, view_center_ms_y)

        view_height_ms = vp_detail_config.view_height_ms
        if view_height_ms is None: # If not directly set, try to calculate from scale or use $VIEWSIZE
            if self.writer_config.paperspace_viewport_scale and height_ps > 0: # scale is 1/X, so drawing_units / paper_units
                 # view_height_ms (model units) = viewport_height_paper_units / scale_factor
                 # scale_factor = model_units / paper_units. Example: 1:50 scale means 1 paper unit = 50 model units. Scale factor = 50.
                 # view_height_ms = height_ps * (1/paperspace_viewport_scale) if scale is given as output/input unit ratio.
                 # If paperspace_viewport_scale is like AutoCAD (1/50 = 0.02), then view_height_ms = height_ps / paperspace_viewport_scale
                 # The current description of paperspace_viewport_scale is "Scale for the viewport in paperspace (e.g., 1/50 = 0.02)"
                 # This is PaperUnits / DrawingUnits.
                 # So, ModelSpaceHeight = PaperSpaceViewportHeight / (PaperUnits/DrawingUnits)
                if self.writer_config.paperspace_viewport_scale > 0:
                    view_height_ms = height_ps / self.writer_config.paperspace_viewport_scale
                else:
                    view_height_ms = doc.header.get('$VIEWSIZE', 100.0) # Fallback if scale is zero or invalid
            else:
                view_height_ms = doc.header.get('$VIEWSIZE', 100.0) # Fallback if no scale and no direct height

        try:
            # Create the viewport entity in paper space
            # Note: ezdxf < 0.17 add_viewport is different from >=0.17
            # Assuming modern ezdxf (>=0.17, add_viewport is on layout)
            if hasattr(ps, "add_viewport"):
                viewport = ps.add_viewport(
                    center=center_ps,  # Center of viewport in paper space
                    width=width_ps,    # Width of viewport in paper space
                    height=height_ps,  # Height of viewport in paper space
                    view_center_point=view_center_ms, # Model space point to center on
                    view_height=view_height_ms # Model space height to fit in viewport
                )
                # Further viewport properties can be set:
                viewport.dxf.status = 1 # Mark as active viewport if it's the main one
                viewport.dxf.id = 1 # Common ID for the first main viewport
                # viewport.dxf.layer = "VIEWPORTS" # Optional: put viewport on a specific layer
                # viewport.dxf.on = 1 # Viewport is on
                # viewport.dxf.view_target = view_center_ms # redundant if set in add_viewport
                # viewport.dxf.view_height = view_height_ms # redundant

                # Lock the viewport if specified
                if vp_detail_config.lock_viewport:
                    viewport.lock()

                self.logger.info(f"Main viewport created in layout '{layout_name}'. PS Center=({center_ps[0]},{center_ps[1]}), MS View Center=({view_center_ms[0]},{view_center_ms[1]}), MS View Height={view_height_ms:.2f}")
            else: # Older ezdxf syntax, might be needed for compatibility if ezdxf version is old
                self.logger.warning("Modern ps.add_viewport() not found. Viewport setup might be incomplete or use legacy methods.")
                # Example legacy (might not be perfectly analogous):
                # vp = doc.viewports.new('*Active') # This creates a VPORT table entry, not entity
                # ps.add_viewport_entity(...) if such method exists or direct entity creation

        except Exception as e:
            self.logger.error(f"Error creating main viewport: {e}", exc_info=True)
