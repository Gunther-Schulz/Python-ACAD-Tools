"""Module for processing geometry in DXF files."""

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, GeometryCollection
import geopandas as gpd
from src.core.utils import log_debug, log_warning
from src.dxf_utils import attach_custom_data, get_color_code, convert_transparency
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN

class GeometryProcessor:
    def __init__(self, script_identifier, project_loader, style_manager, layer_manager):
        self.project_loader = project_loader
        self.style_manager = style_manager
        self.layer_manager = layer_manager
        self.script_identifier = script_identifier

    def add_geometries_to_dxf(self, msp, geo_data, layer_name):
        """Add geometries to DXF modelspace"""
        log_debug(f"Adding geometries to DXF for layer: {layer_name}")
        
        # Check if this is a hatch layer that references other geometries
        layer_info = self.layer_manager.all_layers.get(layer_name, {})
        if 'hatchGeometry' in layer_info:
            log_debug(f"Converting hatchGeometry to hatches format for layer {layer_name}")
            # Convert hatchGeometry to hatches format
            referenced_layers = layer_info['hatchGeometry'].get('layers', [])
            if referenced_layers:
                # Create a hatches entry in the layer info
                if 'hatches' not in layer_info:
                    layer_info['hatches'] = []
                # Add a hatch configuration that references the source layer
                for ref_layer in referenced_layers:
                    hatch_info = {
                        'name': layer_name,
                        'style': layer_info.get('style'),
                        'updateDxf': layer_info.get('updateDxf', True)
                    }
                    layer_info['hatches'].append(hatch_info)
                    
                    # Get the referenced layer's geometry
                    ref_geo_data = self.project_loader.get_layer_geometry(ref_layer)
                    if ref_geo_data is not None:
                        # Process the geometry using the standard hatches mechanism
                        if isinstance(ref_geo_data, gpd.GeoDataFrame):
                            self._process_geometry_hatches(msp, ref_geo_data.geometry, layer_info)
                        elif isinstance(ref_geo_data, gpd.GeoSeries):
                            self._process_geometry_hatches(msp, ref_geo_data, layer_info)
            return

        if geo_data is None:
            log_debug(f"No geometry data available for layer: {layer_name}")
            return

        if isinstance(geo_data, gpd.GeoDataFrame):
            # Check if this is a label layer from labelAssociation operation
            if 'label' in geo_data.columns and 'rotation' in geo_data.columns:
                return
            geometries = geo_data.geometry
        elif isinstance(geo_data, gpd.GeoSeries):
            geometries = geo_data
        else:
            log_warning(f"Unexpected data type for layer {layer_name}: {type(geo_data)}")
            return

        log_debug(f"add_geometries_to_dxf Layer Name: {layer_name}")
        
        # First process all geometries
        for geometry in geometries:
            if isinstance(geometry, Polygon):
                self.add_polygon_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, MultiPolygon):
                for polygon in geometry.geoms:
                    self.add_polygon_to_dxf(msp, polygon, layer_name)
            elif isinstance(geometry, LineString):
                self.add_linestring_to_dxf(msp, geometry, layer_name)
            elif isinstance(geometry, MultiLineString):
                for line in geometry.geoms:
                    self.add_linestring_to_dxf(msp, line, layer_name)
            else:
                self.add_geometry_to_dxf(msp, geometry, layer_name)
        
        # Then process hatches after all geometries are added
        if 'hatches' in layer_info:
            self._process_geometry_hatches(msp, geometries, layer_info)

    def _process_geometry_hatches(self, msp, geometries, layer_info):
        """Process hatches for a collection of geometries"""
        if 'hatches' not in layer_info:
            return
            
        for geometry in geometries:
            if isinstance(geometry, Polygon):
                self._create_hatches_for_geometry(msp, geometry, layer_info)
            elif isinstance(geometry, MultiPolygon):
                for polygon in geometry.geoms:
                    self._create_hatches_for_geometry(msp, polygon, layer_info)

    def _create_hatches_for_geometry(self, msp, geometry, layer_info):
        """Create hatches for a single geometry"""
        if 'hatches' not in layer_info:
            return
            
        for hatch_info in layer_info['hatches']:
            hatch_layer_name = hatch_info['name']
            
            # Create hatch entity with BYLAYER color (256)
            hatch = msp.add_hatch()
            hatch.dxf.color = 256  # BYLAYER
            hatch.dxf.layer = hatch_layer_name
            
            # Add the boundary paths
            # Add exterior boundary
            exterior_coords = list(geometry.exterior.coords)
            if len(exterior_coords) > 2:
                hatch.paths.add_polyline_path(exterior_coords, is_closed=True)
            
            # Add interior boundaries
            for interior in geometry.interiors:
                interior_coords = list(interior.coords)
                if len(interior_coords) > 2:
                    hatch.paths.add_polyline_path(interior_coords, is_closed=True)
            
            # Apply hatch settings from style
            if 'style' in hatch_info:
                style, warning = self.style_manager.get_style(hatch_info['style'])
                if style and 'hatch' in style:
                    hatch_props = style['hatch']
                    if 'pattern' in hatch_props:
                        try:
                            scale = float(hatch_props.get('scale', 1.0))
                            hatch.set_pattern_fill(hatch_props['pattern'], scale=scale)
                            if hatch_props.get('individual_hatches', False):
                                hatch.dxf.solid_fill = 0
                        except Exception as e:
                            log_warning(f"Failed to set pattern '{hatch_props['pattern']}': {str(e)}")
            
            attach_custom_data(hatch, self.script_identifier)

    def add_polygon_to_dxf(self, msp, geometry, layer_name, entity_name=None):
        """Add a polygon geometry to DXF"""
        layer_properties = self.layer_manager.get_layer_properties(layer_name)
        entity_properties = layer_properties.get('entity', {})
        
        # Prepare initial attributes
        dxfattribs = {
            'layer': layer_name,
            'closed': entity_properties.get('close', True),  # Default to True for polygons
        }
        
        # Add linetype scale to initial attributes
        if 'linetypeScale' in entity_properties:
            dxfattribs['ltscale'] = float(entity_properties['linetypeScale'])
        
        # Create the main polyline
        exterior_coords = list(geometry.exterior.coords)
        if len(exterior_coords) > 2:
            polyline = msp.add_lwpolyline(exterior_coords, dxfattribs=dxfattribs)
            
            # Set linetype generation after creation
            if 'linetypeGeneration' in entity_properties:
                try:
                    if entity_properties['linetypeGeneration']:
                        polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                    else:
                        polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
                except Exception as e:
                    log_warning(f"Could not set linetype generation for polyline. Error: {str(e)}")
            
            attach_custom_data(polyline, self.script_identifier, entity_name)
            msp.last_geometry = polyline

        # Add interior rings
        for interior in geometry.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) > 2:
                polyline = msp.add_lwpolyline(interior_coords, dxfattribs=dxfattribs)
                
                # Set linetype generation after creation
                if 'linetypeGeneration' in entity_properties:
                    try:
                        if entity_properties['linetypeGeneration']:
                            polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                        else:
                            polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
                    except Exception as e:
                        log_warning(f"Could not set linetype generation for interior polyline. Error: {str(e)}")
                
                attach_custom_data(polyline, self.script_identifier, entity_name)

    def add_linestring_to_dxf(self, msp, geometry, layer_name):
        """Add a LineString geometry to DXF"""
        coords = list(geometry.coords)
        if not coords:
            return

        layer_properties = self.layer_manager.get_layer_properties(layer_name)
        entity_properties = layer_properties.get('entity', {})
        
        dxfattribs = {
            'layer': layer_name,
            'closed': entity_properties.get('close', False),  # Default to False for LineStrings
        }

        # Add linetype scale to initial attributes
        if 'linetypeScale' in entity_properties:
            dxfattribs['ltscale'] = float(entity_properties['linetypeScale'])
        
        # Create polyline
        polyline = msp.add_lwpolyline(coords, dxfattribs=dxfattribs)
        
        # Set linetype generation after creation
        if 'linetypeGeneration' in entity_properties:
            try:
                if entity_properties['linetypeGeneration']:
                    polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                else:
                    polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
            except Exception as e:
                log_warning(f"Could not set linetype generation for polyline. Error: {str(e)}")
        
        attach_custom_data(polyline, self.script_identifier)

    def add_point_to_dxf(self, msp, point, layer_name, entity_name=None):
        """Add a point geometry to DXF"""
        try:
            # Get point coordinates
            x, y = point.x, point.y
            
            # Create a POINT entity
            point_entity = msp.add_point(
                (x, y),
                dxfattribs={
                    'layer': layer_name,
                }
            )
            
            # Attach custom data
            attach_custom_data(point_entity, self.script_identifier, entity_name)
            
            log_debug(f"Added point at ({x}, {y}) to layer {layer_name}")
            
        except Exception as e:
            log_warning(f"Error adding point to layer {layer_name}: {str(e)}")

    def add_geometry_to_dxf(self, msp, geometry, layer_name, entity_name=None):
        """Add any geometry type to DXF"""
        if isinstance(geometry, (Polygon, MultiPolygon)):
            self.add_polygon_to_dxf(msp, geometry, layer_name, entity_name)
        elif isinstance(geometry, LineString):
            self.add_linestring_to_dxf(msp, geometry, layer_name)
        elif isinstance(geometry, MultiLineString):
            for line in geometry.geoms:
                self.add_linestring_to_dxf(msp, line, layer_name, entity_name)
        elif isinstance(geometry, Point):
            self.add_point_to_dxf(msp, geometry, layer_name, entity_name)
        elif isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                self.add_geometry_to_dxf(msp, geom, layer_name, entity_name)
        else:
            log_warning(f"Unsupported geometry type for layer {layer_name}: {type(geometry)}")

    def get_geometry_centroid(self, geometry):
        """Get the centroid of any geometry type"""
        if isinstance(geometry, (Polygon, MultiPolygon)):
            return geometry.centroid
        elif isinstance(geometry, (LineString, MultiLineString)):
            return geometry.interpolate(0.5, normalized=True)
        elif isinstance(geometry, Point):
            return geometry
        elif isinstance(geometry, GeometryCollection):
            # For GeometryCollection, we'll use the centroid of the first geometry
            if len(geometry.geoms) > 0:
                return self.get_geometry_centroid(geometry.geoms[0])
        return None

    def _create_hatch_from_geometry(self, msp, geometry, layer_name):
        """Create a hatch entity from a geometry"""
        log_debug(f"Creating hatch in layer {layer_name}")
        
        # Create hatch entity
        hatch = msp.add_hatch(color=1)  # Default color, will be overridden by layer
        hatch.dxf.layer = layer_name
        
        # Add the boundary paths
        # Add exterior boundary
        exterior_coords = list(geometry.exterior.coords)
        if len(exterior_coords) > 2:
            hatch.paths.add_polyline_path(exterior_coords, is_closed=True)
            log_debug(f"Added exterior boundary with {len(exterior_coords)} points")
        
        # Add interior boundaries
        for interior in geometry.interiors:
            interior_coords = list(interior.coords)
            if len(interior_coords) > 2:
                hatch.paths.add_polyline_path(interior_coords, is_closed=True)
                log_debug(f"Added interior boundary with {len(interior_coords)} points")
        
        # Get and apply hatch properties from style
        hatch_properties = self.layer_manager.get_layer_properties(layer_name)
        if hatch_properties and 'layer' in hatch_properties:
            hatch_props = hatch_properties['layer']
            log_debug(f"Applying hatch properties: {hatch_props}")
            
            if 'pattern' in hatch_props:
                hatch.pattern_name = hatch_props['pattern']
                log_debug(f"Set hatch pattern to {hatch_props['pattern']}")
            if 'scale' in hatch_props:
                hatch.dxf.pattern_scale = hatch_props['scale']
                log_debug(f"Set hatch scale to {hatch_props['scale']}")
            if 'color' in hatch_props:
                color = get_color_code(hatch_props['color'], self.layer_manager.name_to_aci)
                if isinstance(color, tuple):
                    hatch.rgb = color
                else:
                    hatch.dxf.color = color
                log_debug(f"Set hatch color to {color}")
            if 'transparency' in hatch_props:
                transparency = convert_transparency(hatch_props['transparency'])
                if transparency is not None:
                    hatch.transparency = transparency
                    log_debug(f"Set hatch transparency to {transparency}")
        else:
            log_warning(f"No hatch properties found for layer {layer_name}")
        
        attach_custom_data(hatch, self.script_identifier)
        log_debug(f"Completed hatch creation for layer {layer_name}")
