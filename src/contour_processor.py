import requests
import xml.etree.ElementTree as ET
import rasterio
import numpy as np
from scipy.ndimage import gaussian_filter
import geopandas as gpd
from shapely.geometry import LineString, box
from shapely.ops import linemerge, unary_union
from src.utils import log_info, log_warning, log_error, resolve_path
from skimage import measure
import os
import zipfile
from rasterio.merge import merge
from pyproj import Transformer
import pandas as pd
import hashlib

CACHE_DIR = '.cache'

def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        log_info(f"Created cache directory: {CACHE_DIR}")

def get_cached_file(url, file_type):
    file_name = os.path.join(CACHE_DIR, f"{hashlib.md5(url.encode()).hexdigest()}.{file_type}")
    if os.path.exists(file_name):
        log_info(f"Using cached file: {file_name}")
        return file_name
    return None

def cache_file(url, content, file_type):
    file_name = os.path.join(CACHE_DIR, f"{hashlib.md5(url.encode()).hexdigest()}.{file_type}")
    with open(file_name, 'wb') as f:
        f.write(content)
    log_info(f"Cached file: {file_name}")
    return file_name

def process_contour(operation, geltungsbereich, buffer_distance, project_crs):
    ensure_cache_dir()
    log_info("Starting contour processing")
    url = operation['url']
    layers = operation['layers']
    buffer = operation.get('buffer', 0)

    log_info(f"Downloading ATOM feed from URL: {url}")
    atom_file = get_cached_file(url, 'xml')
    if atom_file is None:
        try:
            response = requests.get(url)
            response.raise_for_status()
            atom_file = cache_file(url, response.content, 'xml')
            log_info("Successfully downloaded and cached ATOM feed")
        except requests.RequestException as e:
            log_error(f"Failed to download ATOM feed: {str(e)}")
            return None
    
    try:
        with open(atom_file, 'rb') as f:
            root = ET.parse(f).getroot()
        log_info("Successfully parsed ATOM feed")
    except ET.ParseError as e:
        log_error(f"Failed to parse ATOM feed: {str(e)}")
        return None

    log_info("Searching for DGM data download links")
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    download_links = root.findall('.//atom:link[@rel="section"][@type="application/zip"]', ns)
    if not download_links:
        log_error("Could not find download links for DGM data in ATOM feed")
        return None

    log_info(f"Found {len(download_links)} potential DGM data files")

    log_info(f"Project CRS: {project_crs}")
    log_info(f"Geltungsbereich bounds: {geltungsbereich.bounds}")
    
    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)
    log_info(f"Buffered geltungsbereich bounds: {geltungsbereich_buffered.bounds}")

    # Create a transformer from EPSG:4326 to the project CRS
    transformer = Transformer.from_crs("EPSG:4326", project_crs, always_xy=True)

    relevant_links = []
    for link in download_links:
        href = link.get('href')
        if href and href.endswith('_isoli.zip'):
            bbox_str = link.get('bbox')
            if bbox_str:
                bbox = [float(x) for x in bbox_str.split()]
                # Transform the bounding box coordinates
                transformed_bbox = transformer.transform(bbox[1], bbox[0]) + transformer.transform(bbox[3], bbox[2])
                tile_box = box(*transformed_bbox)
                if geltungsbereich_buffered.intersects(tile_box):
                    relevant_links.append(link)
                    log_info(f"Found intersecting isoli tile: {bbox} -> {transformed_bbox}")

    log_info(f"Found {len(relevant_links)} relevant isoli data files")

    # Download and extract relevant files
    shape_files = []
    for link in relevant_links:
        download_url = link.get('href')
        cached_zip = resolve_path(get_cached_file(download_url, 'zip'), CACHE_DIR)
        if cached_zip is None:
            try:
                response = requests.get(download_url)
                response.raise_for_status()
                cached_zip = cache_file(download_url, response.content, 'zip')
                log_info(f"Downloaded and cached: {cached_zip}")
            except Exception as e:
                log_error(f"Failed to download {download_url}: {str(e)}")
                continue
    
        # Extract files from zip if not already extracted
        zip_hash = os.path.basename(cached_zip).split('.')[0]
        extracted_dir = resolve_path(os.path.join(CACHE_DIR, zip_hash))
        if not os.path.exists(extracted_dir):
            os.makedirs(extracted_dir)
            with zipfile.ZipFile(cached_zip, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)
            log_info(f"Extracted contents to: {extracted_dir}")
        
        # Find shape files in extracted directory
        shp_files = [f for f in os.listdir(extracted_dir) if f.endswith('.shp')]
        if shp_files:
            shape_files.extend([os.path.join(extracted_dir, f) for f in shp_files])
        else:
            log_warning(f"No shape file found in {extracted_dir}")

    if not shape_files:
        log_error("No valid shape files found")
        return None

    log_info("Reading and merging shape files")
    gdf_list = []
    for shp_file in shape_files:
        gdf = gpd.read_file(shp_file)
        # Ensure we only keep LineString geometries
        gdf = gdf[gdf.geometry.type == 'LineString']
        gdf_list.append(gdf)

    merged_gdf = gpd.GeoDataFrame(pd.concat(gdf_list, ignore_index=True), crs=gdf_list[0].crs)
    log_info(f"Successfully merged shape data. Total features: {len(merged_gdf)}")

    log_info(f"Clipping contours to geltungsbereich with buffer {buffer_distance}")
    clipped_gdf = merged_gdf.clip(geltungsbereich_buffered)
    log_info(f"Clipped GeoDataFrame contains {len(clipped_gdf)} features")

    # Ensure all geometries are LineStrings
    clipped_gdf = clipped_gdf[clipped_gdf.geometry.type == 'LineString']
    log_info(f"Final GeoDataFrame contains {len(clipped_gdf)} LineString features")

    log_info("Contour processing completed successfully")

    return clipped_gdf