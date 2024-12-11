import geopandas as gpd
import pandas as pd
from pathlib import Path
from src.utils import log_debug, log_warning, log_error, log_info

class LagefaktorProcessor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.config = self._load_lagefaktor_config()
        
    def _load_lagefaktor_config(self):
        """Load the lagefaktor configuration from the project."""
        try:
            # Use project_loader to load the lagefaktor config
            config = self.project_loader.load_yaml_file('lagefaktor.yaml', required=False)
            if not config:
                log_warning("No Lagefaktor configuration found in project directory")
                return []
            return config
        except Exception as e:
            log_error(f"Error loading lagefaktor config: {str(e)}")
            return []

    def process_construction_scores(self, layer_processor):
        """Process construction scores for all configured areas."""
        log_info(f"-------------Processing construction scores for {len(self.config)} areas")
        total_score_all_areas = 0
        
        for area_config in self.config:
            if 'construction' not in area_config:
                continue
                
            area_name = area_config['name']
            grz = area_config.get('grz', 0.0)
            construction_config = area_config['construction']
            area_total = 0
            
            try:
                # Process each construction layer
                for layer_config in construction_config['layers']:
                    layer_name = layer_config['layer']
                    base_value = layer_config['baseValue']
                    
                    if layer_name not in layer_processor.all_layers:
                        log_warning(f"Layer {layer_name} not found for construction calculation")
                        continue
                        
                    # Get the layer's GeoDataFrame
                    gdf = layer_processor.all_layers[layer_name].copy()
                    if gdf is None or len(gdf) == 0:
                        log_warning(f"Layer {layer_name} is empty")
                        continue
                        
                    # Add base value to features
                    gdf['base_value'] = base_value
                    
                    # Keep track of processed areas
                    processed_areas = gpd.GeoDataFrame(geometry=[], crs=gdf.crs)
                    result_gdf = gpd.GeoDataFrame(geometry=[], crs=gdf.crs)
                    
                    # Process lagefaktor for each distance range
                    for lf_config in area_config.get('lagefaktor', []):
                        source_layer = lf_config['sourceLayer']
                        if source_layer not in layer_processor.all_layers:
                            log_warning(f"Lagefaktor source layer {source_layer} not found")
                            continue
                            
                        # Intersect with buffer layer
                        buffer_gdf = layer_processor.all_layers[source_layer]
                        intersection = gpd.overlay(gdf, buffer_gdf, how='intersection')
                        if not intersection.empty:
                            intersection['lagefaktor'] = lf_config['value']
                            result_gdf = pd.concat([result_gdf, intersection])
                            processed_areas = pd.concat([processed_areas, intersection])
                    
                    # Check for unprocessed areas
                    if not processed_areas.empty:
                        unprocessed = gdf[~gdf.geometry.intersects(processed_areas.geometry.union_all())]
                    else:
                        unprocessed = gdf
                        
                    if not unprocessed.empty:
                        log_warning(f"Found areas in layer '{layer_name}' that don't intersect with any buffer zone. "
                                  f"These areas will be excluded from the calculation.")
                        
                    if result_gdf.empty:
                        log_warning(f"No areas in layer '{layer_name}' intersect with any buffer zones")
                        continue
                    
                    # Calculate scores
                    scored_gdf = self._calculate_construction_scores(result_gdf, grz, area_name)
                    layer_score = scored_gdf['score'].sum()
                    area_total += layer_score
                    
                    # Log layer score
                    log_info(f"Construction score for {area_name} - {layer_name}: {layer_score:.2f}")
                    
                    # Update the layer in layer_processor
                    layer_processor.all_layers[layer_name] = scored_gdf
                    
                log_info(f"Total construction score for {area_name}: {area_total:.2f}")
                total_score_all_areas += area_total
                        
            except Exception as e:
                log_error(f"Error processing construction scores for area {area_name}: {str(e)}")
                import traceback
                log_error(f"Traceback:\n{traceback.format_exc()}")
        
        log_info(f"Total construction score across all areas: {total_score_all_areas:.2f}")
        

    def _get_lagefaktor_value(self, area, lagefaktor_values):
        """Determine the lagefaktor value based on area."""
        for range_str, value in lagefaktor_values.items():
            # Handle the special case for ranges like '>100<625'
            if '>' in range_str and '<' in range_str:
                min_val = float(range_str.split('<')[0].replace('>', ''))
                max_val = float(range_str.split('<')[1])
                if min_val < area < max_val:
                    return value
            # Handle simple less than case
            elif '<' in range_str:
                max_val = float(range_str.replace('<', ''))
                if area < max_val:
                    return value
            # Handle greater than case
            elif '>' in range_str:
                min_val = float(range_str.replace('>', ''))
                if area > min_val:
                    return value
                    
        log_warning(f"No matching lagefaktor value found for area: {area}")
        return 1.0  # Default value if no match found

    def _calculate_construction_scores(self, features, grz, area_name):
        """Calculate construction scores for features."""
        def calculate_score(row):
            area = row.geometry.area
            base_value = row['base_value']
            lagefaktor = row['lagefaktor']
            
            # Calculate intermediate values
            base_times_lage = base_value * lagefaktor
            initial_value = base_times_lage * area
            
            # Get GRZ factors from configuration instead of hardcoded values
            factor_a, factor_b, factor_c = self._get_grz_factors(grz)
            
            adjusted_value = initial_value * factor_a
            factor_sum = factor_b + factor_c
            final_value = adjusted_value * factor_sum
            
            # Store detailed calculation steps
            row['calculation'] = {
                'feature_id': self._create_feature_identifier(row),
                'area': area,
                'base_value': base_value,
                'lagefaktor': lagefaktor,
                'base_times_lage': base_times_lage,
                'initial_value': initial_value,
                'factor_a': factor_a,
                'factor_b': factor_b,
                'factor_c': factor_c,
                'adjusted_value': adjusted_value,
                'factor_sum': factor_sum,
                'final_value': final_value
            }
            
            # Log detailed calculation steps
            self._log_calculation_protocol(row['calculation'], area_name)
            
            return round(final_value, 2)
        
        # Calculate scores
        features['score'] = features.apply(calculate_score, axis=1)
        
        # Log the total score for this area
        total_score = features['score'].sum()
        log_debug(f"Calculated construction scores for area: {area_name}")
        
        return features

    def _get_grz_factors(self, grz):
        """
        Get the GRZ factors based on the GRZ value.
        
        Args:
            grz (float): The GRZ value as specified in the configuration
            
        Returns:
            tuple: (factor_a, factor_b, factor_c)
        """
        # Define GRZ factors
        GRZ_FACTORS = {
            '0.5': [0.5, 0.2, 0.6],
            '0.75': [0.75, 0.5, 0.8]
        }
        
        # Convert grz to string for dictionary lookup
        grz_str = str(grz)
        
        if grz_str in GRZ_FACTORS:
            factors = GRZ_FACTORS[grz_str]
            return tuple(factors)  # returns (factor_a, factor_b, factor_c)
        else:
            log_warning(f"No GRZ factors defined for GRZ={grz}. Using default values.")
            return (1.0, 1.0, 0.0)  # default values if GRZ not found

    def _create_feature_identifier(self, feature):
        """Create a unique identifier for the feature."""
        # Implement feature identification logic
        return f"Feature_{hash(str(feature.geometry))}"

    def _log_calculation_protocol(self, calc_data, area_name):
        """Log detailed calculation protocol."""
        protocol_message = (
            f"Construction Score Calculation for {area_name}:\n"
            f"  Feature ID: {calc_data['feature_id']}\n"
            f"  Area: {calc_data['area']:.2f}\n"
            f"  Base Value: {calc_data['base_value']}\n"
            f"  Lagefaktor: {calc_data['lagefaktor']}\n"
            f"  Step 1 (Base * Lagefaktor): {calc_data['base_times_lage']:.2f}\n"
            f"  Step 2 (Step 1 * Area) = Initial Value: {calc_data['initial_value']:.2f}\n"
            f"  Step 3 (Initial * Factor A [{calc_data['factor_a']}]) = Adjusted Value: {calc_data['adjusted_value']:.2f}\n"
            f"  Step 4 (Factor B + Factor C = {calc_data['factor_b']} + {calc_data['factor_c']}): {calc_data['factor_sum']:.2f}\n"
            f"  Step 5 (Adjusted * (B+C)) = Final Value: {calc_data['final_value']:.2f}\n"
            f"-------------------"
        )
        log_debug(protocol_message)
