import geopandas as gpd
from matplotlib import pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
import os
from src.wmts_downloader import download_wmts_tiles, download_wms_tiles, process_and_stitch_tiles
from shapely.ops import unary_union, linemerge
from shapely.validation import make_valid, explain_validity
from shapely.geometry import LinearRing
import shutil
from src.contour_processor import process_contour
from owslib.wmts import WebMapTileService
import ezdxf
import pandas as pd
import math
from geopandas import GeoSeries
import re
from src.project_loader import project_loader

def create_buffer_layer(all_layers, project_settings, crs, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layers = operation.get('layers', [])
        buffer_distance = operation['distance']
        join_style = operation.get('joinStyle', 'mitre')  # Default to 'mitre' instead of 'round'

        join_style_map = {'round': 1, 'mitre': 2, 'bevel': 3}
        join_style_value = join_style_map.get(join_style, 2)  # Default to mitre (2) if not specified

        combined_geometry = None
        for layer_info in source_layers:
            source_layer_name, values = _process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = _get_filtered_geometry(source_layer_name, values)
            if layer_geometry is None:
                continue

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.union(layer_geometry)

        if combined_geometry is not None:
            if isinstance(combined_geometry, gpd.GeoDataFrame):
                buffered = combined_geometry.geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                buffered = buffered[~buffered.is_empty]  # Remove empty geometries
                if buffered.empty:
                    log_warning(f"Buffer operation resulted in empty geometry for layer {layer_name}")
                    return None
                result = gpd.GeoDataFrame(geometry=buffered, crs=crs)
                
                # Copy attributes from the original geometry
                for col in combined_geometry.columns:
                    if col != 'geometry':
                        result[col] = combined_geometry[col].iloc[0]
            else:
                # Handle individual geometry objects
                buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                if buffered.is_empty:
                    log_warning(f"Buffer operation resulted in empty geometry for layer {layer_name}")
                    return None
                result = gpd.GeoDataFrame(geometry=[buffered], crs=crs)
            
            return result
        else:
            log_warning(f"No valid geometry found for buffer operation on layer {layer_name}")
            return None


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


def _extract_coords_from_reason(all_layers, project_settings, crs, reason):
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


def write_shapefile(all_layers, project_settings, crs, layer_name, output_path):
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


