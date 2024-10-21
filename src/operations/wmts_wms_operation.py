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

def process_wmts_or_wms_layer(all_layers, project_settings, crs, layer_name, operation):
        log_info(f"Processing WMTS/WMS layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        target_folder = project_loader.resolve_full_path(operation['targetFolder'])
        zoom_level = operation.get('zoom')
        
        zoom_folder = os.path.join(target_folder, f"zoom_{zoom_level}") if zoom_level else target_folder
        
        layer_info = next((l for l in project_settings['geomLayers'] if l['name'] == layer_name), None)
        update_flag = layer_info.get('update', False) if layer_info else False
        overwrite_flag = operation.get('overwrite', False)
        
        os.makedirs(zoom_folder, exist_ok=True)
        
        log_info(f"Target folder path: {zoom_folder}")
        log_info(f"Update flag: {update_flag}, Overwrite flag: {overwrite_flag}")

        layers = operation.get('layers', [])
        buffer_distance = operation.get('buffer', 100)
        service_info = {
            'url': operation['url'],
            'layer': operation['layer'],
            'proj': operation.get('proj'),
            'srs': operation.get('srs'),
            'format': operation.get('format', 'image/png'),
            'sleep': operation.get('sleep', 0),
            'limit': operation.get('limit', 0),
            'postProcess': operation.get('postProcess', {}),
            'overwrite': overwrite_flag,
            'zoom': zoom_level
        }

        service_info['postProcess']['removeText'] = operation.get('postProcess', {}).get('removeText', False)
        service_info['postProcess']['textRemovalMethod'] = operation.get('postProcess', {}).get('textRemovalMethod', 'tesseract')

        stitch_tiles = operation.get('stitchTiles', False)
        service_info['stitchTiles'] = stitch_tiles

        log_info(f"Service info: {service_info}")
        log_info(f"Layers to process: {layers}")

        wmts = WebMapTileService(service_info['url'])
        tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
        available_zooms = sorted(tile_matrix.keys(), key=int)
        
        requested_zoom = service_info.get('zoom')
        
        if requested_zoom is None:
            # Use the highest available zoom level if not specified
            chosen_zoom = available_zooms[-1]
            log_info(f"No zoom level specified. Using highest available zoom: {chosen_zoom}")
        else:
            # Try to use the manually specified zoom level
            if str(requested_zoom) in available_zooms:
                chosen_zoom = str(requested_zoom)
            else:
                error_message = (
                    f"Error: Zoom level {requested_zoom} not available for projection {service_info['proj']}.\n"
                    f"Available zoom levels: {', '.join(available_zooms)}.\n"
                    f"Please choose a zoom level from the available options or remove the 'zoom' key to use the highest available zoom."
                )
                raise ValueError(error_message)
        
        service_info['zoom'] = chosen_zoom
        log_info(f"Using zoom level: {chosen_zoom}")
        
        all_tiles = []
        for layer in layers:
            if layer in all_layers:
                layer_geometry = all_layers[layer]
                if isinstance(layer_geometry, gpd.GeoDataFrame):
                    layer_geometry = layer_geometry.geometry.unary_union

                log_info(f"Downloading tiles for layer: {layer}")
                log_info(f"Layer geometry type: {type(layer_geometry)}")
                log_info(f"Layer geometry bounds: {layer_geometry.bounds}")

                if 'wmts' in operation['type'].lower():
                    downloaded_tiles = download_wmts_tiles(service_info, layer_geometry, buffer_distance, zoom_folder, update=update_flag, overwrite=overwrite_flag)
                    wmts = WebMapTileService(service_info['url'])
                    tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
                    try:
                        tile_matrix_zoom = tile_matrix[str(service_info['zoom'])]
                    except KeyError:
                        available_zooms = sorted(tile_matrix.keys())
                        error_message = (
                            f"Error: Zoom level {service_info['zoom']} not available for projection {service_info['proj']}.\n"
                            f"Available zoom levels: {', '.join(available_zooms)}.\n"
                            f"Please choose a zoom level from the available options."
                        )
                        raise ValueError(error_message)
                else:
                    downloaded_tiles = download_wms_tiles(service_info, layer_geometry, buffer_distance, zoom_folder, update=update_flag, overwrite=overwrite_flag)
                    tile_matrix_zoom = None

                if stitch_tiles:
                    processed_tiles = process_and_stitch_tiles(service_info, downloaded_tiles, tile_matrix_zoom, zoom_folder, layer)
                    all_tiles.extend(processed_tiles)
                else:
                    all_tiles.extend(downloaded_tiles)
            else:
                log_warning(f"Layer {layer} not found for WMTS/WMS download of {layer_name}")

        all_layers[layer_name] = all_tiles
        log_info(f"Total tiles for {layer_name}: {len(all_tiles)}")

        return all_layers[layer_name]


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


