import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.utils import log_debug, log_warning
from src.style_manager import StyleManager

def create_point_label_layer(all_layers, project_settings, crs, layer_name, operation, project_loader=None):
    """
    Create a label layer using existing point geometries for placement.
    This function takes an existing point layer and uses those points directly
    for label placement, extracting label text from the specified column.

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
        Operation configuration with optional fields:
        - sourceLayer: name of the point layer to use for positions (defaults to current layer)
        - labelColumn: column containing the label text (falls back to layer's label field)
        - style: text style to apply
    project_loader : ProjectLoader, optional
        Project loader instance for accessing style presets

    Returns:
    --------
    GeoDataFrame
        A GeoDataFrame with Point geometries and label texts
    """
    log_debug(f"Creating point label layer for {layer_name}")

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
        log_warning(f"No label column specified for pointLabel operation on layer {layer_name}")
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    # Check if source layer exists
    if source_layer_name not in all_layers:
        log_warning(f"Source layer {source_layer_name} not found for pointLabel operation")
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

    # Filter for point geometries only
    point_rows = []
    for idx, row in source_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        # Only process Point geometries
        if not isinstance(geom, Point):
            log_warning(f"Skipping non-point geometry in row {idx} of layer {source_layer_name}")
            continue

        point_rows.append(row)

    if not point_rows:
        log_warning(f"No valid point geometries found in source layer {source_layer_name}")
        return gpd.GeoDataFrame({'geometry': [], 'label': [], 'rotation': []}, geometry='geometry', crs=crs)

    # Extract data for label layer
    points = []
    labels = []
    rotations = []

    for row in point_rows:
        geom = row.geometry
        label_text = str(row[label_column])

        # Use the existing point geometry directly
        points.append(geom)
        labels.append(label_text)

        # Check if rotation column exists and use it, otherwise default to 0
        if 'rotation' in row.index and pd.notnull(row['rotation']):
            rotations.append(float(row['rotation']))
        else:
            rotations.append(0.0)

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

    log_debug(f"Created point label layer with {len(label_gdf)} labels from {len(point_rows)} source points")
    return label_gdf
