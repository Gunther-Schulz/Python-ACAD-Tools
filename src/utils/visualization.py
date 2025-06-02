"""Visualization utilities for debugging and development plotting."""
from typing import Optional

# Direct imports for hard dependencies
import matplotlib.pyplot as plt
from shapely.geometry.base import BaseGeometry
from shapely.geometry import MultiPolygon, Polygon, LineString, MultiLineString, Point, MultiPoint
import geopandas as gpd

def plot_shapely_geometry(geom: BaseGeometry, title: Optional[str] = None, ax=None, **kwargs):
    """
    Plots a single Shapely geometry using matplotlib.

    Args:
        geom: The Shapely geometry object to plot.
        title: Optional title for the plot.
        ax: Optional matplotlib Axes object to plot on. If None, a new figure and axes are created.
        **kwargs: Additional keyword arguments to pass to the plot function
                  (e.g., color, alpha, linewidth for lines; facecolor, edgecolor for polygons).
    """
    if geom is None or geom.is_empty:
        return

    if ax is None:
        fig, ax = plt.subplots()
    else:
        fig = ax.figure

    if isinstance(geom, (Polygon, MultiPolygon)):
        default_kwargs = {'facecolor': 'lightblue', 'edgecolor': 'blue', 'alpha': 0.7}
        default_kwargs.update(kwargs)
        if hasattr(geom, 'exterior'): # Single Polygon
            x, y = geom.exterior.xy
            ax.fill(x, y, **default_kwargs)
            ax.plot(x, y, color=default_kwargs.get('edgecolor', 'blue'), linewidth=default_kwargs.get('linewidth', 1))
        elif hasattr(geom, 'geoms'): # MultiPolygon
            for poly in geom.geoms:
                x, y = poly.exterior.xy
                ax.fill(x, y, **default_kwargs)
                ax.plot(x, y, color=default_kwargs.get('edgecolor', 'blue'), linewidth=default_kwargs.get('linewidth', 1))
                for interior in poly.interiors:
                    x_i, y_i = interior.xy
                    ax.fill(x_i, y_i, facecolor='white', edgecolor=default_kwargs.get('edgecolor', 'blue'), linewidth=default_kwargs.get('linewidth', 1))
                    ax.plot(x_i, y_i, color=default_kwargs.get('edgecolor', 'blue'), linewidth=default_kwargs.get('linewidth', 1))

    elif isinstance(geom, (LineString, MultiLineString)):
        default_kwargs = {'color': 'green', 'linewidth': 1.5, 'solid_capstyle': 'round'}
        default_kwargs.update(kwargs)
        if hasattr(geom, 'xy'): # Single LineString
            x, y = geom.xy
            ax.plot(x, y, **default_kwargs)
        elif hasattr(geom, 'geoms'): # MultiLineString
            for line in geom.geoms:
                x, y = line.xy
                ax.plot(x, y, **default_kwargs)

    elif isinstance(geom, (Point, MultiPoint)):
        default_kwargs = {'color': 'red', 'marker': 'o', 'markersize': 5}
        default_kwargs.update(kwargs)
        if hasattr(geom, 'xy'): # Single Point
            x, y = geom.xy
            ax.plot(x, y, **default_kwargs)
        elif hasattr(geom, 'geoms'): # MultiPoint
            for pt in geom.geoms:
                x, y = pt.xy
                ax.plot(x, y, **default_kwargs)

    ax.set_aspect('equal', adjustable='box')
    if title:
        ax.set_title(title)

    if ax is None: # Only call show if we created the figure
        plt.show()

def plot_gdf(gdf, title: Optional[str] = None, ax=None, **kwargs):
    """
    Plots a GeoDataFrame using its built-in plot method (which uses matplotlib).

    Args:
        gdf: The GeoDataFrame to plot.
        title: Optional title for the plot.
        ax: Optional matplotlib Axes object to plot on. If None, a new figure and axes are created.
        **kwargs: Additional keyword arguments to pass to gdf.plot().
    """
    if gdf is None or gdf.empty:
        return

    if ax is None:
        fig, current_ax = plt.subplots()
    else:
        current_ax = ax
        fig = current_ax.figure

    gdf.plot(ax=current_ax, **kwargs)

    current_ax.set_aspect('equal', adjustable='box')
    if title:
        current_ax.set_title(title)

    if ax is None: # Only call show if we created the figure
        plt.show()
