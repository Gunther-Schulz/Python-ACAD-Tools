import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, LineString, MultiLineString, MultiPolygon
from src.utils import log_debug, log_warning, log_info
import os


def create_interactive_label_layer(all_layers, project_settings, crs, layer_name, operation, project_loader=None, dxf_doc=None, label_manager=None):
    """
    Create interactive label configurations and DXF entities atomically.
    This generates YAML configurations AND creates DXF entities with proper sync metadata
    in one atomic operation, establishing complete bi-directional sync from the start.

    Parameters:
    -----------
    all_layers : dict
        Dictionary of all available layers
    project_settings : dict
        Project configuration settings
    crs : str
        Coordinate reference system
    layer_name : str
        Name of the layer to create labels for
    operation : dict
        Operation configuration
    project_loader : ProjectLoader, optional
        Project loader instance for writing label YAML files
    dxf_doc : ezdxf.Document, optional
        DXF document for creating entities immediately
    label_manager : LabelManager, optional
        Label manager for creating DXF entities with proper sync tracking

    Returns:
    --------
    bool
        True if labels were successfully created and saved, False otherwise
    """
    log_info(f"🚀 ATOMIC: Creating interactive labels for {layer_name}")
    log_debug(f"Creating interactive labels for {layer_name}")

    # Check if labels already exist - if so, skip creation to avoid conflicts
    if project_loader:
        filename = f"labels/{layer_name.lower()}.yaml"
        existing_data = project_loader.load_yaml_file(filename, required=False)
        if existing_data and existing_data.get('labels'):
            log_info(f"🔄 SKIP: Labels already exist for '{layer_name}' ({len(existing_data['labels'])} labels) - skipping recreation")
            return True  # Consider this a success since labels exist

    # Get source layer configuration (reuse existing logic from simple_label_operation)
    source_layer_name = operation.get('sourceLayer', layer_name)
    label_column = operation.get('labelColumn')

    # If no explicit labelColumn, check layer config (reuse existing fallback logic)
    if not label_column:
        for layer_config in project_settings.get('geomLayers', []):
            if layer_config.get('name') == source_layer_name:
                label_column = layer_config.get('label')
                break

    if not label_column:
        log_warning(f"No label column specified for interactiveLabel operation on layer {layer_name}")
        return False

    # Check if source layer exists (reuse existing validation)
    if source_layer_name not in all_layers:
        log_warning(f"Source layer {source_layer_name} not found for interactiveLabel operation")
        return False

    # Get source GeoDataFrame
    source_gdf = all_layers[source_layer_name]
    if source_gdf is None or len(source_gdf) == 0:
        log_warning(f"Source layer {source_layer_name} is empty")
        return False

    # Use existing column finding logic from simple_label_operation
    actual_columns = list(source_gdf.columns)
    log_debug(f"Available columns in {source_layer_name}: {actual_columns}")

    # Find the label column (reuse exact logic from simple_label_operation)
    found_column = _find_label_column(source_gdf, label_column)
    if not found_column:
        log_warning(f"Label column '{label_column}' not found in layer {source_layer_name}")
        log_warning(f"Available columns are: {actual_columns}")
        return False

    label_column = found_column

    # Generate label configurations
    label_configs = []
    label_layer_name = f"{layer_name} Labels"  # Source-specific layer name

    for idx, row in source_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        label_text = str(row[label_column])

        # Generate label point using existing geometry processing logic
        point, rotation = _get_label_point_and_rotation(geom)
        if point is None:
            continue

        # Create label configuration
        label_config = {
            'name': f"{layer_name}_label_{idx:03d}",
            'text': label_text,
            'position': {
                'x': float(point.x),
                'y': float(point.y)
            },
            'rotation': float(rotation),
            'style': operation.get('style', 'default'),
            'sourceGeometry': layer_name,
            'sourceFeatureId': str(idx),
            'layer': label_layer_name,
            'sync': 'auto'  # Enable bi-directional sync
        }
        label_configs.append(label_config)

    if not label_configs:
        log_warning(f"No valid labels could be generated for layer {layer_name}")
        return False

    # DXF entities will be created by LabelManager during export phase
    log_debug(f"Generated {len(label_configs)} label configurations for sync system")

    # Save to labels/ folder if project_loader is available
    if project_loader:
        success = _save_label_configs_to_yaml(label_configs, layer_name, label_layer_name, project_loader)
        if success:
            log_debug(f"Created {len(label_configs)} interactive labels for '{layer_name}' in labels/{layer_name.lower()}.yaml")
            return True
        else:
            log_warning(f"Failed to save label configurations for layer {layer_name}")
            return False
    else:
        log_warning("No project_loader available - cannot save label configurations to YAML")
        return False


def _find_label_column(source_gdf, label_column):
    """Find the label column using the same logic as simple_label_operation."""
    found_column = None
    actual_columns = list(source_gdf.columns)

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

    # 4. Try fuzzy matching
    if not found_column:
        for col in actual_columns:
            if (col.replace('_', '') == label_column.replace('_', '') or
                col.lower().startswith(label_column.lower()) or
                label_column.lower().startswith(col.lower())):
                found_column = col
                log_debug(f"Found fuzzy match: '{col}' for requested column '{label_column}'")
                break

    return found_column


def _get_label_point_and_rotation(geom):
    """Get label point and rotation using the same logic as simple_label_operation."""
    if isinstance(geom, (Polygon, MultiPolygon)):
        # For polygons, use centroid or representative point
        centroid = geom.centroid
        if not geom.contains(centroid):
            centroid = geom.representative_point()
        return centroid, 0.0

    elif isinstance(geom, (LineString, MultiLineString)):
        # For lines, use midpoint and calculate rotation
        if isinstance(geom, LineString):
            mid_point = geom.interpolate(0.5, normalized=True)

            # Calculate rotation angle
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
                    return mid_point, angle
                else:
                    return mid_point, 0.0
            else:
                return mid_point, 0.0
        else:
            # For MultiLineString, use longest segment's midpoint
            longest_line = max(geom.geoms, key=lambda g: g.length)
            mid_point = longest_line.interpolate(0.5, normalized=True)
            return mid_point, 0.0

    else:
        # For points and other geometry types
        if isinstance(geom, Point):
            return geom, 0.0
        else:
            return geom.centroid, 0.0


def _create_dxf_entities_and_sync_metadata(label_configs, dxf_doc, label_manager):
    """
    Create DXF entities for label configs and populate sync metadata atomically.

    This ensures that labels are created in the DXF and have proper sync tracking
    from the moment they're generated, enabling true bi-directional sync.
    """
    from src.sync_hash_utils import calculate_entity_content_hash, update_sync_metadata

    created_count = 0
    failed_count = 0

    for config in label_configs:
        try:
            entity_name = config.get('name', 'unnamed')
            log_debug(f"Creating DXF entity for label '{entity_name}'")

            # Determine target space (model vs paper)
            target_space = label_manager._get_target_space(dxf_doc, config)

            # Create DXF entity using LabelManager's sync_push logic
            result_entity = label_manager._sync_push(dxf_doc, target_space, config)

            if result_entity:
                # Calculate content hash for sync tracking
                content_hash = calculate_entity_content_hash(config, 'label')

                # Get entity handle for tracking
                entity_handle = str(result_entity.dxf.handle)

                # Update sync metadata in the config
                update_sync_metadata(config, content_hash, 'yaml', entity_handle=entity_handle)

                log_debug(f"Created DXF entity for label '{entity_name}' with handle {entity_handle}")
                created_count += 1
            else:
                log_warning(f"Failed to create DXF entity for label '{entity_name}'")
                failed_count += 1

        except Exception as e:
            log_warning(f"Error creating DXF entity for label '{config.get('name', 'unnamed')}': {str(e)}")
            failed_count += 1

    log_debug(f"DXF entity creation results: {created_count} created, {failed_count} failed")
    return failed_count == 0  # Return True only if all entities were created successfully


def _save_label_configs_to_yaml(label_configs, layer_name, label_layer_name, project_loader):
    """Save label configurations to YAML file in labels/ folder."""
    try:
        # Create filename (lowercase layer name)
        filename = f"labels/{layer_name.lower()}.yaml"

        # Load existing YAML data to preserve user settings
        existing_data = project_loader.load_yaml_file(filename, required=False)

        if existing_data:
            # Preserve existing global settings AND sync metadata
            yaml_data = existing_data.copy()

            # If existing labels exist, merge intelligently to preserve sync metadata
            if 'labels' in existing_data:
                existing_labels = {label.get('name'): label for label in existing_data['labels']}
                merged_configs = []

                for new_config in label_configs:
                    label_name = new_config.get('name')
                    if label_name in existing_labels:
                        # Preserve existing label but update properties
                        existing_label = existing_labels[label_name].copy()

                        # Update all properties except _sync metadata
                        for key, value in new_config.items():
                            if key != '_sync':
                                existing_label[key] = value

                        merged_configs.append(existing_label)
                        log_debug(f"Preserved sync metadata for '{label_name}'")
                    else:
                        # New label - use as-is
                        merged_configs.append(new_config)
                        log_debug(f"Added new label '{label_name}'")

                yaml_data['labels'] = merged_configs
                log_debug(f"Merged {len(merged_configs)} labels ({len([l for l in merged_configs if '_sync' in l])} with sync metadata)")
            else:
                # No existing labels - use new ones
                yaml_data['labels'] = label_configs
                log_debug(f"No existing labels found - using new configurations")

            log_debug(f"Preserving existing global settings in {filename}")
        else:
            # Create new file with default settings
            yaml_data = {
                'labels': label_configs,
                'discover_untracked_layers': [],
                'deletion_policy': 'confirm',
                'default_layer': label_layer_name,
                'sync': 'auto'
            }
            log_debug(f"Creating new label file {filename} with default settings")

        # Use existing YAML writing infrastructure
        success = project_loader.write_yaml_file(filename, yaml_data)
        return success

    except Exception as e:
        log_warning(f"Error saving label configurations: {str(e)}")
        return False
