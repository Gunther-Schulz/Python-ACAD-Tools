import requests
import xml.etree.ElementTree as ET
import rasterio
import numpy as np
from scipy.ndimage import gaussian_filter
import geopandas as gpd
from shapely.geometry import LineString
from src.logger import log_info, log_warning, log_error

def process_contour(operation, geltungsbereich, buffer_distance):
    url = operation['url']
    layers = operation['layers']
    buffer = operation.get('buffer', 0)

    # Download and parse the ATOM feed
    response = requests.get(url)
    root = ET.fromstring(response.content)

    # Find the download link for the DGM data
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    download_link = root.find('.//atom:link[@rel="alternate"][@type="application/x-ogc-wcs"]', ns).get('href')

    # Download the DGM data
    dgm_response = requests.get(download_link)
    with open('temp_dgm.tif', 'wb') as f:
        f.write(dgm_response.content)

    # Read the DGM data
    with rasterio.open('temp_dgm.tif') as src:
        elevation_data = src.read(1)
        transform = src.transform

    # Apply Gaussian smoothing to reduce noise
    smoothed_data = gaussian_filter(elevation_data, sigma=1)

    # Generate contour lines
    contours = generate_contours(smoothed_data, transform)

    # Convert contours to GeoDataFrame
    gdf = gpd.GeoDataFrame(geometry=contours, crs=src.crs)

    # Clip to geltungsbereich with buffer
    geltungsbereich_buffered = geltungsbereich.buffer(buffer)
    clipped_gdf = gdf.clip(geltungsbereich_buffered)

    return clipped_gdf

def generate_contours(elevation_data, transform, interval=1.0):
    contours = []
    for level in np.arange(elevation_data.min(), elevation_data.max(), interval):
        for contour in measure.find_contours(elevation_data, level):
            coords = [rasterio.transform.xy(transform, y, x) for y, x in contour]
            contours.append(LineString(coords))
    return contours