"""Module for processing geometry in DXF files."""

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, GeometryCollection
import geopandas as gpd
from src.core.utils import log_debug, log_warning, log_error
from .utils import attach_custom_data
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
        log_debug(f"=== Starting polygon creation for layer {layer_name} ===")
        layer_properties = self.layer_manager.get_layer_properties(layer_name)
        log_debug(f"Full layer properties: {layer_properties}")
        
        entity_properties = layer_properties.get('entity', {})
        log_debug(f"Layer {layer_name} - Entity properties: {entity_properties}")
        
        # Prepare initial attributes
        dxfattribs = {
            'layer': layer_name,
            'closed': entity_properties.get('close', True),  # Default to True for polygons
        }
        
        # Add linetype scale to initial attributes if specified
        if 'linetypeScale' in entity_properties:
            try:
                ltscale = float(entity_properties['linetypeScale'])
                dxfattribs['ltscale'] = ltscale
                log_debug(f"Setting initial ltscale={ltscale} for layer {layer_name}")
            except (ValueError, TypeError) as e:
                log_warning(f"Invalid linetypeScale value for layer {layer_name}: {str(e)}")
        
        # Add linetype if specified
        if 'linetype' in entity_properties:
            dxfattribs['linetype'] = entity_properties['linetype']
            
        log_debug(f"Initial dxfattribs: {dxfattribs}")
        
        exterior_coords = list(geometry.exterior.coords)
        if len(exterior_coords) > 2:
            try:
                log_debug(f"Creating polyline with attributes: {dxfattribs}")
                polyline = msp.add_lwpolyline(exterior_coords, dxfattribs=dxfattribs)
                
                # Verify the linetype scale was set
                try:
                    actual_ltscale = polyline.dxf.ltscale
                    log_debug(f"Actual ltscale after creation: {actual_ltscale}")
                except Exception as e:
                    log_warning(f"Could not read ltscale after creation: {str(e)}")
                
                # Set linetype generation after creation
                if 'linetypeGeneration' in entity_properties:
                    try:
                        original_flags = polyline.dxf.flags
                        log_debug(f"Original flags: {original_flags}")
                        
                        if entity_properties['linetypeGeneration']:
                            polyline.dxf.flags |= LWPOLYLINE_PLINEGEN
                        else:
                            polyline.dxf.flags &= ~LWPOLYLINE_PLINEGEN
                        
                        new_flags = polyline.dxf.flags
                        log_debug(f"New flags after setting linetypeGeneration: {new_flags}")
                        log_debug(f"PLINEGEN bit is {'set' if new_flags & LWPOLYLINE_PLINEGEN else 'not set'}")
                    except Exception as e:
                        log_warning(f"Could not set linetype generation for polyline. Error: {str(e)}")
                
                # Set other entity properties
                try:
                    if 'color' in entity_properties:
                        polyline.dxf.color = entity_properties['color']
                    if 'lineweight' in entity_properties:
                        polyline.dxf.lineweight = entity_properties['lineweight']
                    if 'transparency' in entity_properties:
                        polyline.transparency = entity_properties['transparency']
                except Exception as e:
                    log_warning(f"Could not set some entity properties: {str(e)}")
                
                attach_custom_data(polyline, self.script_identifier, entity_name)
                
                # Final verification
                log_debug(f"=== Final polyline state ===")
                log_debug(f"ltscale: {getattr(polyline.dxf, 'ltscale', 'Not set')}")
                log_debug(f"flags: {getattr(polyline.dxf, 'flags', 'Not set')}")
                log_debug(f"layer: {getattr(polyline.dxf, 'layer', 'Not set')}")
                log_debug(f"color: {getattr(polyline.dxf, 'color', 'Not set')}")
                log_debug(f"lineweight: {getattr(polyline.dxf, 'lineweight', 'Not set')}")
                log_debug(f"linetype: {getattr(polyline.dxf, 'linetype', 'Not set')}")
                log_debug(f"=== End final state ===")
            except Exception as e:
                log_error(f"Error creating exterior polyline: {str(e)}")

            # Process interior rings
            for interior in geometry.interiors:
                try:
                    interior_coords = list(interior.coords)
                    if len(interior_coords) > 2:
                        log_debug(f"Creating interior polyline with attributes: {dxfattribs}")
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
                except Exception as e:
                    log_error(f"Error creating interior polyline: {str(e)}")
        
        log_debug(f"=== Completed polygon creation for layer {layer_name} ===\n")

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
