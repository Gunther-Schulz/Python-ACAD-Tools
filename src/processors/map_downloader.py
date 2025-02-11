from typing import Dict, Any, List, Optional, Union, Tuple
import os
import math
from pathlib import Path
import requests
from owslib.wmts import WebMapTileService
from owslib.wms import WebMapService
from PIL import Image
import numpy as np
from shapely.geometry import box, Polygon
import pyproj
from pyproj import Transformer

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error

class MapDownloader(BaseProcessor):
    """Processor for downloading and processing web map services."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the map downloader.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self.wmts_services: Dict[str, WebMapTileService] = {}
        self.wms_services: Dict[str, WebMapService] = {}
        self._initialize()

    def _initialize(self) -> None:
        """Initialize map downloader resources."""
        # Create cache directory if needed
        cache_dir = Path('cache/maps')
        cache_dir.mkdir(parents=True, exist_ok=True)

    def process_map_layers(self) -> None:
        """Process all configured map layers."""
        # Process WMTS layers
        for layer_config in self.config.project_config.wmts_layers:
            try:
                self._process_wmts_layer(layer_config)
            except Exception as e:
                log_error(f"Error processing WMTS layer {layer_config.get('name', 'unknown')}: {str(e)}")

        # Process WMS layers
        for layer_config in self.config.project_config.wms_layers:
            try:
                self._process_wms_layer(layer_config)
            except Exception as e:
                log_error(f"Error processing WMS layer {layer_config.get('name', 'unknown')}: {str(e)}")

    def _process_wmts_layer(self, layer_config: Dict[str, Any]) -> None:
        """Process a WMTS layer configuration.
        
        Args:
            layer_config: Layer configuration dictionary
        """
        name = layer_config.get('name')
        if not name:
            log_error("WMTS layer configuration missing required 'name' field")
            return

        url = layer_config.get('url')
        if not url:
            log_error(f"WMTS layer {name} missing required 'url' field")
            return

        layer_name = layer_config.get('layer')
        if not layer_name:
            log_error(f"WMTS layer {name} missing required 'layer' field")
            return

        log_info(f"Processing WMTS layer: {name}")

        # Get or create WMTS service
        wmts = self._get_wmts_service(url)
        if not wmts:
            return

        # Get layer bounds
        bounds = self._get_layer_bounds(layer_config)
        if not bounds:
            return

        # Download tiles
        self._download_wmts_tiles(
            wmts, layer_name, bounds, layer_config
        )

    def _process_wms_layer(self, layer_config: Dict[str, Any]) -> None:
        """Process a WMS layer configuration.
        
        Args:
            layer_config: Layer configuration dictionary
        """
        name = layer_config.get('name')
        if not name:
            log_error("WMS layer configuration missing required 'name' field")
            return

        url = layer_config.get('url')
        if not url:
            log_error(f"WMS layer {name} missing required 'url' field")
            return

        layer_name = layer_config.get('layer')
        if not layer_name:
            log_error(f"WMS layer {name} missing required 'layer' field")
            return

        log_info(f"Processing WMS layer: {name}")

        # Get or create WMS service
        wms = self._get_wms_service(url)
        if not wms:
            return

        # Get layer bounds
        bounds = self._get_layer_bounds(layer_config)
        if not bounds:
            return

        # Download image
        self._download_wms_image(
            wms, layer_name, bounds, layer_config
        )

    def _get_wmts_service(self, url: str) -> Optional[WebMapTileService]:
        """Get or create a WMTS service.
        
        Args:
            url: Service URL
            
        Returns:
            WMTS service or None if creation fails
        """
        if url in self.wmts_services:
            return self.wmts_services[url]

        try:
            wmts = WebMapTileService(url)
            self.wmts_services[url] = wmts
            return wmts
        except Exception as e:
            log_error(f"Error creating WMTS service for {url}: {str(e)}")
            return None

    def _get_wms_service(self, url: str) -> Optional[WebMapService]:
        """Get or create a WMS service.
        
        Args:
            url: Service URL
            
        Returns:
            WMS service or None if creation fails
        """
        if url in self.wms_services:
            return self.wms_services[url]

        try:
            wms = WebMapService(url)
            self.wms_services[url] = wms
            return wms
        except Exception as e:
            log_error(f"Error creating WMS service for {url}: {str(e)}")
            return None

    def _get_layer_bounds(self, layer_config: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
        """Get layer bounds from configuration.
        
        Args:
            layer_config: Layer configuration
            
        Returns:
            Tuple of (minx, miny, maxx, maxy) or None if invalid
        """
        bounds = layer_config.get('bounds')
        if not bounds:
            log_error("Layer configuration missing required 'bounds' field")
            return None

        try:
            return (
                float(bounds['minx']),
                float(bounds['miny']),
                float(bounds['maxx']),
                float(bounds['maxy'])
            )
        except (KeyError, ValueError) as e:
            log_error(f"Invalid bounds configuration: {str(e)}")
            return None

    def _download_wmts_tiles(self, wmts: WebMapTileService,
                           layer_name: str,
                           bounds: Tuple[float, float, float, float],
                           config: Dict[str, Any]) -> None:
        """Download WMTS tiles for a layer.
        
        Args:
            wmts: WMTS service
            layer_name: Layer name
            bounds: Layer bounds
            config: Layer configuration
        """
        # Get layer
        layer = wmts.contents[layer_name]
        
        # Get target CRS
        target_crs = config.get('srs', layer.tilematrixsets[0])
        
        # Get zoom level
        zoom = config.get('zoom', 0)
        
        # Get tile matrix
        matrix_id = None
        for matrix_set in layer.tilematrixsets:
            if matrix_set.startswith(target_crs):
                matrix_id = f"{matrix_set}:{zoom}"
                break
        
        if not matrix_id:
            log_error(f"No suitable tile matrix found for {layer_name}")
            return

        # Calculate tile range
        tile_matrix = wmts.tilematrixsets[matrix_id].tilematrix[zoom]
        min_tile_row, min_tile_col = wmts.gettilematrixindex(
            bounds[:2], zoom, layer_name
        )
        max_tile_row, max_tile_col = wmts.gettilematrixindex(
            bounds[2:], zoom, layer_name
        )

        # Create target directory
        target_dir = Path(self.resolve_path(config.get('targetFolder', 'maps')))
        target_dir.mkdir(parents=True, exist_ok=True)

        # Download tiles
        for row in range(min_tile_row, max_tile_row + 1):
            for col in range(min_tile_col, max_tile_col + 1):
                try:
                    tile = wmts.gettile(
                        layer=layer_name,
                        tilematrix=matrix_id,
                        row=row,
                        column=col,
                        format=config.get('format', 'image/png')
                    )
                    
                    tile_path = target_dir / f"{layer_name}_{zoom}_{row}_{col}.png"
                    with open(tile_path, 'wb') as f:
                        f.write(tile.read())
                    
                    log_debug(f"Downloaded tile: {tile_path}")
                    
                except Exception as e:
                    log_warning(f"Error downloading tile ({row}, {col}): {str(e)}")

    def _download_wms_image(self, wms: WebMapService,
                           layer_name: str,
                           bounds: Tuple[float, float, float, float],
                           config: Dict[str, Any]) -> None:
        """Download WMS image for a layer.
        
        Args:
            wms: WMS service
            layer_name: Layer name
            bounds: Layer bounds
            config: Layer configuration
        """
        # Calculate image size
        width = config.get('width', 1024)
        height = config.get('height', 1024)

        # Create target directory
        target_dir = Path(self.resolve_path(config.get('targetFolder', 'maps')))
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Get image
            img = wms.getmap(
                layers=[layer_name],
                srs=config.get('srs', 'EPSG:3857'),
                bbox=bounds,
                size=(width, height),
                format=config.get('format', 'image/png'),
                transparent=config.get('transparent', True)
            )

            # Save image
            target_path = target_dir / f"{layer_name}.png"
            with open(target_path, 'wb') as f:
                f.write(img.read())

            log_info(f"Downloaded WMS image: {target_path}")

        except Exception as e:
            log_error(f"Error downloading WMS image: {str(e)}")

    def _post_process_image(self, image_path: Path,
                          config: Dict[str, Any]) -> None:
        """Apply post-processing to an image.
        
        Args:
            image_path: Path to image
            config: Post-processing configuration
        """
        try:
            img = Image.open(image_path)
            post_process = config.get('postProcess', {})

            if post_process.get('grayscale'):
                img = img.convert('L')

            if 'alphaColor' in post_process:
                img = self._set_alpha_color(
                    img, post_process['alphaColor']
                )

            if 'colorMap' in post_process:
                img = self._apply_color_map(
                    img, post_process['colorMap']
                )

            img.save(image_path)
            log_debug(f"Applied post-processing to {image_path}")

        except Exception as e:
            log_warning(f"Error post-processing image {image_path}: {str(e)}")

    def _set_alpha_color(self, img: Image.Image,
                        color: Union[str, List[int]]) -> Image.Image:
        """Set a color to be fully transparent.
        
        Args:
            img: Input image
            color: Color to make transparent
            
        Returns:
            Processed image
        """
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        data = np.array(img)
        if isinstance(color, str):
            # Convert color name to RGB
            rgb = Image.new('RGB', (1, 1), color).getpixel((0, 0))
            alpha_mask = np.all(data[:, :, :3] == rgb, axis=2)
        else:
            alpha_mask = np.all(data[:, :, :3] == color[:3], axis=2)

        data[alpha_mask, 3] = 0
        return Image.fromarray(data)

    def _apply_color_map(self, img: Image.Image,
                        color_map: Dict[str, str]) -> Image.Image:
        """Apply a color mapping to an image.
        
        Args:
            img: Input image
            color_map: Mapping of source to target colors
            
        Returns:
            Processed image
        """
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        data = np.array(img)
        for src_color, dst_color in color_map.items():
            # Convert color names to RGB
            src_rgb = Image.new('RGB', (1, 1), src_color).getpixel((0, 0))
            dst_rgb = Image.new('RGB', (1, 1), dst_color).getpixel((0, 0))
            
            # Find matching pixels
            mask = np.all(data[:, :, :3] == src_rgb, axis=2)
            
            # Replace colors
            data[mask, :3] = dst_rgb

        return Image.fromarray(data) 