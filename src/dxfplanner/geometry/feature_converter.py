"""
Converts GeoFeature domain models to DxfEntity domain models.
"""
from typing import List, Any, Dict, Union, Optional, Tuple, AsyncIterator
from dxfplanner.core.logging_config import get_logger
from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import (
    GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPointGeo,
    MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo
)
from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfPoint, DxfLWPolyline, DxfHatch, DxfMText, DxfText, DxfInsert,
    DxfHatchPath, HatchEdgeType
)
import math

logger = get_logger(__name__)

DEFAULT_LAYER_NAME = "0" # Define at module level

async def convert_geo_feature_to_dxf_entities(
    geo_feature: GeoFeature,
    effective_style: Dict[str, Any],
    # NEW parameters:
    output_target_layer_name: Optional[str] = None,
    input_layer_name_for_context: Optional[str] = None,
    default_xdata_app_id: Optional[str] = "DXFPLANNER", # Match IGeometryTransformer
    default_xdata_tags: Optional[List[Tuple[int, Any]]] = None # Match IGeometryTransformer
) -> AsyncIterator[DxfEntity]: # Changed to AsyncIterator[DxfEntity]
    """
    Converts a GeoFeature (containing AnyGeoGeometry and properties) into a list
    of DxfEntity domain models based on the feature's geometry, properties,
    the effective style, and explicit layer overrides.

    Args:
        geo_feature: The input GeoFeature.
        effective_style: A dictionary of resolved style attributes from StyleService.
        output_target_layer_name: Explicit target layer name from pipeline. Takes highest precedence.
        input_layer_name_for_context: Name of the original input layer, used as a fallback.
        default_xdata_app_id: Default application ID for XDATA.
        default_xdata_tags: Default XDATA tags.


    Returns:
        A list of DxfEntity instances.
    """
    feature_geometry = geo_feature.geometry
    # Ensure feature_properties is always a dict, even if geo_feature.properties is None
    feature_properties = geo_feature.properties if geo_feature.properties is not None else {}


    if feature_geometry is None:
        logger.warning(f"GeoFeature ID '{geo_feature.id}' has no geometry. Skipping DxfEntity conversion.")
        return # In an async generator, return means stop iteration
        # yield from [] # Alternatively, to be explicit it's an empty async generator

    # Layer Determination Logic
    layer_from_style = effective_style.get("layer_name") # From StyleObjectConfig.layer.name via effective_style
    layer_from_feature_attr = feature_properties.get("layer")

    # Logging for debug - REMOVE OR MAKE DEBUG LEVEL LATER
    logger.info(
        f"FeatureConverter LayerCalc for Feature ID '{geo_feature.id}': "
        f"output_target_layer_name='{output_target_layer_name}', "
        f"layer_from_style='{layer_from_style}', "
        f"layer_from_feature_attr='{layer_from_feature_attr}', "
        f"input_layer_name_for_context='{input_layer_name_for_context}'"
    )

    current_dxf_entity_layer = output_target_layer_name or \
                               layer_from_style or \
                               layer_from_feature_attr or \
                               input_layer_name_for_context or \
                               DEFAULT_LAYER_NAME

    logger.info(f"FeatureConverter for Feature ID '{geo_feature.id}': Final effective layer: '{current_dxf_entity_layer}'")


    # Common style attributes (already extracted in effective_style, but can be re-referenced)
    # These are fine as they are, layer name is the main issue.
    aci_color = effective_style.get("color", 256) # Default to BYLAYER/BYBLOCK
    rgb_color_tuple = effective_style.get("rgb_color") # This is already a tuple (r,g,b) or None
    resolved_linetype = effective_style.get("linetype") # Already resolved or None
    resolved_lineweight = effective_style.get("lineweight", -1) # Default to default lineweight
    resolved_transparency = effective_style.get("transparency_value") # Already resolved or None
    # XDATA application ID and tags
    xdata_app_id = default_xdata_app_id # Use passed-in default
    xdata_tags = default_xdata_tags # Use passed-in default


    # Simplified: Use current_dxf_entity_layer for all entities created below.
    # Example for DxfPoint:
    if isinstance(feature_geometry, PointGeo):
        # ... (existing block/text handling logic based on effective_style and feature_properties)
        # Make sure to use current_dxf_entity_layer in DxfInsert, DxfMText, DxfText constructors.
        # For a plain DxfPoint:
        # Ensure existing logic for creating DxfInsert or DxfText from PointGeo is preserved
        # and updated to use `current_dxf_entity_layer`.

        # --- START REVISED PointGeo Handling ---
        block_name_from_style = effective_style.get("block_name")
        text_content_from_style = effective_style.get("text_content") # Used to identify text points
        is_label_feature = feature_properties.get("__geometry_type__") == "LABEL"

        if block_name_from_style:
            dxf_insert = DxfInsert(
                block_name=block_name_from_style,
                # ... other DxfInsert params from existing code ...
                position=feature_geometry.coordinates, # Use Coordinate object
                x_scale=effective_style.get("block_scale_x", 1.0),
                y_scale=effective_style.get("block_scale_y", 1.0),
                z_scale=effective_style.get("block_scale_z", 1.0),
                rotation=effective_style.get("block_rotation", 0.0),
                layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                true_color=rgb_color_tuple,
                color_256=aci_color,
                linetype=resolved_linetype,
                lineweight=resolved_lineweight,
                transparency=resolved_transparency,
                xdata_app_id=xdata_app_id,
                xdata_tags=xdata_tags
            )
            # dxf_entities.append(dxf_insert) # Changed
            yield dxf_insert
        elif is_label_feature or text_content_from_style: # Prioritize if it's marked as a label or style indicates text
            text_string = text_content_from_style or feature_properties.get("label_text", "Default Text")
            text_height = effective_style.get("text_height", 1.0)
            # Use label_rotation from feature_properties if available (e.g., from LabelPlacementService)
            text_rotation = feature_properties.get("label_rotation", effective_style.get("text_rotation", 0.0))
            text_style_name = effective_style.get("text_style_name", "Standard") # From StyleObjectConfig
            # MText specific from StyleObjectConfig's text_paragraph_props
            mtext_attachment_point = effective_style.get("mtext_attachment_point", 1) # Default to TopLeft
            mtext_width = effective_style.get("mtext_width") # Optional MText width
            mtext_line_spacing_factor = effective_style.get("mtext_line_spacing_factor") # Optional

            text_entity: Union[DxfMText, DxfText]
            if "\\P" in text_string or "\n" in text_string or mtext_width is not None:
                text_entity = DxfMText(
                    text=text_string,
                    insertion_point=feature_geometry.coordinates, # Use Coordinate object
                    height=text_height,
                    rotation=text_rotation,
                    style=text_style_name,
                    attachment_point=mtext_attachment_point,
                    width=mtext_width,
                    line_spacing_factor=mtext_line_spacing_factor,
                    layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                    true_color=rgb_color_tuple,
                    color_256=aci_color,
                    transparency=resolved_transparency,
                    xdata_app_id=xdata_app_id,
                    xdata_tags=xdata_tags
                )
            else: # Simple Text
                text_entity = DxfText(
                    text=text_string,
                    insertion_point=feature_geometry.coordinates, # Use Coordinate object
                    height=text_height,
                    rotation=text_rotation,
                    style=text_style_name,
                    layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                    true_color=rgb_color_tuple,
                    color_256=aci_color,
                    transparency=resolved_transparency,
                    xdata_app_id=xdata_app_id,
                    xdata_tags=xdata_tags
                )
            # dxf_entities.append(text_entity) # Changed
            yield text_entity
        else: # Default to DxfPoint if not a block or explicitly styled/marked as text
            dxf_point = DxfPoint(
                position=feature_geometry.coordinates,
                layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                true_color=rgb_color_tuple,
                color_256=aci_color,
                linetype=resolved_linetype,
                # lineweight, transparency not typically for POINT, but XDATA can be added
                xdata_app_id=xdata_app_id,
                xdata_tags=xdata_tags
            )
            # Corrected logging for DxfPoint creation
            logger.info(
                f"FeatureConverter: Created DxfPoint. Assigned Layer='{current_dxf_entity_layer}'. "
                f"Model Layer='{dxf_point.layer}'. Position=({dxf_point.position.x},{dxf_point.position.y})."
            )
            # dxf_entities.append(dxf_point) # Changed
            yield dxf_point
        # --- END REVISED PointGeo Handling ---

    elif isinstance(feature_geometry, PolylineGeo):
        # ... existing PolylineGeo logic ...
        # Update layer=current_dxf_entity_layer, xdata_app_id, xdata_tags
        points = feature_geometry.coordinates # This is already List[Coordinate]
        if len(points) >= 2:
            is_closed = False # Default to not closed unless specific conditions met
            if len(points) > 2: # A line or a point cannot be 'closed' in the typical polyline sense
                 # Compare first and last Coordinate objects if they exist and list has enough points
                if points[0].x == points[-1].x and \
                   points[0].y == points[-1].y and \
                   (points[0].z == points[-1].z if points[0].z is not None and points[-1].z is not None else points[0].z is None and points[-1].z is None):
                    is_closed = True

            dxf_lwpolyline = DxfLWPolyline(
                points=points, # List of (x,y,z) tuples
                closed=is_closed,
                layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                true_color=rgb_color_tuple,
                color_256=aci_color,
                linetype=resolved_linetype,
                lineweight=resolved_lineweight,
                transparency=resolved_transparency,
                xdata_app_id=xdata_app_id,
                xdata_tags=xdata_tags
            )
            # dxf_entities.append(dxf_lwpolyline) # Changed
            yield dxf_lwpolyline
        else:
            logger.warning(f"PolylineGeo for feature ID '{geo_feature.id}' has < 2 points. Skipping.")


    elif isinstance(feature_geometry, PolygonGeo):
        # ... existing PolygonGeo logic ...
        # Update layer=current_dxf_entity_layer for DxfHatch and boundary DxfLWPolyline
        # Update xdata_app_id, xdata_tags for DxfHatch and boundary DxfLWPolyline

        hatch_pattern_name = effective_style.get("hatch_pattern_name")
        # hatch_pattern_type from effective_style if available (e.g. predefined, custom)
        hatch_scale = effective_style.get("hatch_scale", 1.0)
        hatch_angle = effective_style.get("hatch_angle", 0.0)
        # hatch_solid_fill from effective_style (bool)
        # hatch_associative from effective_style (bool)
        # hatch_style (normal, outer, ignore) from effective_style

        draw_hatch_boundary = effective_style.get("draw_hatch_boundary", True)
        all_rings_coords = feature_geometry.coordinates # List of List of Coordinate

        if not all_rings_coords or not all_rings_coords[0]:
            logger.warning(f"PolygonGeo for feature ID '{geo_feature.id}' has no exterior ring. Skipping.")
            return # Return from async generator
            # yield from []

        boundary_paths_data: List[DxfHatchPath] = []

        # Exterior ring
        exterior_ring_domain_coords = all_rings_coords[0]
        if len(exterior_ring_domain_coords) >= 3:
            # For DxfHatchPath, only XY is typically used by ezdxf for polyline paths.
            # Ensure closed for hatch path by checking/appending first point if needed.
            exterior_hatch_path_vertices = [Coordinate(x=c.x, y=c.y) for c in exterior_ring_domain_coords]
            if exterior_hatch_path_vertices[0].x != exterior_hatch_path_vertices[-1].x or \
               exterior_hatch_path_vertices[0].y != exterior_hatch_path_vertices[-1].y: # Compare Coordinate objects
                exterior_hatch_path_vertices.append(exterior_hatch_path_vertices[0])
            boundary_paths_data.append(DxfHatchPath(vertices=exterior_hatch_path_vertices, is_closed=True)) # Explicitly set is_closed

            # Interior rings (holes)
            if len(all_rings_coords) > 1:
                for interior_ring_domain_coords in all_rings_coords[1:]:
                    if len(interior_ring_domain_coords) >= 3:
                        interior_hatch_path_vertices = [Coordinate(x=c.x, y=c.y) for c in interior_ring_domain_coords]
                        if interior_hatch_path_vertices[0].x != interior_hatch_path_vertices[-1].x or \
                           interior_hatch_path_vertices[0].y != interior_hatch_path_vertices[-1].y: # Compare Coordinate objects
                            interior_hatch_path_vertices.append(interior_hatch_path_vertices[0])
                        boundary_paths_data.append(DxfHatchPath(vertices=interior_hatch_path_vertices, is_closed=True)) # Explicitly set is_closed
                    else:
                        logger.warning(f"PolygonGeo interior ring for feature ID '{geo_feature.id}' has < 3 points. Skipping this hole.")
        else:
            logger.warning(f"PolygonGeo exterior ring for feature ID '{geo_feature.id}' has < 3 points. Cannot create HATCH or boundary.")
            # If we can't form a valid exterior, we might not want to draw anything.
            # Depending on requirements, one might still draw the boundary if draw_hatch_boundary is true,
            # even if the hatch itself cannot be created. For now, let's assume if exterior is bad, skip all.
            return # Return from async generator
            # yield from []

        if not boundary_paths_data:
            logger.warning(f"PolygonGeo for feature ID '{geo_feature.id}' resulted in no valid boundary paths. Skipping hatch.")

        if hatch_pattern_name and boundary_paths_data: # Only add hatch if pattern and valid paths exist
            # Extract hatch specific props from effective_style
            hatch_props = DxfHatch.HatchProperties(
                pattern_name=hatch_pattern_name,
                scale=hatch_scale,
                angle=hatch_angle,
                # TODO: Add other DxfHatch.HatchProperties from effective_style if defined there
                # e.g., definition_file, solid_fill, associative, style (normal, outer, ignore)
            )
            dxf_hatch = DxfHatch(
                boundary_paths=boundary_paths_data,
                hatch_props=hatch_props,
                layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                true_color=rgb_color_tuple, # Hatch color usually from pattern or layer
                color_256=aci_color,
                transparency=resolved_transparency,
                xdata_app_id=xdata_app_id,
                xdata_tags=xdata_tags
            )
            # dxf_entities.append(dxf_hatch) # Changed
            yield dxf_hatch

        if draw_hatch_boundary and boundary_paths_data: # Check boundary_paths_data again as it confirms valid exterior
            # Use the first path (exterior) for drawing the boundary LWPolyline
            # DxfHatchPath stores (x,y) tuples, LWPolyline needs (x,y,z)
            # We need the original exterior_ring_domain_coords for Z values.
            exterior_points_for_lw = exterior_ring_domain_coords # This is already List[Coordinate]

            # LWPolyline must be closed if it represents a polygon boundary
            # The DxfHatchPath vertices are already ensured to be closed if they were polyline type.
            # For LWPolyline, ezdxf handles closure based on the `closed` flag.
            # It's generally better to provide the points without explicit duplication for closure
            # and let `closed=True` handle it, but ezdxf is robust.
            # Let's ensure the input list for DxfLWPolyline isn't doubly closed if it came from closed hatch path.
            # For simplicity, use the original list and set closed=True.
            # If exterior_ring_domain_coords was [P1,P2,P3,P1], then exterior_points_for_lw = [(x1,y1,z1), (x2,y2,z2), (x3,y3,z3), (x1,y1,z1)]
            # DxfLWPolyline with closed=True will correctly handle this.

            is_closed_lw = True # Polygon boundaries are closed
            dxf_boundary_lwpolyline = DxfLWPolyline(
                points=exterior_points_for_lw,
                closed=is_closed_lw,
                layer=current_dxf_entity_layer, # USE RESOLVED LAYER
                true_color=rgb_color_tuple,
                color_256=aci_color,
                linetype=resolved_linetype,
                lineweight=resolved_lineweight,
                transparency=resolved_transparency,
                xdata_app_id=xdata_app_id,
                xdata_tags=xdata_tags
            )
            # dxf_entities.append(dxf_boundary_lwpolyline) # Changed
            yield dxf_boundary_lwpolyline


    elif isinstance(feature_geometry, (MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo)):
        # ... existing multi-geometry logic ...
        # Update recursive call to include new parameters.
        geoms_to_process: List[GeoFeature] = []
        # Unpack multi-geometries into a list of GeoFeatures with single part geometries
        if isinstance(feature_geometry, MultiPointGeo):
            for coord in feature_geometry.coordinates: # List of Coordinate
                geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_mpt_{len(geoms_to_process)}", geometry=PointGeo(coordinates=coord), properties=feature_properties))
        elif isinstance(feature_geometry, MultiPolylineGeo):
            for coord_list in feature_geometry.coordinates: # List of List of Coordinate
                geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_mpl_{len(geoms_to_process)}", geometry=PolylineGeo(coordinates=coord_list), properties=feature_properties))
        elif isinstance(feature_geometry, MultiPolygonGeo):
             for poly_coord_rings in feature_geometry.coordinates: # List of List of List of Coordinate
                geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_mpg_{len(geoms_to_process)}", geometry=PolygonGeo(coordinates=poly_coord_rings), properties=feature_properties))
        elif isinstance(feature_geometry, GeometryCollectionGeo):
             for i, part_geom in enumerate(feature_geometry.geometries): # List of AnyGeoGeometry
                 geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_gc{i}", geometry=part_geom, properties=feature_properties))

        for part_feature in geoms_to_process:
            # Recursive call with ALL necessary parameters
            # dxf_entities.extend(convert_geo_feature_to_dxf_entities( # Changed
            async for part_entity in convert_geo_feature_to_dxf_entities( # Now async for
                geo_feature=part_feature,
                effective_style=effective_style, # Pass the same resolved style
                output_target_layer_name=output_target_layer_name, # Pass down
                input_layer_name_for_context=input_layer_name_for_context, # Pass down
                default_xdata_app_id=default_xdata_app_id, # Pass down
                default_xdata_tags=default_xdata_tags # Pass down
            ):
                yield part_entity # Yield from the async generator

    else:
        logger.warning(f"Unsupported AnyGeoGeometry type: {type(feature_geometry).__name__} for feature ID '{geo_feature.id}'")

    # Remove the old logging block that was misplaced by the apply model previously
    # The new logging is at the top of the function for layer calculation,
    # and specific entity creation logs (like for DxfPoint) are within their respective blocks.
