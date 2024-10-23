from src.project_loader import ProjectLoader
import geopandas as gpd
from matplotlib import pyplot as plt
from shapely import LinearRing
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from shapely.ops import unary_union
from shapely.validation import make_valid, explain_validity
from src.utils import log_info, log_warning, log_error
import pandas as pd
from geopandas import GeoSeries
import re
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
import traceback

from src.operations.common_operations import *
from src.project_loader import ProjectLoader
from shapely.ops import unary_union, linemerge
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from src.utils import log_info, log_warning
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from src.utils import log_info, log_warning, log_error



def _get_filtered_geometry(all_layers, project_settings, crs, layer_name, values):
        if layer_name not in all_layers:
            log_warning(f"Layer '{layer_name}' not found")
            return None

        source_gdf = all_layers[layer_name]
        log_info(f"Initial number of geometries in {layer_name}: {len(source_gdf)}")

        if values:
            label_column = next((l['label'] for l in project_settings['geomLayers'] if l['name'] == layer_name), None)
            if label_column and label_column in source_gdf.columns:
                filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(values)].copy()
                log_info(f"Number of geometries after filtering by values: {len(filtered_gdf)}")
            else:
                log_warning(f"Label column '{label_column}' not found in layer '{layer_name}'")
                return None
        else:
            filtered_gdf = source_gdf.copy()

        # Check validity of original geometries
        invalid_geoms = filtered_gdf[~filtered_gdf.geometry.is_valid]
        if not invalid_geoms.empty:
            log_warning(f"Found {len(invalid_geoms)} invalid geometries in layer '{layer_name}'")
            
            # Plot the layer with invalid points marked
            fig, ax = plt.subplots(figsize=(12, 8))
            filtered_gdf.plot(ax=ax, color='blue', alpha=0.5)
            
            for idx, geom in invalid_geoms.geometry.items():
                reason = explain_validity(geom)
                log_warning(f"Invalid geometry at index {idx}: {reason}")
                
                # Extract coordinates of invalid points
                coords = _extract_coords_from_reason(reason)
                if coords:
                    ax.plot(coords[0], coords[1], 'rx', markersize=10, markeredgewidth=2)
                    ax.annotate(f"Invalid point", (coords[0], coords[1]), xytext=(5, 5), 
                                textcoords='offset points', color='red', fontsize=8)
                else:
                    log_warning(f"Could not extract coordinates from reason: {reason}")
            
            # Add some buffer to the plot extent
            x_min, y_min, x_max, y_max = filtered_gdf.total_bounds
            ax.set_xlim(x_min - 10, x_max + 10)
            ax.set_ylim(y_min - 10, y_max + 10)
            
            plt.title(f"Layer: {layer_name} - Invalid Points Marked")
            plt.axis('equal')
            plt.tight_layout()
            plt.savefig(f"invalid_geometries_{layer_name}.png", dpi=300)
            plt.close()

            log_info(f"Plot saved as invalid_geometries_{layer_name}.png")

        # Attempt to fix invalid geometries
        def fix_geometry(geom):
            if geom.is_valid:
                return geom
            try:
                valid_geom = make_valid(geom)
                if isinstance(valid_geom, (MultiPolygon, Polygon, LineString, MultiLineString)):
                    return valid_geom
                elif isinstance(valid_geom, GeometryCollection):
                    valid_parts = [g for g in valid_geom.geoms if isinstance(g, (Polygon, MultiPolygon, LineString, MultiLineString))]
                    if valid_parts:
                        return GeometryCollection(valid_parts)
                log_warning(f"Unable to fix geometry: {valid_geom.geom_type}")
                return None
            except Exception as e:
                log_warning(f"Error fixing geometry: {e}")
                return None

        filtered_gdf['geometry'] = filtered_gdf['geometry'].apply(fix_geometry)
        filtered_gdf = filtered_gdf[filtered_gdf['geometry'].notna()]
        log_info(f"Number of valid geometries after fixing: {len(filtered_gdf)}")

        if filtered_gdf.empty:
            log_warning(f"No valid geometries found for layer '{layer_name}'")
            return None

        try:
            union_result = unary_union(filtered_gdf.geometry.tolist())
            log_info(f"Unary union result type for {layer_name}: {type(union_result)}")
            return union_result
        except Exception as e:
            log_error(f"Error performing unary_union on filtered geometries: {e}")
            return None


def _process_layer_info(all_layers, project_settings, crs, layer_info):
        if isinstance(layer_info, str):
            return layer_info, []
        elif isinstance(layer_info, dict):
            return layer_info['name'], layer_info.get('values', [])
        else:
            log_warning(f"Invalid layer info type: {type(layer_info)}")
            return None, []


def _extract_coords_from_reason(reason):
    # Try to extract coordinates using regex
    match = re.search(r'\[([-\d.]+)\s+([-\d.]+)\]', reason)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None


def ensure_geodataframe(all_layers, project_settings, crs, layer_name, geometry):
        if not isinstance(geometry, gpd.GeoDataFrame):
            if isinstance(geometry, gpd.GeoSeries):
                return gpd.GeoDataFrame(geometry=geometry, crs=crs)
            elif isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection)):
                return gpd.GeoDataFrame(geometry=[geometry], crs=crs)
            else:
                log_warning(f"Unsupported type for layer {layer_name}: {type(geometry)}")
                return None
        return geometry


def standardize_layer_crs(all_layers, project_settings, crs, layer_name, geometry_or_gdf):
        target_crs = crs
        log_info(f"Standardizing CRS for layer: {layer_name}")

        if isinstance(geometry_or_gdf, gpd.GeoDataFrame):
            log_info(f"Original CRS: {geometry_or_gdf.crs}")
            if geometry_or_gdf.crs is None:
                log_warning(f"Layer {layer_name} has no CRS. Setting to target CRS: {target_crs}")
                geometry_or_gdf.set_crs(target_crs, inplace=True)
            elif geometry_or_gdf.crs != target_crs:
                log_info(f"Transforming layer {layer_name} from {geometry_or_gdf.crs} to {target_crs}")
                geometry_or_gdf = geometry_or_gdf.to_crs(target_crs)
            log_info(f"Final CRS for layer {layer_name}: {geometry_or_gdf.crs}")
            return geometry_or_gdf
        elif isinstance(geometry_or_gdf, gpd.GeoSeries):
            return standardize_layer_crs(layer_name, gpd.GeoDataFrame(geometry=geometry_or_gdf))
        elif isinstance(geometry_or_gdf, (Polygon, MultiPolygon, LineString, MultiLineString)):
            log_info(f"Processing individual geometry for layer: {layer_name}")
            gdf = gpd.GeoDataFrame(geometry=[geometry_or_gdf], crs=target_crs)
            log_info(f"Created GeoDataFrame with CRS: {gdf.crs}")
            return gdf.geometry.iloc[0]
        else:
            log_warning(f"Unsupported type for layer {layer_name}: {type(geometry_or_gdf)}")
            return geometry_or_gdf


def plot_operation_result(all_layers, project_settings, crs, layer_name, op_type, result):
        plt.figure(figsize=(10, 10))
        if isinstance(result, gpd.GeoDataFrame):
            result.plot(ax=plt.gca())
        elif isinstance(result, list):  # For WMTS tiles
            log_info(f"WMTS layer {layer_name} cannot be plotted directly.")
            return
        else:
            gpd.GeoSeries([result]).plot(ax=plt.gca())
        plt.title(f"{op_type.capitalize()} Operation Result for {layer_name}")
        plt.axis('off')
        plt.tight_layout()
        plt.show()


def write_shapefile(all_layers, project_settings, crs, layer_name, output_path, project_loader):
        log_info(f"Writing shapefile for layer {layer_name}: {output_path}")
        if layer_name in all_layers:
            gdf = all_layers[layer_name]
            log_info(f"Type of data for {layer_name}: {type(gdf)}")
            log_info(f"Columns in the data: {gdf.columns.tolist() if hasattr(gdf, 'columns') else 'No columns'}")
            log_info(f"CRS of the data: {gdf.crs if hasattr(gdf, 'crs') else 'No CRS'}")
            log_info(f"Number of rows: {len(gdf) if hasattr(gdf, '__len__') else 'Unknown'}")
            
            if isinstance(gdf, gpd.GeoDataFrame):
                log_info(f"Geometry column name: {gdf.geometry.name}")
                log_info(f"Geometry types: {gdf.geometry.type.unique().tolist()}")
                
                # Handle GeometryCollection
                def convert_geometry(geom):
                    if isinstance(geom, GeometryCollection):
                        polygons = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
                        if polygons:
                            return MultiPolygon(polygons)
                        return None
                    return geom

                gdf['geometry'] = gdf['geometry'].apply(convert_geometry)
                gdf = gdf[gdf['geometry'].notna()]

                if not gdf.empty:
                    full_path = project_loader.resolve_full_path(output_path)
                    gdf.to_file(full_path)
                    log_info(f"Shapefile written for layer {layer_name}: {full_path}")
                else:
                    log_warning(f"No valid geometries found for layer {layer_name} after conversion")
            else:
                log_warning(f"Cannot write shapefile for layer {layer_name}: not a GeoDataFrame")
        else:
            log_warning(f"Cannot write shapefile for layer {layer_name}: layer not found")

def _clean_single_geometry(all_layers, project_settings, crs, geometry):
    # Implement the cleaning logic here
    # For example:
    if geometry.is_valid:
        return geometry
    try:
        cleaned = geometry.buffer(0)
        if cleaned.is_empty:
            return None
        return cleaned
    except Exception as e:
        log_warning(f"Error cleaning geometry: {e}")
        return None


def _remove_thin_growths(all_layers, project_settings, crs, geometry, threshold):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            # Apply a negative buffer followed by a positive buffer
            cleaned = geometry.buffer(-threshold).buffer(threshold)
            
            # Ensure the result is valid and of the same type as the input
            cleaned = make_valid(cleaned)
            if isinstance(geometry, Polygon) and isinstance(cleaned, MultiPolygon):
                # If a Polygon became a MultiPolygon, take the largest part
                largest = max(cleaned.geoms, key=lambda g: g.area)
                return largest
            return cleaned
        elif isinstance(geometry, GeometryCollection):
            cleaned_geoms = [_remove_thin_growths(geom, threshold) for geom in geometry.geoms]
            return GeometryCollection([g for g in cleaned_geoms if g is not None])
        else:
            # For non-polygon geometries, return as is
            return geometry


def _clean_polygon(all_layers, project_settings, crs, polygon, sliver_removal_distance, min_area):
        if polygon.is_empty:
            log_warning("Encountered an empty polygon during cleaning. Skipping.")
            return polygon

        cleaned_exterior = _clean_linear_ring(polygon.exterior, sliver_removal_distance)
        cleaned_interiors = [_clean_linear_ring(interior, sliver_removal_distance) for interior in polygon.interiors]

        # Filter out any empty interiors
        cleaned_interiors = [interior for interior in cleaned_interiors if not interior.is_empty]

        try:
            cleaned_polygon = Polygon(cleaned_exterior, cleaned_interiors)
        except Exception as e:
            log_warning(f"Error creating cleaned polygon: {str(e)}. Returning original polygon.")
            return polygon

        if cleaned_polygon.area < min_area:
            log_info(f"Polygon area ({cleaned_polygon.area}) is below minimum ({min_area}). Removing.")
            return None

        return cleaned_polygon


def _clean_linear_ring(all_layers, project_settings, crs, ring, sliver_removal_distance):
        if ring.is_empty:
            log_warning("Encountered an empty ring during cleaning. Skipping.")
            return ring

        coords = list(ring.coords)
        if len(coords) < 3:
            log_warning(f"Ring has fewer than 3 coordinates. Skipping cleaning. Coords: {coords}")
            return ring

        line = LineString(coords)
        try:
            merged = linemerge([line])
        except Exception as e:
            log_warning(f"Error during linemerge: {str(e)}. Returning original ring.")
            return ring

        if merged.geom_type == 'LineString':
            cleaned = merged.simplify(sliver_removal_distance)
        else:
            log_warning(f"Unexpected geometry type after merge: {merged.geom_type}. Returning original ring.")
            return ring

        if not cleaned.is_ring:
            log_warning("Cleaned geometry is not a ring. Attempting to close it.")
            cleaned = LineString(list(cleaned.coords) + [cleaned.coords[0]])

        return LinearRing(cleaned)


def _remove_small_polygons(all_layers, project_settings, crs, geometry, min_area):
        if isinstance(geometry, Polygon):
            if geometry.area >= min_area:
                return geometry
            else:
                return Polygon()
        elif isinstance(geometry, MultiPolygon):
            return MultiPolygon([poly for poly in geometry.geoms if poly.area >= min_area])
        else:
            return geometry
            

def _merge_close_vertices(all_layers, project_settings, crs, geometry, tolerance=0.1):
        def merge_points(geom):
            if isinstance(geom, LineString):
                coords = list(geom.coords)
                merged_coords = [coords[0]]
                for coord in coords[1:]:
                    if Point(coord).distance(Point(merged_coords[-1])) > tolerance:
                        merged_coords.append(coord)
                return LineString(merged_coords)
            elif isinstance(geom, Polygon):
                exterior_coords = merge_points(LineString(geom.exterior.coords)).coords
                interiors = [merge_points(LineString(interior.coords)).coords for interior in geom.interiors]
                return Polygon(exterior_coords, interiors)
            elif isinstance(geom, MultiPolygon):
                return MultiPolygon([merge_points(part) for part in geom.geoms])
            elif isinstance(geom, MultiLineString):
                return MultiLineString([merge_points(part) for part in geom.geoms])
            else:
                return geom

        if isinstance(geometry, GeometryCollection):
            return GeometryCollection([merge_points(geom) for geom in geometry.geoms])
        else:
            return merge_points(geometry)
        

def _clean_geometry(all_layers, project_settings, crs, geometry):
        if isinstance(geometry, (gpd.GeoSeries, pd.Series)):
            return geometry.apply(lambda geom: _clean_single_geometry(all_layers, project_settings, crs, geom))
        else:
            return _clean_single_geometry(all_layers, project_settings, crs, geometry)


def _remove_empty_geometries(all_layers, project_settings, crs, layer_name, geometry):
        if isinstance(geometry, gpd.GeoDataFrame):
            non_empty = geometry[~geometry.geometry.is_empty & geometry.geometry.notna()]
            if non_empty.empty:
                log_warning(f"All geometries in layer '{layer_name}' are empty or null")
                return None
            return non_empty
        elif isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString)):
            if geometry.is_empty:
                log_warning(f"Geometry in layer '{layer_name}' is empty")
                return None
            return geometry
        else:
            log_warning(f"Unsupported geometry type for layer '{layer_name}': {type(geometry)}")
            return None

def _create_generic_overlay_layer(all_layers, project_settings, crs, layer_name, operation, overlay_type):
        log_info(f"Creating {overlay_type} layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        overlay_layers = operation.get('layers', [])
        
        if not overlay_layers:
            log_warning(f"No overlay layers specified for {layer_name}")
            return
        
        base_geometry = all_layers.get(layer_name)
        if base_geometry is None:
            log_warning(f"Base layer '{layer_name}' not found for {overlay_type} operation")
            return
        
        combined_overlay_geometry = None
        for layer_info in overlay_layers:
            overlay_layer_name, values = _process_layer_info(layer_info)
            if overlay_layer_name is None:
                continue

            overlay_geometry = _get_filtered_geometry(overlay_layer_name, values)
            if overlay_geometry is None:
                continue

            if combined_overlay_geometry is None:
                combined_overlay_geometry = overlay_geometry
            else:
                combined_overlay_geometry = combined_overlay_geometry.union(overlay_geometry)

        if combined_overlay_geometry is None:
            log_warning(f"No valid overlay geometries found for layer '{layer_name}'")
            return

        try:
            if overlay_type == 'difference':
                result_geometry = base_geometry.geometry.difference(combined_overlay_geometry)
            elif overlay_type == 'intersection':
                result_geometry = base_geometry.geometry.intersection(combined_overlay_geometry)
            else:
                log_error(f"Unsupported overlay type: {overlay_type}")
                return
            
            # Apply a series of cleaning operations
            result_geometry = _clean_geometry(result_geometry)
            
            log_info(f"Applied {overlay_type} operation and cleaned up results")
        except Exception as e:
            log_error(f"Error during {overlay_type} operation: {str(e)}")
            import traceback
            log_error(f"Traceback:\n{traceback.format_exc()}")
            return

        # Check if result_geometry is empty
        if result_geometry.empty:
            log_warning(f"No valid geometry created for {overlay_type} layer: {layer_name}")
            all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=base_geometry.crs)
        else:
            # Create a new GeoDataFrame with the resulting geometries
            result_gdf = gpd.GeoDataFrame(geometry=result_geometry, crs=base_geometry.crs)
            all_layers[layer_name] = result_gdf
            log_info(f"Created {overlay_type} layer: {layer_name} with {len(result_geometry)} geometries")


def apply_buffer_trick(geometry, buffer_distance=0.01):
    log_info(f"Applying buffer trick with distance: {buffer_distance}")
    
    buffered = geometry.buffer(buffer_distance)
    log_info(f"Buffered geometry type: {buffered.geom_type}")
    
    unbuffered = buffered.buffer(-buffer_distance)
    log_info(f"Unbuffered geometry type: {unbuffered.geom_type}")
    
    return unbuffered


def prepare_and_clean_geometry(all_layers, project_settings, crs, geometry, buffer_distance=0.001, thin_growth_threshold=0.001, merge_vertices_tolerance=0.0001):
    """
    Prepares and cleans a geometry by applying multiple cleaning operations and the buffer trick.
    
    Args:
    all_layers (dict): Dictionary containing all layers.
    project_settings (dict): Project settings.
    crs: Coordinate Reference System.
    geometry: Input geometry to be cleaned.
    buffer_distance (float): Distance for buffer operations.
    thin_growth_threshold (float): Threshold for removing thin growths.
    merge_vertices_tolerance (float): Tolerance for merging close vertices.
    
    Returns:
    Cleaned and prepared geometry.
    """
    log_info("Starting geometry preparation and cleaning")
    
    if isinstance(geometry, gpd.GeoDataFrame):
        geometry = geometry.geometry.unary_union
    
    # Clean the geometry
    geometry = _clean_geometry(all_layers, project_settings, crs, geometry)
    log_info("Initial cleaning completed")
    
    # Remove thin growths
    geometry = _remove_thin_growths(all_layers, project_settings, crs, geometry, thin_growth_threshold)
    log_info("Thin growths removed")
    
    # Merge close vertices
    geometry = _merge_close_vertices(all_layers, project_settings, crs, geometry, merge_vertices_tolerance)
    log_info("Close vertices merged")
    
    # Apply buffer trick
    geometry = apply_buffer_trick(geometry, buffer_distance)
    log_info("Buffer trick applied")
    
    # Final unary union to ensure a single geometry
    geometry = unary_union(geometry)
    log_info("Final unary union applied")
    
    return geometry

# Make sure to import any necessary functions at the top of the file
from shapely.ops import unary_union

def explode_to_singlepart(geometry_or_gdf):
    """
    Converts multipart geometries to singlepart geometries.
    
    Args:
    geometry_or_gdf: A Shapely geometry object or a GeoDataFrame
    
    Returns:
    A GeoDataFrame with singlepart geometries
    """
    log_info("Exploding multipart geometries to singlepart")
    
    if isinstance(geometry_or_gdf, gpd.GeoDataFrame):
        exploded = geometry_or_gdf.explode(index_parts=True)
        exploded = exploded.reset_index(drop=True)
    else:
        if isinstance(geometry_or_gdf, GeometryCollection):
            geometries = [geom for geom in geometry_or_gdf.geoms if isinstance(geom, (Polygon, MultiPolygon))]
        elif isinstance(geometry_or_gdf, (MultiPolygon, Polygon)):
            geometries = [geometry_or_gdf]
        else:
            log_warning(f"Unsupported geometry type for explosion: {type(geometry_or_gdf)}")
            return gpd.GeoDataFrame(geometry=[geometry_or_gdf])
        
        exploded = gpd.GeoDataFrame(geometry=[])
        for geom in geometries:
            if isinstance(geom, MultiPolygon):
                exploded = exploded.append(gpd.GeoDataFrame(geometry=list(geom.geoms)))
            else:
                exploded = exploded.append(gpd.GeoDataFrame(geometry=[geom]))
    
    log_info(f"Exploded {len(geometry_or_gdf) if isinstance(geometry_or_gdf, gpd.GeoDataFrame) else 1} "
             f"multipart geometries into {len(exploded)} singlepart geometries")
    return exploded

