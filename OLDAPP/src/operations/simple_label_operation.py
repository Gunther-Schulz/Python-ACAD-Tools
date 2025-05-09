import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, LineString, MultiLineString, MultiPolygon
from src.utils import log_debug, log_warning
from src.style_manager import StyleManager

def create_simple_label_layer(all_layers, project_settings, crs, layer_name, operation, project_loader=None):
    """
    Create a simple label layer with texts placed at the center of each geometry.
    This function creates label points at the centroid of each geometry with the
    value from the specified label column.

    Parameters:
    -----------
    all_layers : dict
        Dictionary of all available layers
    project_settings : dict
        Project configuration settings
    crs : str
        Coordinate reference system
    layer_name : str
        Name of the layer to create
    operation : dict
        Operation configuration
    project_loader : ProjectLoader, optional
        Project loader instance for accessing style presets

    Returns:
    --------
    GeoDataFrame
        A GeoDataFrame with Point geometries and label texts
    """
    log_debug(f"Creating simple label layer for {layer_name}")

    # Get source layer configuration
    source_layer_name = operation.get('sourceLayer', layer_name)
    label_column = operation.get('labelColumn')

    # If no explicit labelColumn is provided, check for a label attribute in the layer config
    if not label_column:
        for layer_config in project_settings.get('geomLayers', []):
            if layer_config.get('name') == source_layer_name:
                label_column = layer_config.get('label')
                break

    if not label_column:
        log_warning(f"No label column specified for simple label operation on layer {layer_name}")
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    # Check if source layer exists
    if source_layer_name not in all_layers:
        log_warning(f"Source layer {source_layer_name} not found for simple label operation")
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    # Get source GeoDataFrame
    source_gdf = all_layers[source_layer_name]
    if source_gdf is None or len(source_gdf) == 0:
        log_warning(f"Source layer {source_layer_name} is empty")
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    # Debug: Print the actual column names to see what's available
    actual_columns = list(source_gdf.columns)
    log_debug(f"Available columns in {source_layer_name}: {actual_columns}")

    # Try various methods to find the column
    found_column = None

    # 1. Direct match
    if label_column in source_gdf.columns:
        found_column = label_column

    # 2. Case-insensitive match
    if not found_column:
        for col in actual_columns:
            if col.lower() == label_column.lower():
                found_column = col
                log_debug(f"Found case-insensitive match: '{col}' for requested column '{label_column}'")
                break

    # 3. Try prefix/suffix variations
    if not found_column:
        prefixes = ['', 'f_', 'field_', 'attr_']
        suffixes = ['', '_field', '_attr', '_value']
        for prefix in prefixes:
            for suffix in suffixes:
                test_col = f"{prefix}{label_column}{suffix}"
                if test_col in source_gdf.columns:
                    found_column = test_col
                    log_debug(f"Found column with prefix/suffix: '{test_col}' for requested column '{label_column}'")
                    break
            if found_column:
                break

    # 4. Try fuzzy matching - if column looks similar
    if not found_column:
        for col in actual_columns:
            # Check for common transformations
            if (col.replace('_', '') == label_column.replace('_', '') or  # Compare without underscores
                col.lower().startswith(label_column.lower()) or           # Prefix match
                label_column.lower().startswith(col.lower())):            # Suffix match
                found_column = col
                log_debug(f"Found fuzzy match: '{col}' for requested column '{label_column}'")
                break

    # Use the found column or fall back to the original
    if found_column:
        label_column = found_column

    # Check if label column exists in source data
    if label_column not in source_gdf.columns:
        log_warning(f"Label column '{label_column}' not found in layer {source_layer_name}")
        log_warning(f"Available columns are: {actual_columns}")
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    # Create label points at geometry centroids
    points = []
    labels = []
    rotations = []

    for idx, row in source_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        label_text = str(row[label_column])

        # Get centroid point based on geometry type
        if isinstance(geom, (Polygon, MultiPolygon)):
            # For polygons, use centroid if it's within the polygon, otherwise use representative point
            centroid = geom.centroid
            if not geom.contains(centroid):
                centroid = geom.representative_point()
            points.append(centroid)
            rotations.append(0.0)  # No rotation for polygons

        elif isinstance(geom, (LineString, MultiLineString)):
            # For lines, use the midpoint and calculate rotation
            if isinstance(geom, LineString):
                # Get midpoint
                mid_point = geom.interpolate(0.5, normalized=True)
                points.append(mid_point)

                # Calculate angle for text rotation
                if len(list(geom.coords)) >= 2:
                    coords = list(geom.coords)
                    mid_idx = int(len(coords) / 2)
                    if mid_idx < len(coords) - 1:
                        dx = coords[mid_idx+1][0] - coords[mid_idx][0]
                        dy = coords[mid_idx+1][1] - coords[mid_idx][1]
                        angle = (180 / 3.14159) * (dy and dx and dy/dx or 0)
                        # Normalize angle
                        if angle > 90:
                            angle -= 180
                        elif angle < -90:
                            angle += 180
                        rotations.append(angle)
                    else:
                        rotations.append(0.0)
                else:
                    rotations.append(0.0)
            else:
                # For MultiLineString, use the longest segment's midpoint
                longest_line = max(geom.geoms, key=lambda g: g.length)
                mid_point = longest_line.interpolate(0.5, normalized=True)
                points.append(mid_point)
                rotations.append(0.0)  # Simplified: no rotation for multilines

        else:
            # For points and other geometry types, use the geometry itself or its centroid
            if isinstance(geom, Point):
                points.append(geom)
            else:
                points.append(geom.centroid)
            rotations.append(0.0)

        labels.append(label_text)

    # Create GeoDataFrame with labels
    if not points:
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    label_gdf = gpd.GeoDataFrame({
        'geometry': points,
        'label': labels,
        'rotation': rotations
    }, geometry='geometry', crs=crs)

    # Set text style attributes if project_loader is provided
    if project_loader:
        style_manager = StyleManager(project_loader)
        style_name = operation.get('style')

        if style_name:
            style_data, _ = style_manager.get_style(style_name)
            if style_data:
                text_style = style_data.get('text', {})
                label_gdf.attrs['text_style'] = text_style

    return label_gdf
