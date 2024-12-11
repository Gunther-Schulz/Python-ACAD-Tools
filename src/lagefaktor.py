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

    def process_scores(self, layer_processor):
        """Process both construction and compensatory scores for all configured areas."""
        log_info(f"-------------Processing scores for {len(self.config)} areas")
        
        # Create GeoDataFrames to store all results
        construction_results = None
        compensatory_results = None
        
        for area_config in self.config:
            area_name = area_config['name']
            grz = area_config.get('grz', 0.0)
            output_dir = area_config.get('outputDir', '')
            
            try:
                # Process construction scores
                if 'construction' in area_config:
                    construction_gdf = self._process_area_construction(
                        layer_processor,
                        area_config,
                        area_name,
                        grz=grz
                    )
                    
                    if construction_gdf is not None:
                        construction_gdf['area_name'] = area_name
                        if construction_results is None:
                            construction_results = construction_gdf
                        else:
                            construction_results = pd.concat([construction_results, construction_gdf])
                        
                        # Save to layer processor
                        layer_name = f"{area_name}_construction_results"
                        layer_processor.all_layers[layer_name] = construction_gdf
                        if output_dir:
                            layer_processor.write_shapefile(layer_name)
                
                # Process compensatory scores
                if 'compensatory' in area_config:
                    compensatory_gdf = self._process_area_compensatory(
                        layer_processor,
                        area_config,
                        area_name
                    )
                    
                    if compensatory_gdf is not None:
                        compensatory_gdf['area_name'] = area_name
                        if compensatory_results is None:
                            compensatory_results = compensatory_gdf
                        else:
                            compensatory_results = pd.concat([compensatory_results, compensatory_gdf])
                        
                        # Save to layer processor
                        layer_name = f"{area_name}_compensatory_results"
                        layer_processor.all_layers[layer_name] = compensatory_gdf
                        if output_dir:
                            layer_processor.write_shapefile(layer_name)
                
            except Exception as e:
                log_error(f"Error processing scores for area {area_name}: {str(e)}")
                import traceback
                log_error(f"Traceback:\n{traceback.format_exc()}")
        
        return construction_results, compensatory_results

    def _process_area_construction(self, layer_processor, area_config, area_name, grz):
        """Process construction scores for a single area."""
        area_construction_total = 0
        result_gdf = None
        
        construction_config = area_config['construction']
        for layer_config in construction_config['layers']:
            layer_name = layer_config['layer']
            base_value = layer_config['baseValue']
            
            layer_gdf = self._process_layer_scores(
                layer_processor,
                layer_name,
                base_value,
                area_config.get('lagefaktor', []),
                area_name,
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
            log_info(f"Total construction score for {area_name}: {area_construction_total:.2f}")
        
        return result_gdf

    def _process_area_compensatory(self, layer_processor, area_config, area_name):
        """Process compensatory scores for a single area."""
        area_compensatory_total = 0
        result_gdf = None
        
        compensatory_config = area_config['compensatory']
        for layer_config in compensatory_config['layers']:
            layer_name = layer_config['layer']
            base_value = layer_config['baseValue']
            compensatory_value = layer_config['compensatoryMeasureValue']
            
            layer_gdf = self._process_layer_scores(
                layer_processor,
                layer_name,
                base_value,
                area_config.get('lagefaktor', []),
                area_name,
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
            log_info(f"Total compensatory score for {area_name}: {area_compensatory_total:.2f}")
        
        return result_gdf

    def _process_layer_scores(self, layer_processor, layer_name, base_value, lagefaktor_config, area_name, is_construction=True, grz=None, compensatory_value=None):
        """Process scores for a single layer."""
        if layer_name not in layer_processor.all_layers:
            log_warning(f"Layer {layer_name} not found in processed layers")
            return None

        layer_gdf = layer_processor.all_layers[layer_name]
        if layer_gdf.empty:
            log_warning(f"Layer {layer_name} is empty")
            return None

        # Create a copy to avoid modifying the original
        result_gdf = layer_gdf.copy()
        result_gdf['base_value'] = base_value
        result_gdf['lagefaktor'] = 1.0  # Default lagefaktor
        result_gdf['feature_id'] = [f"Feature_{hash(geom.wkb)}" for geom in result_gdf.geometry]
        result_gdf['name'] = layer_name  # Add feature type/name
        
        # Process lagefaktor intersections
        processed_areas = gpd.GeoDataFrame(geometry=[])
        for lf_config in lagefaktor_config:
            buffer_layer = layer_processor.all_layers.get(lf_config['sourceLayer'])
            if buffer_layer is None:
                continue
            
            intersection = gpd.overlay(
                result_gdf[~result_gdf.geometry.isin(processed_areas.geometry)],
                buffer_layer,
                how='intersection'
            )
            
            if not intersection.empty:
                intersection['lagefaktor'] = lf_config['value']
                result_gdf.loc[result_gdf.geometry.isin(intersection.geometry), 'lagefaktor'] = lf_config['value']
                processed_areas = pd.concat([processed_areas, intersection])

        # Calculate areas
        result_gdf['area'] = result_gdf.geometry.area

        if is_construction:
            # Construction calculation aligned with add_construction_score
            result_gdf['base_times_lage'] = result_gdf['base_value'] * result_gdf['lagefaktor']
            result_gdf['initial_value'] = result_gdf['base_times_lage'] * result_gdf['area']
            
            # Get GRZ factors
            factor_a = grz if grz else 0.5  # Default if not specified
            factor_b = 0.2
            factor_c = 0.6
            factor_sum = factor_b + factor_c
            
            result_gdf['adjusted_value'] = result_gdf['initial_value'] * factor_a
            result_gdf['final_value'] = result_gdf['adjusted_value'] * factor_sum
            result_gdf['score'] = result_gdf['final_value'].round(2)
            
            # Store GRZ factors for logging
            result_gdf['factor_a'] = factor_a
            result_gdf['factor_b'] = factor_b
            result_gdf['factor_c'] = factor_c
            
            # Log calculation details
            for _, row in result_gdf.iterrows():
                self._log_construction_calculation(area_name, row)
            
        else:
            # Compensatory calculation aligned with calculate_compensatory_score
            result_gdf['eligible'] = True  # Default to eligible
            result_gdf['compensat'] = compensatory_value
            result_gdf['initial_value'] = result_gdf['compensat'] - result_gdf['base_value']
            result_gdf['area_value'] = result_gdf['area']
            result_gdf['adjusted_value'] = result_gdf['initial_value'] * result_gdf['area_value']
            
            # Protection value handling (simplified version)
            result_gdf['prot_value'] = 1  # Default protection value
            
            result_gdf['final_value'] = result_gdf['adjusted_value'] * result_gdf['lagefaktor']
            result_gdf['protected_final_v'] = result_gdf['final_value'] * result_gdf['prot_value']
            result_gdf['score'] = result_gdf['protected_final_v'].round(2)
            
            # Log calculation details
            for _, row in result_gdf.iterrows():
                if row['eligible']:
                    self._log_compensatory_calculation(area_name, row)
                else:
                    log_debug(f"Feature marked as not eligible - Feature ID: {row['feature_id']} - Feature Type: {row['name']} - Score: 0")

        layer_score = result_gdf['score'].sum()
        score_type = "Construction" if is_construction else "Compensatory"
        log_info(f"{score_type} score for {area_name} - {layer_name}: {layer_score:.2f}")

        return result_gdf

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

    def _calculate_compensatory_scores(self, features, area_name):
        """Calculate compensatory scores for features."""
        def calculate_score(row):
            if not row['eligible']:
                log_debug(f"Feature {self._create_feature_identifier(row)} marked as not eligible - Score: 0")
                return 0
            
            area = row.geometry.area
            compensat = row['compensat']
            base_value = row['base_value']
            lagefaktor = row['lagefaktor']
            
            # Calculate intermediate values
            initial_value = compensat - base_value
            area_value = area
            adjusted_value = initial_value * area
            
            # For now, using default protection value of 1
            # This can be extended to support protected areas configuration
            prot_value = 1
            
            final_v = adjusted_value * lagefaktor
            protected_final_v = final_v * prot_value
            
            # Store detailed calculation steps
            row['calculation'] = {
                'feature_id': self._create_feature_identifier(row),
                'area': area,
                'compensat': compensat,
                'base_value': base_value,
                'lagefaktor': lagefaktor,
                'initial_value': initial_value,
                'area_value': area_value,
                'adjusted_value': adjusted_value,
                'prot_value': prot_value,
                'final_v': final_v,
                'protected_final_v': protected_final_v
            }
            
            # Log detailed calculation steps
            self._log_compensatory_protocol(row['calculation'], area_name)
            
            return round(protected_final_v, 2)
        
        # Calculate scores
        features['score'] = features.apply(calculate_score, axis=1)
        return features

    def _log_compensatory_protocol(self, calc_data, area_name):
        """Log detailed compensatory calculation protocol."""
        protocol_message = (
            f"Compensatory Score Calculation for {area_name}:\n"
            f"  Feature ID: {calc_data['feature_id']}\n"
            f"  Area: {calc_data['area']:.2f}\n"
            f"  Step 1 (Compensatory - Base): {calc_data['compensat']} - {calc_data['base_value']} = {calc_data['initial_value']}\n"
            f"  Step 2 (Initial * Area): {calc_data['initial_value']} * {calc_data['area_value']:.2f} = {calc_data['adjusted_value']:.2f}\n"
            f"  Step 3 (Adjusted * Lagefaktor): {calc_data['adjusted_value']:.2f} * {calc_data['lagefaktor']} = {calc_data['final_v']:.2f}\n"
            f"  Step 4 (Final * Protection): {calc_data['final_v']:.2f} * {calc_data['prot_value']} = {calc_data['protected_final_v']:.2f}\n"
            f"  Final Score: {calc_data['protected_final_v']:.2f}\n"
            f"-------------------"
        )
        log_debug(protocol_message)

    def _log_construction_calculation(self, area_name, row):
        """Log the details of a construction calculation."""
        log_debug(f"Construction Score Calculation for {area_name}:\n"
                  f"  Feature ID: {row['feature_id']}\n"
                  f"  Feature Type: {row['name']}\n"
                  f"  Area: {row['area']:.2f}\n"
                  f"  Base Value: {row['base_value']}\n"
                  f"  Lagefaktor: {row['lagefaktor']}\n"
                  f"  Step 1 (Base * Lagefaktor): {row['base_times_lage']:.2f}\n"
                  f"  Step 2 (Step 1 * Area) = Initial Value: {row['initial_value']:.2f}\n"
                  f"  Step 3 (Initial * Factor A [{row['factor_a']}]) = Adjusted Value: {row['adjusted_value']:.2f}\n"
                  f"  Step 4 (Factor B + Factor C = {row['factor_b']} + {row['factor_c']}): {row['factor_b'] + row['factor_c']:.2f}\n"
                  f"  Step 5 (Adjusted * (B+C)) = Final Value: {row['final_value']:.2f}\n"
                  f"  GRZ Factors (a,b,c): {row['factor_a']}, {row['factor_b']}, {row['factor_c']}\n"
                  f"  Final Score: {row['score']}\n"
                  f"-------------------")

    def _log_compensatory_calculation(self, area_name, row):
        """Log the details of a compensatory calculation."""
        log_debug(f"Compensatory Score Calculation for {area_name}:\n"
                  f"  Feature ID: {row['feature_id']}\n"
                  f"  Feature Type: {row['name']}\n"
                  f"  Area: {row['area']:.2f}\n"
                  f"  Step 1 (Compensatory - Base): {row['compensat']} - {row['base_value']} = {row['initial_value']}\n"
                  f"  Step 2 (Initial * Area): {row['initial_value']} * {row['area_value']:.2f} = {row['adjusted_value']:.2f}\n"
                  f"  Step 3 (Adjusted * Lagefaktor): {row['adjusted_value']:.2f} * {row['lagefaktor']} = {row['final_value']:.2f}\n"
                  f"  Step 4 (Final * Protection): {row['final_value']:.2f} * {row['prot_value']} = {row['protected_final_v']:.2f}\n"
                  f"  Final Score: {row['score']:.2f}\n"
                  f"-------------------")
