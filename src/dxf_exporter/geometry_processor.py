"""Module for processing geometry in DXF files."""

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, GeometryCollection
import geopandas as gpd
from src.core.utils import log_debug, log_warning
from .utils import attach_custom_data, get_color_code, convert_transparency
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

        # Get layer info to check for hatches
        layer_info = self.layer_manager.all_layers.get(layer_name, {})
        if 'hatches' in layer_info:
            for hatch_info in layer_info['hatches']:
                hatch_layer_name = hatch_info['name']
                
                # Create hatch entity
                hatch = msp.add_hatch(color=1)  # Default color, will be overridden by layer
                hatch.dxf.layer = hatch_layer_name
                
                # Add the boundary paths
                # Add exterior boundary
                if len(exterior_coords) > 2:
                    hatch.paths.add_polyline_path(exterior_coords, is_closed=True)
                
                # Add interior boundaries
                for interior in geometry.interiors:
                    interior_coords = list(interior.coords)
                    if len(interior_coords) > 2:
                        hatch.paths.add_polyline_path(interior_coords, is_closed=True)
                
                # Get and apply hatch properties from style
                hatch_properties = self.layer_manager.get_layer_properties(hatch_layer_name)
                if hatch_properties and 'layer' in hatch_properties:
                    hatch_props = hatch_properties['layer']
                    if 'pattern' in hatch_props:
                        hatch.pattern_name = hatch_props['pattern']
                    if 'scale' in hatch_props:
                        hatch.dxf.pattern_scale = hatch_props['scale']
                    if 'color' in hatch_props:
                        color = get_color_code(hatch_props['color'], self.layer_manager.name_to_aci)
                        if isinstance(color, tuple):
                            hatch.rgb = color
                        else:
                            hatch.dxf.color = color
                    if 'transparency' in hatch_props:
                        transparency = convert_transparency(hatch_props['transparency'])
                        if transparency is not None:
                            hatch.transparency = transparency
                
                attach_custom_data(hatch, self.script_identifier, entity_name)

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
