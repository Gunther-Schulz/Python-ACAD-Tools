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
        
        for area_config in self.config:
            if 'construction' not in area_config:
                continue
                
            area_name = area_config['name']
            grz = area_config.get('grz', 0.0)
            construction_config = area_config['construction']
            area_total = 0  # Track total for this area
            
            try:
                # Process each construction layer
                for layer_config in construction_config['layers']:
                    layer_name = layer_config['layer']
                    base_value = layer_config['baseValue']
                    
                    if layer_name not in layer_processor.all_layers:
                        log_warning(f"Layer {layer_name} not found for construction calculation")
                        continue
                        
                    # Get the layer's GeoDataFrame
                    gdf = layer_processor.all_layers[layer_name]
                    if gdf is None or len(gdf) == 0:
                        log_warning(f"Layer {layer_name} is empty")
                        continue
                        
                    # Add base value to features
                    gdf['base_value'] = base_value
                    
                    # Calculate Lagefaktor based on area
                    gdf['lagefaktor'] = gdf.geometry.area.apply(
                        lambda x: self._get_lagefaktor_value(x, construction_config['lagefaktorValues'])
                    )
                    
                    # Calculate construction scores
                    scored_gdf = self._calculate_construction_scores(gdf, grz, area_name)
                    layer_score = scored_gdf['score'].sum()
                    area_total += layer_score
                    
                    # Log layer score
                    log_info(f"Construction score for {area_name} - {layer_name}: {layer_score:.2f}")
                    
                    # Update the layer in layer_processor
                    layer_processor.all_layers[layer_name] = scored_gdf
                    
                    log_debug(f"Processed construction scores for layer: {layer_name}")
                    
                # Log area total
                log_info(f"Total construction score for {area_name}: {area_total:.2f}")
                    
            except Exception as e:
                log_error(f"Error processing construction scores for area {area_name}: {str(e)}")
        

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
        # Add score calculation
        def calculate_score(row):
            area = row.geometry.area
            base_value = row['base_value']
            lagefaktor = row['lagefaktor']
            
            # Calculate intermediate values
            base_times_lage = base_value * lagefaktor
            initial_value = base_times_lage * area
            
            # TODO: Replace with actual GRZ factors from configuration
            factor_a = 1.0  # These should come from configuration
            factor_b = 1.0
            factor_c = 0.0
            
            adjusted_value = initial_value * factor_a
            factor_sum = factor_b + factor_c
            final_value = adjusted_value * factor_sum
            
            # Log calculation steps
            calculation_steps = {
                'area': area,
                'base_value': base_value,
                'lagefaktor': lagefaktor,
                'base_times_lage': base_times_lage,
                'initial_value': initial_value,
                'adjusted_value': adjusted_value,
                'final_value': final_value
            }
            
            # Add calculation steps to row attributes
            if 'attributes' not in row:
                row['attributes'] = {}
            row['attributes']['calculation'] = calculation_steps
            
            return round(final_value, 2)
        
        # Calculate scores
        features['score'] = features.apply(calculate_score, axis=1)
        
        log_debug(f"Calculated construction scores for area: {area_name}")
        return features
