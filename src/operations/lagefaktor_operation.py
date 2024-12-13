import geopandas as gpd
import pandas as pd
from src.utils import log_debug, log_warning, log_error, log_info, resolve_path
import yaml
import os
from openpyxl.styles import Alignment, Font, PatternFill

def create_lagefaktor_layer(all_layers, project_settings, crs, layer_name, operation):
    """Process Lagefaktor calculations for construction and compensatory areas."""
    show_log = operation.get('showLog', False)
    if show_log:
        log_info(f"-----------------Processing Lagefaktor operation for layer: {layer_name}")
    
    try:
        grz = operation.get('grz', 0.5)
        parcel_layer_name = operation.get('parcelLayer')
        parcel_label = operation.get('parcelLabel', 'name')
        protokol_output_dir = operation.get('protokolOutputDir')
        min_parcel_area_percent = operation.get('minParcelAreaPercent', None)
        edge_area_range = operation.get('edgeAreaRange', None)  # Add this line
        lagefaktor_config = operation.get('lagefaktor', operation.get('context', []))
        
        # Process construction scores
        construction_results = None
        if 'construction' in operation:
            construction_results = _process_construction(
                all_layers,
                operation['construction'],
                lagefaktor_config,
                grz,
                min_parcel_area_percent,
                edge_area_range
            )
            
        # Process compensatory scores
        compensatory_results = None
        if 'compensatory' in operation:
            compensatory_results = _process_compensatory(
                all_layers,
                operation['compensatory'],
                lagefaktor_config,
                min_parcel_area_percent,
                edge_area_range
            )
        
        # Combine results if both exist
        if construction_results is not None and compensatory_results is not None:
            result = pd.concat([construction_results, compensatory_results])
        else:
            result = construction_results if construction_results is not None else compensatory_results

        if result is not None:
            # Explode MultiPolygons into individual Polygons
            # result = result.explode(index_parts=True).reset_index(drop=True)
            
            # Add IDs without reordering columns
            result['id'] = range(1, len(result) + 1)
            
            # Generate protocol if needed
            if protokol_output_dir and protokol_output_dir.strip():
                _generate_protocol(
                    result,
                    all_layers.get(parcel_layer_name),
                    parcel_label,
                    grz,
                    protokol_output_dir,
                    layer_name
                )
            
            if show_log:
                log_info(f"Successfully processed {layer_name} with {len(result)} features")
                log_info(f"Result DataFrame summary for {layer_name}:")
                log_info(f"Total features: {len(result)}")
                log_info(f"Total area: {result['area'].sum():.2f}")
                log_info(f"Total score: {result['score'].sum():.2f}")
                log_info(f"Columns: {', '.join(result.columns)}")
            return result

        return None
        
    except Exception as e:
        log_error(f"Error in Lagefaktor operation: {str(e)}")
        import traceback
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return None

def _process_construction(all_layers, construction_config, lagefaktor_config, grz, min_parcel_area_percent, edge_area_range):
    """Process construction scores."""
    show_log = construction_config.get('showLog', False)
    result_gdf = None
    area_construction_total = 0
    
    for layer_config in construction_config['layers']:
        layer_name = layer_config['layer']
        base_value = layer_config['baseValue']
        
        layer_gdf = _process_layer_scores(
            all_layers,
            layer_name,
            base_value,
            lagefaktor_config,
            is_construction=True,
            grz=grz,
            min_parcel_area_percent=min_parcel_area_percent,
            edge_area_range=edge_area_range
        )
        
        if layer_gdf is not None:
            area_construction_total += layer_gdf['score'].sum()
            if result_gdf is None:
                result_gdf = layer_gdf
            else:
                result_gdf = pd.concat([result_gdf, layer_gdf])
    
    if area_construction_total > 0 and show_log:
        log_info(f"Total construction score: {area_construction_total:.2f}")
        log_info(f"Total construction area: {result_gdf['area'].sum():.2f}")
    
    return result_gdf

def _process_compensatory(all_layers, compensatory_config, lagefaktor_config, min_parcel_area_percent, edge_area_range):
    """Process compensatory scores."""
    show_log = compensatory_config.get('showLog', False)
    result_gdf = None
    area_compensatory_total = 0
    
    for layer_config in compensatory_config['layers']:
        layer_name = layer_config['layer']
        base_value = layer_config['baseValue']
        compensatory_value = layer_config['compensatoryMeasureValue']
        
        layer_gdf = _process_layer_scores(
            all_layers,
            layer_name,
            base_value,
            lagefaktor_config,
            is_construction=False,
            compensatory_value=compensatory_value,
            min_parcel_area_percent=min_parcel_area_percent,
            edge_area_range=edge_area_range
        )
        
        if layer_gdf is not None:
            area_compensatory_total += layer_gdf['score'].sum()
            if result_gdf is None:
                result_gdf = layer_gdf
            else:
                result_gdf = pd.concat([result_gdf, layer_gdf])
    
    if area_compensatory_total > 0 and show_log:
        log_info(f"Total compensatory score: {area_compensatory_total:.2f}")
        log_info(f"Total compensatory area: {result_gdf['area'].sum():.2f}")
    
    return result_gdf

def _process_layer_scores(all_layers, layer_name, base_value, lagefaktor_config, 
                         is_construction=True, grz=None, compensatory_value=None, 
                         min_parcel_area_percent=None, edge_area_range=None):
    """Process scores for a single layer."""
    show_log = lagefaktor_config[0].get('showLog', False) if lagefaktor_config else False
    
    if is_construction and show_log:
        log_debug(f"Processing construction layer: {layer_name}")
    
    if layer_name not in all_layers:
        log_warning(f"Layer {layer_name} not found in processed layers")
        return None

    layer_gdf = all_layers[layer_name]
    if layer_gdf.empty:
        log_warning(f"Layer {layer_name} is empty")
        return None

    # Get parcel layer from all_layers
    parcel_layer = all_layers.get('Parcel')
    if parcel_layer is not None and (min_parcel_area_percent is not None or edge_area_range is not None):
        # Calculate intersection with parcels
        intersections = gpd.overlay(layer_gdf, parcel_layer, how='intersection')
        if not intersections.empty:
            small_areas = None
            
            # Process percentage-based filtering
            if min_parcel_area_percent is not None:
                # Calculate intersection areas
                intersections['intersection_area'] = intersections.geometry.area
                
                # Get the total area of each parcel
                parcel_areas = parcel_layer.geometry.area
                
                # Map parcel areas to intersections
                intersections['parcel_area'] = intersections.index.map(parcel_areas)
                
                # Calculate what percentage of each parcel is covered by the intersection
                intersections['parcel_coverage'] = intersections['intersection_area'] / intersections['parcel_area']
                
                # Handle different types of minParcelAreaPercent
                if isinstance(min_parcel_area_percent, dict):
                    min_threshold = min_parcel_area_percent.get('min', 0) / 100.0
                    max_threshold = min_parcel_area_percent.get('max', 100) / 100.0
                    small_areas = intersections[
                        (intersections['parcel_coverage'] >= min_threshold) & 
                        (intersections['parcel_coverage'] <= max_threshold)
                    ]
                else:
                    threshold = min_parcel_area_percent / 100.0
                    small_areas = intersections[intersections['parcel_coverage'] < threshold]
            
            # Process absolute area filtering
            if edge_area_range is not None:
                if not 'intersection_area' in intersections.columns:
                    intersections['intersection_area'] = intersections.geometry.area
                
                if isinstance(edge_area_range, dict):
                    min_area = edge_area_range.get('min', 0)
                    max_area = edge_area_range.get('max', float('inf'))
                    area_filtered = intersections[
                        (intersections['intersection_area'] >= min_area) & 
                        (intersections['intersection_area'] <= max_area)
                    ]
                else:
                    # Treat single value as maximum area
                    max_area = edge_area_range
                    area_filtered = intersections[intersections['intersection_area'] < max_area]
                
                # Combine with percentage-based filtering if both are present
                if small_areas is not None:
                    small_areas = pd.concat([small_areas, area_filtered]).drop_duplicates()
                else:
                    small_areas = area_filtered
            
            if small_areas is not None and not small_areas.empty:
                # Get the boundary of the original geometries
                layer_boundaries = layer_gdf.geometry.boundary.unary_union
                
                # Only keep small areas that touch the boundary
                edge_small_areas = small_areas[small_areas.geometry.intersects(layer_boundaries)]
                
                if not edge_small_areas.empty:
                    # Instead of removing entire features, just subtract the small areas at edges
                    small_geometries = edge_small_areas.geometry.unary_union
                    # Difference operation keeps everything EXCEPT the small areas
                    layer_gdf['geometry'] = layer_gdf.geometry.difference(small_geometries)
                    if not edge_small_areas.empty and show_log:
                        log_info(f"Removed {len(edge_small_areas)} small edge areas from {layer_name}")

    result_gdf = None
    # Calculate the correct factor_sum based on GRZ formula
    if is_construction:
        factor_a = grz
        # Determine factors based on GRZ value
        if grz <= 0.5:
            factor_b = 1 - 0.4  # Factor for GRZ portion (Überschirmte Fläche)
            factor_c = 1 - 0.8  # Factor for non-GRZ portion (Zwischenmodulflächen)
        elif 0.51 <= grz <= 0.75:
            factor_b = 1 - 0.2  # Factor for GRZ portion (Überschirmte Fläche)
            factor_c = 1 - 0.5  # Factor for non-GRZ portion (Zwischenmodulflächen)
        else:
            log_warning(f"GRZ value {grz} is outside the supported range (0-0.75). Using default factors.")
            factor_b = 1 - 0.4  # Factor for GRZ portion (Überschirmte Fläche)
            factor_c = 1 - 0.8  # Factor for non-GRZ portion (Zwischenmodulflächen)
        
        # Calculate: (GRZ * factor_b + (1-GRZ) * factor_c) * 2
        factor_sum = ((grz * factor_b) + ((1-grz) * factor_c)) * 2
    
    # Ich brauche eine Spalte für Fläche x Wert und eine für Fläche x GRZ x 
    # Faktor und eine für FinaleEingriffspunkte
    
    for lf_config in lagefaktor_config:
        buffer_layer = all_layers.get(lf_config['sourceLayer'])
        if buffer_layer is None:
            continue
        
        # Perform overlay operation
        intersection = gpd.overlay(layer_gdf, buffer_layer, how='intersection')
        
        # Explode any MultiPolygons that were created during overlay
        intersection = intersection.explode(index_parts=True).reset_index(drop=True)
        
        if not intersection.empty:
            zone_gdf = intersection.copy()
            zone_gdf['base_value'] = base_value
            zone_gdf['lagefaktor'] = lf_config['value']
            zone_gdf['feature_id'] = [f"Feature_{hash(geom.wkb)}" for geom in zone_gdf.geometry]
            zone_gdf['name'] = layer_name
            zone_gdf['buffer_zone'] = lf_config['sourceLayer']
            zone_gdf['distance'] = lf_config['distance']
            zone_gdf['area'] = zone_gdf.geometry.area

            if is_construction:
                zone_gdf['base_times_lage'] = zone_gdf['base_value'] * zone_gdf['lagefaktor']
                zone_gdf['initial_value'] = zone_gdf['base_times_lage'] * zone_gdf['area']
                zone_gdf['adjusted_value'] = zone_gdf['initial_value'] * factor_a
                # Calculate grz_factor_value: Fläche x GRZ x factor_b x 2
                zone_gdf['grz_factor_value'] = zone_gdf['adjusted_value'] * factor_b * 2
                zone_gdf['final_value'] = zone_gdf['adjusted_value'] * factor_sum
                zone_gdf['score'] = zone_gdf['final_value'].round(2)
                if show_log:
                    log_debug(f"Added grz_factor_value to zone_gdf. Columns: {zone_gdf.columns.tolist()}")
                
            else:
                zone_gdf['compensatory_value'] = compensatory_value
                zone_gdf['eligible'] = True
                zone_gdf['compensat'] = compensatory_value
                zone_gdf['initial_value'] = zone_gdf['compensat'] - zone_gdf['base_value']
                zone_gdf['area_value'] = zone_gdf['area']
                zone_gdf['adjusted_value'] = zone_gdf['initial_value'] * zone_gdf['area_value']
                zone_gdf['prot_value'] = 1
                zone_gdf['final_value'] = zone_gdf['adjusted_value'] * zone_gdf['lagefaktor']
                zone_gdf['protected_final_v'] = zone_gdf['final_value'] * zone_gdf['prot_value']
                zone_gdf['score'] = zone_gdf['protected_final_v'].round(2)

            if result_gdf is None:
                result_gdf = zone_gdf
            else:
                result_gdf = pd.concat([result_gdf, zone_gdf])



    if result_gdf is not None:
        # Base columns for both types
        keep_columns = [
            'feature_id', 
            'name', 
            'buffer_zone', 
            'distance', 
            'area', 
            'score',
            'base_value',
            'initial_value',
            'adjusted_value',
            'final_value',
            'geometry'
        ]
        
        # For construction: include grz_factor_value
        if is_construction:
            keep_columns.append('grz_factor_value')
        # For compensatory: include compensatory_value
        elif 'compensatory_value' in result_gdf.columns:
            keep_columns.append('compensatory_value')
            
        return result_gdf[keep_columns]

    return result_gdf

def _generate_protocol(result_gdf, parcel_layer, parcel_label, grz, output_dir, layer_name):
    """Generate and save protocol in YAML and Excel formats."""
    show_log = result_gdf.attrs.get('show_log', False) if hasattr(result_gdf, 'attrs') else False
    
    if parcel_layer is None:
        log_warning("Parcel layer not found, skipping protocol generation")
        return

    try:
        protocol_type = "Konstruktion" if 'grz_factor_value' in result_gdf.columns else "Kompensation"
        
        protocol = {
            'Ausgleichsprotokoll': {
                'Typ': protocol_type,
                'GRZ': grz,
                'Gesamt': {
                    'Score': round(float(result_gdf['score'].sum()), 2),
                    'Flächengröße': round(float(result_gdf['area'].sum()), 2)
                },
                'Flächen-Id': {},
                'Flurstücke': {}
            }
        }

        # Add ID section - using the actual IDs from result_gdf
        for _, feature in result_gdf.iterrows():
            id_entry = {
                'Flächengröße': round(float(feature['area']), 2),
                'Biotoptyp': feature['name'],
                'Ausgangswert': float(feature['base_value']),
                'Fläche_x_Wert': round(float(feature['initial_value']), 2),
                'Fläche_x_GRZ': round(float(feature['adjusted_value']), 2),
                'FinaleEingriffspunkte': round(float(feature['final_value']), 2),
                'Score': round(float(feature['score']), 2)
            }
            
            # Add construction-specific fields
            if protocol_type == "Konstruktion":
                id_entry['Fläche_x_GRZ_x_Faktor'] = round(float(feature['grz_factor_value']), 2)
            elif 'compensatory_value' in feature:
                id_entry['Zielwert'] = float(feature['compensatory_value'])
            
            protocol['Ausgleichsprotokoll']['Flächen-Id'][str(feature['feature_id'])] = id_entry

        # First, find which parcels actually intersect with our result geometries
        result_union = result_gdf.unary_union
        intersecting_parcels = parcel_layer[parcel_layer.intersects(result_union)]
        
        if intersecting_parcels.empty:
            log_warning("No intersecting parcels found")
            return
            
        # Now calculate intersections only for relevant parcels
        parcels = gpd.overlay(intersecting_parcels, result_gdf, how='intersection')
        
        # Flurstücke section
        for parcel_id, parcel_group in parcels.groupby(parcel_label):
            measures = []
            for _, intersection in parcel_group.iterrows():
                area = intersection.geometry.area
                if area > 0.01:  # Only include if area is significant
                    area_proportion = area / intersection['area']
                    partial_score = intersection['score'] * area_proportion
                    
                    measure = {
                        'Flächen-Id': int(intersection['id']),  # Use the actual ID from result_gdf
                        'Biotoptyp': intersection['name'],
                        'Flurstücksanteilsgröße': round(float(area), 2),
                        'Zone': intersection['buffer_zone'],
                        'Ausgangswert': float(intersection['base_value']),
                        'Teilscore': round(float(partial_score), 2)
                    }
                    
                    if 'compensatory_value' in intersection:
                        measure['Zielwert'] = float(intersection['compensatory_value'])
                    
                    measures.append(measure)
            
            if measures:
                protocol['Ausgleichsprotokoll']['Flurstücke'][str(parcel_id)] = {
                    'Flächengröße': round(float(sum(m['Flurstücksanteilsgröße'] for m in measures)), 2),
                    'Maßnahmen': measures
                }

        # Generate Excel protocol
        excel_filename = f"protocol_{layer_name}.xlsx"
        excel_path = resolve_path(os.path.join(output_dir, excel_filename))
        
        # Create Excel writer object
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # Overview sheet
            overview_data = {
                'Parameter': ['Typ', 'GRZ', 'Gesamt Score', 'Gesamt Flächengröße'],
                'Wert': [
                    protocol_type,
                    grz,
                    round(float(result_gdf['score'].sum()), 2),
                    round(float(result_gdf['area'].sum()), 2)
                ]
            }
            overview_df = pd.DataFrame(overview_data)
            overview_df.to_excel(writer, sheet_name='��bersicht', index=False)

            # Flächen-Id sheet
            areas_data = []
            for _, feature in result_gdf.iterrows():
                area_entry = {
                    'Flächen-Id': feature['id'],
                    'Flächengröße': round(float(feature['area']), 2),
                    'Biotoptyp': feature['name'],
                    'Ausgangswert': float(feature['base_value']),
                    'Fläche_x_Wert': round(float(feature['initial_value']), 2),
                    'Fläche_x_GRZ': round(float(feature['adjusted_value']), 2),
                    'FinaleEingriffspunkte': round(float(feature['final_value']), 2),
                    'Score': round(float(feature['score']), 2)
                }
                
                # Add construction-specific fields only if they exist
                if 'grz_factor_value' in feature:
                    area_entry['Fläche_x_GRZ_x_Faktor'] = round(float(feature['grz_factor_value']), 2)
                if 'compensatory_value' in feature:
                    area_entry['Zielwert'] = float(feature['compensatory_value'])
                    
                areas_data.append(area_entry)
            
            areas_df = pd.DataFrame(areas_data)
            areas_df.to_excel(writer, sheet_name='Flächen', index=False)

            # Flurstücke sheet
            parcels_data = []
            result_union = result_gdf.unary_union
            intersecting_parcels = parcel_layer[parcel_layer.intersects(result_union)]
            parcels = gpd.overlay(intersecting_parcels, result_gdf, how='intersection')
            
            for _, intersection in parcels.iterrows():
                area = intersection.geometry.area
                if area > 0.01:
                    area_proportion = area / intersection['area']
                    partial_score = intersection['score'] * area_proportion
                    
                    parcel_entry = {
                        'Flurstück': intersection[parcel_label],
                        'Flächen-Id': int(intersection['id']),
                        'Biotoptyp': intersection['name'],
                        'Flurstücksanteilsgröße': round(float(area), 2),
                        'Zone': intersection['buffer_zone'],
                        'Ausgangswert': float(intersection['base_value']),
                        'Teilscore': round(float(partial_score), 2)
                    }
                    if 'compensatory_value' in intersection:
                        parcel_entry['Zielwert'] = float(intersection['compensatory_value'])
                    parcels_data.append(parcel_entry)
            
            parcels_df = pd.DataFrame(parcels_data)
            parcels_df.to_excel(writer, sheet_name='Flurstücke', index=False)

            # Apply formatting
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

                # Format headers
                for cell in worksheet[1]:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color='E0E0E0', end_color='E0E0E0', fill_type='solid')
        if show_log:
            log_info(f"Excel protocol saved to {excel_path}")

    except Exception as e:
        log_error(f"Error generating protocol: {str(e)}")
        import traceback
        log_error(f"Traceback:\n{traceback.format_exc()}")
