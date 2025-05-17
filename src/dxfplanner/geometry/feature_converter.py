"""
Converts GeoFeature domain models to DxfEntity domain models.
"""
from typing import List, Any, Dict, Union
from dxfplanner.core.logging_config import get_logger
from dxfplanner.domain.models.geo_models import (
    GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPointGeo,
    MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo
)
from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfPoint, DxfLWPolyline, DxfHatch, DxfMText, DxfText, DxfInsert,
    DxfHatchPath, HatchEdgeType
)

logger = get_logger(__name__)

def convert_geo_feature_to_dxf_entities(
    geo_feature: GeoFeature,
    effective_style: Dict[str, Any]
) -> List[DxfEntity]:
    """
    Converts a GeoFeature (containing AnyGeoGeometry and properties) into a list
    of DxfEntity domain models based on the feature's geometry, properties, and
    the effective style.

    Args:
        geo_feature: The input GeoFeature.
        effective_style: A dictionary of resolved style attributes.

    Returns:
        A list of DxfEntity instances.
    """
    dxf_entities: List[DxfEntity] = []
    feature_geometry = geo_feature.geometry
    feature_properties = geo_feature.properties if geo_feature.properties else {}

    if feature_geometry is None:
        logger.warning(f"GeoFeature ID '{geo_feature.id}' has no geometry. Skipping DxfEntity conversion.")
        return dxf_entities

    layer_name = effective_style.get("layer_name", "0")
    aci_color = effective_style.get("color", 256)
    rgb_color = effective_style.get("rgb_color")
    linetype = effective_style.get("linetype")
    lineweight = effective_style.get("lineweight", -1)
    transparency_val = effective_style.get("transparency_value")

    block_name_from_style = effective_style.get("block_name")
    text_content_from_style = effective_style.get("text_content")

    if isinstance(feature_geometry, PointGeo):
        if block_name_from_style:
            dxf_insert = DxfInsert(
                block_name=block_name_from_style,
                insert_x=feature_geometry.coordinates.x,
                insert_y=feature_geometry.coordinates.y,
                insert_z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
                x_scale=effective_style.get("block_scale_x", 1.0),
                y_scale=effective_style.get("block_scale_y", 1.0),
                z_scale=effective_style.get("block_scale_z", 1.0),
                rotation=effective_style.get("block_rotation", 0.0),
                layer=layer_name, color=aci_color, rgb=rgb_color, linetype=linetype,
                lineweight=lineweight, transparency=transparency_val
            )
            dxf_entities.append(dxf_insert)
            return dxf_entities
        elif feature_properties.get("__geometry_type__") == "LABEL" or text_content_from_style:
            text_string = text_content_from_style or feature_properties.get("label_text", "Default Text")
            text_height = effective_style.get("text_height", 1.0)
            text_rotation = feature_properties.get("label_rotation", effective_style.get("text_rotation", 0.0))
            text_style_name = effective_style.get("text_style_name", "Standard")
            attachment_point = effective_style.get("mtext_attachment_point", 1)
            width = effective_style.get("mtext_width")
            text_entity: Union[DxfMText, DxfText]
            if "\\P" in text_string or "\n" in text_string or width is not None:
                text_entity = DxfMText(
                    text=text_string, insert_x=feature_geometry.coordinates.x, insert_y=feature_geometry.coordinates.y,
                    insert_z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
                    height=text_height, rotation=text_rotation, style=text_style_name,
                    attachment_point=attachment_point, width=width, layer=layer_name, color=aci_color,
                    rgb=rgb_color, transparency=transparency_val )
            else:
                text_entity = DxfText(
                    text=text_string, insert_x=feature_geometry.coordinates.x, insert_y=feature_geometry.coordinates.y,
                    insert_z=feature_geometry.coordinates.z if feature_geometry.coordinates.z is not None else 0.0,
                    height=text_height, rotation=text_rotation, style=text_style_name, layer=layer_name,
                    color=aci_color, rgb=rgb_color, transparency=transparency_val )
            dxf_entities.append(text_entity)
            return dxf_entities

    if isinstance(feature_geometry, PointGeo):
        dxf_point = DxfPoint(
            position=feature_geometry.coordinates,
            layer=layer_name,
            color=aci_color,
            rgb=rgb_color,
            linetype=linetype
        )
        dxf_entities.append(dxf_point)
    elif isinstance(feature_geometry, PolylineGeo):
        points = [(c.x, c.y, c.z if c.z is not None else 0.0) for c in feature_geometry.coordinates]
        if len(points) >= 2:
            is_closed = (len(points) > 2 and points[0] == points[-1])
            dxf_entities.append(DxfLWPolyline(
                points=points, closed=is_closed, layer=layer_name, color=aci_color, rgb=rgb_color,
                linetype=linetype, lineweight=lineweight, transparency=transparency_val ))
        else:
            logger.warning(f"PolylineGeo for feature ID '{geo_feature.id}' has < 2 points.")
    elif isinstance(feature_geometry, PolygonGeo):
        hatch_pattern_name = effective_style.get("hatch_pattern_name")
        draw_hatch_boundary = effective_style.get("draw_hatch_boundary", True)
        all_rings_coords = feature_geometry.coordinates
        if not all_rings_coords or not all_rings_coords[0]:
            logger.warning(f"PolygonGeo for feature ID '{geo_feature.id}' has no exterior ring.")
            return dxf_entities
        boundary_paths_data: List[DxfHatchPath] = []
        exterior_ring_coords = [(c.x, c.y) for c in all_rings_coords[0]]
        if len(exterior_ring_coords) >= 3:
            if exterior_ring_coords[0] != exterior_ring_coords[-1]: exterior_ring_coords.append(exterior_ring_coords[0])
            boundary_paths_data.append(DxfHatchPath(vertices=exterior_ring_coords, type=HatchEdgeType.POLYLINE.value))
            if len(all_rings_coords) > 1:
                for interior_ring_domain_coords in all_rings_coords[1:]:
                    interior_ring_shapely_coords = [(c.x, c.y) for c in interior_ring_domain_coords]
                    if len(interior_ring_shapely_coords) >= 3:
                        if interior_ring_shapely_coords[0] != interior_ring_shapely_coords[-1]: interior_ring_shapely_coords.append(interior_ring_shapely_coords[0])
                        boundary_paths_data.append(DxfHatchPath(vertices=interior_ring_shapely_coords, type=HatchEdgeType.POLYLINE.value))
        else:
            logger.warning(f"PolygonGeo exterior for '{geo_feature.id}' has < 3 points.")

        if hatch_pattern_name and boundary_paths_data:
            dxf_entities.append(DxfHatch(
                pattern_name=hatch_pattern_name, scale=effective_style.get("hatch_scale", 1.0),
                angle=effective_style.get("hatch_angle", 0.0), boundary_paths=boundary_paths_data,
                layer=layer_name, color=aci_color, rgb=rgb_color, transparency=transparency_val ))
        if draw_hatch_boundary and all_rings_coords and all_rings_coords[0] and len(all_rings_coords[0]) >=2 :
            exterior_points_for_lw = [(c.x, c.y, c.z if c.z is not None else 0.0) for c in all_rings_coords[0]]
            is_closed_lw = (len(exterior_points_for_lw) > 2 and exterior_points_for_lw[0] == exterior_points_for_lw[-1])
            dxf_entities.append(DxfLWPolyline(
                points=exterior_points_for_lw, closed=is_closed_lw, layer=layer_name, color=aci_color,
                rgb=rgb_color, linetype=linetype, lineweight=lineweight, transparency=transparency_val ))
    elif isinstance(feature_geometry, (MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo)):
        geoms_to_process: List[GeoFeature] = []
        if isinstance(feature_geometry, MultiPointGeo):
            for coord in feature_geometry.coordinates:
                geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_mpt", geometry=PointGeo(coordinates=coord), properties=feature_properties))
        elif isinstance(feature_geometry, MultiPolylineGeo):
            for coord_list in feature_geometry.coordinates:
                geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_mpl", geometry=PolylineGeo(coordinates=coord_list), properties=feature_properties))
        elif isinstance(feature_geometry, MultiPolygonGeo):
             for poly_coord_rings in feature_geometry.coordinates:
                geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_mpg", geometry=PolygonGeo(coordinates=poly_coord_rings), properties=feature_properties))
        elif isinstance(feature_geometry, GeometryCollectionGeo):
             for i, part_geom in enumerate(feature_geometry.geometries):
                 geoms_to_process.append(GeoFeature(id=f"{geo_feature.id}_gc{i}", geometry=part_geom, properties=feature_properties))
        for part_feature in geoms_to_process:
            dxf_entities.extend(convert_geo_feature_to_dxf_entities(part_feature, effective_style)) # Recursive call
    else:
        logger.warning(f"Unsupported AnyGeoGeometry type: {type(feature_geometry).__name__} for feature ID '{geo_feature.id}'")
    return dxf_entities
