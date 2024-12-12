import geopandas as gpd
import pandas as pd
from src.utils import log_debug, log_warning, log_error, log_info, resolve_path
import yaml
import os

def create_lagefaktor_layer(all_layers, project_settings, crs, layer_name, operation):
    """Process Lagefaktor calculations for construction and compensatory areas."""
    log_info(f"-----------------Processing Lagefaktor operation for layer: {layer_name}")
    
    try:
        grz = operation.get('grz', 0.5)
        parcel_layer_name = operation.get('parcelLayer')
        parcel_label = operation.get('parcelLabel', 'name')
        protokol_output_dir = operation.get('protokolOutputDir')
        lagefaktor_config = operation.get('lagefaktor', operation.get('context', []))
        
        # Process construction scores
        construction_results = None
        if 'construction' in operation:
            construction_results = _process_construction(
                all_layers,
                operation['construction'],
                lagefaktor_config,
                grz
            )
            
        # Process compensatory scores
        compensatory_results = None
        if 'compensatory' in operation:
            compensatory_results = _process_compensatory(
                all_layers,
                operation['compensatory'],
                lagefaktor_config
            )
        
        # Combine results if both exist
        if construction_results is not None and compensatory_results is not None:
            result = pd.concat([construction_results, compensatory_results])
        else:
            result = construction_results if construction_results is not None else compensatory_results

        if result is not None:
            # Explode MultiPolygons into individual Polygons
            result = result.explode(index_parts=True).reset_index(drop=True)
            
            # Reassign IDs after explosion
            result['id'] = range(1, len(result) + 1)
            cols = ['id'] + [col for col in result.columns if col != 'id']
            result = result[cols]
            
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
            
            log_info(f"Successfully processed {layer_name} with {len(result)} features")
            print(result)
            return result

        return None
        
    except Exception as e:
        log_error(f"Error in Lagefaktor operation: {str(e)}")
        import traceback
        log_error(f"Traceback:\n{traceback.format_exc()}")
        return None

def _process_construction(all_layers, construction_config, lagefaktor_config, grz):
    """Process construction scores."""
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
            grz=grz
        )
        
        if layer_gdf is not None:
            area_construction_total += layer_gdf['score'].sum()
            if result_gdf is None:
                result_gdf = layer_gdf
            else:
                result_gdf = pd.concat([result_gdf, layer_gdf])
    
    if area_construction_total > 0:
        log_info(f"Total construction score: {area_construction_total:.2f}")
    
    return result_gdf

def _process_compensatory(all_layers, compensatory_config, lagefaktor_config):
    """Process compensatory scores."""
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
            compensatory_value=compensatory_value
        )
        
        if layer_gdf is not None:
            area_compensatory_total += layer_gdf['score'].sum()
            if result_gdf is None:
                result_gdf = layer_gdf
            else:
                result_gdf = pd.concat([result_gdf, layer_gdf])
    
    if area_compensatory_total > 0:
        log_info(f"Total compensatory score: {area_compensatory_total:.2f}")
    
    return result_gdf

def _process_layer_scores(all_layers, layer_name, base_value, lagefaktor_config, is_construction=True, grz=None, compensatory_value=None):
    """Process scores for a single layer."""
    if layer_name not in all_layers:
        log_warning(f"Layer {layer_name} not found in processed layers")
        return None

    layer_gdf = all_layers[layer_name]
    if layer_gdf.empty:
        log_warning(f"Layer {layer_name} is empty")
        return None

    result_gdf = None
    
    # Store GRZ factors for logging
    if is_construction:
        factor_a = grz if grz else 0.5
        factor_b = 0.2
        factor_c = 0.6
        factor_sum = factor_b + factor_c
    
    for lf_config in lagefaktor_config:
        buffer_layer = all_layers.get(lf_config['sourceLayer'])
        if buffer_layer is None:
            continue
        
        intersection = gpd.overlay(layer_gdf, buffer_layer, how='intersection')
        
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
                zone_gdf['final_value'] = zone_gdf['adjusted_value'] * factor_sum
                zone_gdf['score'] = zone_gdf['final_value'].round(2)
                
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

            # Log calculations
            for _, row in zone_gdf.iterrows():
                if is_construction:
                    _log_construction_calculation(layer_name, row, factor_a, factor_b, factor_c)
                elif row['eligible']:
                    _log_compensatory_calculation(layer_name, row)

    if result_gdf is not None:
        # Define base columns to keep
        keep_columns = [
            'feature_id', 
            'name', 
            'buffer_zone', 
            'distance', 
            'area', 
            'score',
            'base_value',
            'geometry'
        ]
        
        # Add compensatory_value column only if it exists (for compensatory areas)
        if not is_construction and 'compensatory_value' in result_gdf.columns:
            keep_columns.append('compensatory_value')
            
        return result_gdf[keep_columns]

    return result_gdf

def _log_construction_calculation(layer_name, row, factor_a, factor_b, factor_c):
    """Log construction calculation details."""
    log_debug(f"Construction Score Calculation for {layer_name}:\n"
              f"  Feature ID: {row['feature_id']}\n"
              f"  Area: {row['area']:.2f}\n"
              f"  Base Value: {row['base_value']}\n"
              f"  Lagefaktor: {row['lagefaktor']}\n"
              f"  Step 1 (Base * Lagefaktor): {row['base_times_lage']:.2f}\n"
              f"  Step 2 (Step 1 * Area): {row['initial_value']:.2f}\n"
              f"  Step 3 (Initial * Factor A [{factor_a}]): {row['adjusted_value']:.2f}\n"
              f"  Step 4 (Factor B + Factor C = {factor_b} + {factor_c}): {factor_b + factor_c:.2f}\n"
              f"  Final Score: {row['score']:.2f}\n"
              f"-------------------")

def _log_compensatory_calculation(layer_name, row):
    """Log compensatory calculation details."""
    log_debug(f"Compensatory Score Calculation for {layer_name}:\n"
              f"  Feature ID: {row['feature_id']}\n"
              f"  Area: {row['area']:.2f}\n"
              f"  Step 1 (Compensatory - Base): {row['compensat']} - {row['base_value']} = {row['initial_value']}\n"
              f"  Step 2 (Initial * Area): {row['initial_value']} * {row['area_value']:.2f} = {row['adjusted_value']:.2f}\n"
              f"  Step 3 (Adjusted * Lagefaktor): {row['adjusted_value']:.2f} * {row['lagefaktor']} = {row['final_value']:.2f}\n"
              f"  Step 4 (Final * Protection): {row['final_value']:.2f} * {row['prot_value']} = {row['protected_final_v']:.2f}\n"
              f"  Final Score: {row['score']:.2f}\n"
              f"-------------------") 

def _generate_protocol(result_gdf, parcel_layer, parcel_label, grz, output_dir, layer_name):
    """Generate and save protocol in YAML format."""
    if parcel_layer is None:
        log_warning("Parcel layer not found, skipping protocol generation")
        return

    try:
        # First, find which parcels actually intersect with our result geometries
        result_union = result_gdf.unary_union
        intersecting_parcels = parcel_layer[parcel_layer.intersects(result_union)]
        
        if intersecting_parcels.empty:
            log_warning("No intersecting parcels found")
            return
            
        # Now calculate intersections only for relevant parcels
        parcels = gpd.overlay(intersecting_parcels, result_gdf, how='intersection')
        
        protocol = {
            'Ausgleichsprotokoll': {
                'Typ': 'Konstruktion',
                'GRZ': grz,
                'Gesamt': {
                    'Score': round(float(result_gdf['score'].sum()), 2),
                    'Fläche': round(float(result_gdf['area'].sum()), 2)
                },
                'Flurstücke': {}
            }
        }

        for parcel_id, parcel_group in parcels.groupby(parcel_label):
            measures = []
            for _, intersection in parcel_group.iterrows():
                area = intersection.geometry.area
                if area > 0.01:  # Only include if area is significant
                    # Calculate partial score based on area proportion
                    area_proportion = area / intersection['area']
                    partial_score = intersection['score'] * area_proportion
                    
                    measure = {
                        'ID': int(intersection['id']),
                        'Biotoptyp': intersection['name'],
                        'Flurstücksanteilsgröße': round(float(area), 2),
                        'Zone': intersection['buffer_zone'],
                        'Ausgangswert': float(intersection['base_value']),
                        'Teilscore': round(float(partial_score), 2)
                    }
                    
                    # Add Zielwert if compensatory_value exists
                    if 'compensatory_value' in intersection:
                        measure['Zielwert'] = float(intersection['compensatory_value'])
                    
                    measures.append(measure)
            
            # Only add to protocol if there are actual measures
            if measures:
                protocol['Ausgleichsprotokoll']['Flurstücke'][str(parcel_id)] = {
                    'Fläche': round(float(sum(m['Flurstücksanteilsgröße'] for m in measures)), 2),
                    'Maßnahmen': measures
                }

        filename = f"protocol_{layer_name}.yaml"
        output_path = resolve_path(os.path.join(output_dir, filename))
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(protocol, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
        log_info(f"Protocol saved to {output_path}")

    except Exception as e:
        log_error(f"Error generating protocol: {str(e)}")
        import traceback
        log_error(f"Traceback:\n{traceback.format_exc()}")
